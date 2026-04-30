# CRAWLER.md — dynamic crawl daemon for Nepal gov RAG

Design spec for the long-lived crawler behind the dynamic RAG corpus defined in
`PIPELINE.md`. This is the Rust daemon that replaces the Python prototype in
`scripts/crawl_sources.py`.

Dated 2026-04-20. Authored after the Python prototype hit a relative-path
compounding trap on supremecourt.gov.np and ran for 18 hours on one source.
That run produced ~4 GB of mostly-usable blobs; a proper daemon supersedes it.

Related:
- `PIPELINE.md` — end-to-end RAG pipeline; this doc covers the crawl stage only
- `DOCUMENT.md` — engineering log
- `STORY.md` — plain-English narrative

---

## Purpose

Continuously ingest Nepal government web content into a local corpus that
feeds a RAG-based question-answering engine. The crawl is a live, polling
system — not a one-shot. Sources in the registry get polled at tier-specific
cadences (6h–48h), diffs produce versioned documents, and sites that drift
structurally get flagged for agent-driven recipe repair.

## Goals

1. **Correct under adversarial sites.** Relative-path traps, calendar
   combinatorics, infinite pagination, JS-rendered shells — all must be
   detected and handled without operator intervention.
2. **Polite, per-domain.** Rate limiting and concurrency are per-domain, never
   global. Slow or flaky sites don't block fast ones.
3. **Resumable and diff-aware.** Every doc is content-hashed; re-polling is
   idempotent; changes produce new versioned rows that supersede old ones.
4. **Recipe-driven overrides.** Per-source JSON lets us encode exceptions
   (JS rendering, subdomain rules, deny/allow lists) without forking code.
   Recipes are the surface the agent-repair loop modifies.
5. **Observable.** Per-source health metrics and structural-failure detection
   are first-class, not grep-the-log afterthoughts.
6. **Single binary, one box.** Runs on k2 under `launchd`. No Docker, no
   message broker, no distributed coordination.

## Non-goals (v1)

- Distributed crawling across machines
- A fully-general web crawler; Nepal gov quirks are allowed to leak into logic
- Document chunking, embedding, or retrieval (downstream stages)
- Agent-repair execution (the hook exists; the agent invocation is separate)

---

## Architecture

```
┌─────────────────────────────── crawl-daemon (Rust) ──────────────────────────────┐
│                                                                                    │
│   ┌─────────────┐                                                                  │
│   │  scheduler  │ tick every 60s; pick sources where next_poll_at <= now           │
│   └──────┬──────┘                                                                  │
│          │                                                                         │
│          ▼                                                                         │
│   ┌──────────────────────────────────────────────────────────────────────────┐    │
│   │ worker pool (tokio, N≈10 per-source tasks concurrent)                    │    │
│   │                                                                           │    │
│   │   ┌── per-source task ──────────────────────────────────────────────┐   │    │
│   │   │                                                                   │   │    │
│   │   │   load recipe  ─────► resolved_policy                            │   │    │
│   │   │   load manifest ────► visited + priors                           │   │    │
│   │   │                                                                   │   │    │
│   │   │   priority frontier ◄─── recipe.entry_points                     │   │    │
│   │   │         │                                                         │   │    │
│   │   │         ▼ (pop highest priority)                                  │   │    │
│   │   │   ┌─────────────────────┐                                        │   │    │
│   │   │   │ fetch strategy:     │                                        │   │    │
│   │   │   │  - Plain (reqwest)  │  default fast path                     │   │    │
│   │   │   │  - Chromium (cdp)   │  if recipe.js_render_required          │   │    │
│   │   │   └─────────┬───────────┘                                        │   │    │
│   │   │             │                                                     │   │    │
│   │   │             ▼                                                     │   │    │
│   │   │   parse ─┬─ html: readability → shell-check → links              │   │    │
│   │   │         ├─ pdf:  raw bytes only (extraction deferred to ingest)  │   │    │
│   │   │         └─ other: record + skip                                   │   │    │
│   │   │             │                                                     │   │    │
│   │   │             ▼                                                     │   │    │
│   │   │   canonicalize + score + enqueue new links                        │   │    │
│   │   │             │                                                     │   │    │
│   │   │             ▼                                                     │   │    │
│   │   │   persist: SQLite row + content-hashed blob + extracted text      │   │    │
│   │   │             │                                                     │   │    │
│   │   │             ▼                                                     │   │    │
│   │   │   budget check → continue, or stop with stop_reason               │   │    │
│   │   └───────────────────────────────────────────────────────────────────┘   │    │
│   └──────────────────────────────────────────────────────────────────────────┘    │
│          │                                                                         │
│          ▼                                                                         │
│   ┌──────────────┐                                                                 │
│   │ health eval  │ post-poll rolling stats → flag structural failures             │
│   └──────┬───────┘                                                                 │
│          ▼                                                                         │
│   ┌──────────────┐                                                                 │
│   │ repair queue │ jsonl; evidence bundles for claude-code-driven recipe patches  │
│   └──────────────┘                                                                 │
│                                                                                    │
│   admin CLI: init | poll | describe | status | health | import-legacy | daemon    │
└────────────────────────────────────────────────────────────────────────────────────┘
```

Component ownership:

| Module | Responsibility |
|---|---|
| `crawler_v2::types` | Source, Recipe, Document, FetchEvent structs |
| `crawler_v2::store` | SQLite schema, migrations, CRUD |
| `crawler_v2::registry` | Sync `sources_tiered.jsonl` into SQLite |
| `crawler_v2::recipe` | Load per-source recipe, overlay defaults |
| `crawler_v2::url` | Canonicalize, classify, score |
| `crawler_v2::frontier` | Priority queue + seen-set per source |
| `crawler_v2::fetch` | Plain + Chromium fetch strategies |
| `crawler_v2::parse` | HTML → text + links; PDF → raw bytes |
| `crawler_v2::shell_detect` | Heuristic for JS-only shells |
| `crawler_v2::worker` | Per-source async task |
| `crawler_v2::pool` | Multi-source orchestration |
| `crawler_v2::health` | Rolling stats + structural-failure detection |
| `crawler_v2::scheduler` | Tick loop, pick next sources by cadence |
| `bin/crawl` | CLI entry (subcommands) |

---

## Data model

### SQLite (`/Volumes/T9/gemma-god/corpus_v2/index.db`)

Single file. WAL mode. Migrations table at the top.

```sql
CREATE TABLE sources (
  source_id            TEXT PRIMARY KEY,
  domain               TEXT NOT NULL,
  homepage_url         TEXT NOT NULL,
  name_en              TEXT,
  name_np              TEXT,
  office_type          TEXT,
  province             TEXT,
  tier                 INTEGER NOT NULL,
  poll_interval_hours  INTEGER NOT NULL,
  status               TEXT NOT NULL DEFAULT 'active',   -- active|dormant|dead|js_only
  first_seen           TEXT NOT NULL,
  last_polled_at       TEXT,
  last_changed_at      TEXT,
  last_failure_at      TEXT,
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  next_poll_at         TEXT,                             -- scheduler index
  notes                TEXT
);
CREATE INDEX ix_sources_next_poll   ON sources(next_poll_at);
CREATE INDEX ix_sources_tier_status ON sources(tier, status);

CREATE TABLE documents (
  doc_id               TEXT PRIMARY KEY,   -- hash(source_id || url || content_hash)
  source_id            TEXT NOT NULL REFERENCES sources(source_id),
  url                  TEXT NOT NULL,
  content_hash         TEXT NOT NULL,
  fetched_at           TEXT NOT NULL,
  superseded_by        TEXT REFERENCES documents(doc_id),
  removed_at           TEXT,
  doc_type             TEXT NOT NULL,      -- html|pdf|docx|xlsx|other
  status_code          INTEGER NOT NULL,
  title                TEXT,
  language             TEXT,
  date_published       TEXT,
  raw_blob_path        TEXT NOT NULL,
  extracted_text_path  TEXT,
  text_chars           INTEGER NOT NULL DEFAULT 0,
  size_bytes           INTEGER NOT NULL,
  depth                INTEGER NOT NULL,
  priority_at_fetch    INTEGER
);
CREATE UNIQUE INDEX ux_documents_source_url_live
  ON documents(source_id, url) WHERE superseded_by IS NULL AND removed_at IS NULL;
CREATE INDEX ix_documents_source_hash ON documents(source_id, content_hash);

CREATE TABLE fetch_events (
  event_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id  TEXT NOT NULL,
  url        TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  status     INTEGER NOT NULL,
  elapsed_ms INTEGER,
  error      TEXT,
  doc_type   TEXT,
  bytes      INTEGER
);
CREATE INDEX ix_fetch_events_source_time ON fetch_events(source_id, fetched_at);

CREATE TABLE source_health (
  source_id                    TEXT PRIMARY KEY REFERENCES sources(source_id),
  window_start                 TEXT NOT NULL,
  window_end                   TEXT NOT NULL,
  fetches                      INTEGER NOT NULL,
  successes                    INTEGER NOT NULL,
  empty_extractions            INTEGER NOT NULL,
  avg_text_chars               REAL NOT NULL,
  content_hash_change_rate     REAL NOT NULL,
  is_structural_failure        INTEGER NOT NULL DEFAULT 0,
  failure_reason               TEXT
);
```

**Why SQLite, not JSONL:**
- Re-polling needs `WHERE source_id=? AND url=?` lookups — O(log N), not O(full scan).
- Diff detection needs transactional "insert new row + set old row's `superseded_by`."
- Multi-reader for admin CLI while daemon writes.
- Fits on disk; no server process.

### Filesystem (`/Volumes/T9/gemma-god/corpus_v2/`)

```
index.db                                    # SQLite, single file
blobs/
  <source_id>/
    <hash[0:2]>/<content_hash>.{html|pdf|bin}   # sharded by prefix
extracted/
  <source_id>/
    <hash[0:2]>/<content_hash>.txt              # readable HTML text
recipes/
  federal/<source_id>.json                      # versioned in git (symlinked in)
  province/<source_id>.json
  local/<source_id>.json
  defaults.json
logs/
  crawl-YYYY-MM-DD.log
repair_queue.jsonl                              # append-only, consumed by agent-repair
legacy/                                         # archived Python-prototype artifacts
  manifests/, raw/, extracted/
```

**Content-hashed blobs:** same bytes from two URLs store once. A `documents`
row references the blob; blob is not deleted when a doc is superseded (keeps
history cheap).

### Recipe JSON (sparse)

```json
{
  "source_id": "moha_gov_np",
  "version": 1,
  "entry_points": ["https://moha.gov.np/"],
  "deny_paths":  ["/gallery/", "/carousel/", "/team/"],
  "allow_paths": null,
  "max_depth": 2,
  "max_pdf_depth": 3,
  "max_html_fetches": 250,
  "max_total_fetches": 1500,
  "max_elapsed_sec": 1200,
  "rate_limit_ms": 1000,
  "respect_robots": true,
  "allowed_subdomains": ["www", "en"],
  "custom_user_agent": null,
  "js_render_required": false,
  "notes": "",
  "last_repaired_at": null,
  "repaired_by": null
}
```

Every field optional except `source_id` and `entry_points`. Unset → baked-in
default applies. Default recipe = `recipes/defaults.json` shipped with the
binary, overrideable by same-name recipe under `federal/`, `province/`, etc.

---

## Algorithm

### 1. Priority scoring (at enqueue time)

```
score(url, depth) = 100
  + 30  if ext ∈ {.pdf, .doc, .docx, .xls, .xlsx, .ppt, .pptx}
  + 20  if path matches {/content/, /post/, /download/, /notice/,
                         /circular/, /act/, /rule/, /bulletin/}
  + 10  if path matches {/category/, /archive/, ?page=N for N≤5}
  -  5  if path matches {/gallery/, /carousel/, /team/, /contact/,
                         /map/, /tag/}
  -  2 * depth
```

Priority queue ordered max-first. Score ≤ 0 → reject.

### 2. URL canonicalization (ordered pipeline)

Applied to every discovered link, in this exact order:

1. Reject non-http/https scheme.
2. Percent-encode unsafe bytes in path and query.
3. Strip URL fragment.
4. Strip tracking params: `utm_*`, `fbclid`, `gclid`, `ref`, `source`.
5. Sort remaining query params lexicographically.
6. Lowercase scheme + host.
7. Strip trailing `/index.html`, normalize duplicate slashes, strip trailing `/`.
8. **Reject pathological paths:**
   - path length > 500
   - segment count > 15
   - any segment repeats ≥ 3 times (the supremecourt trap)
9. **Reject trap patterns:**
   - calendar combinatorics: `?year=*&month=*`, `?date=` with parse-able date
   - admin/login/logout endpoints: `/admin/`, `/login/`, `/logout/`, `/wp-admin/`
   - unbounded pagination: `?page=N` with N > 20
   - print/amp duplicates: `/print/`, `/amp/`, `?view=print`
10. Public-suffix-list check for same-site (use `publicsuffix` crate).
11. Dedup against per-source visited set (from manifest preload + in-run).

### 3. Fetch politeness

```
fetch(url):
  acquire per-domain semaphore (capacity = 1)
  sleep recipe.rate_limit_ms + jitter(0..300ms)
  perform reqwest (or chromiumoxide if recipe.js_render_required)
    with timeout, size cap, TLS-tolerant config, user-agent
  on 429 / 503 + Retry-After: sleep that duration, retry once
  on 5xx without Retry-After: exponential backoff, retry once, then give up
  on success: reset source.consecutive_failures = 0
  release semaphore
  return (status, content_type, body_bytes, elapsed_ms)
```

One semaphore per domain means workers can fetch 10 different domains
concurrently but never issue concurrent requests to the same domain.

### 4. Parse + shell detection

```
parse(url, content_type, body):
  if content_type contains "html":
    extracted_text = readability(body)     # via scraper + custom rules
    links          = extract_anchor_hrefs(body, base=url)
    script_count   = count_script_tags(body)
    if len(extracted_text) < 200
       AND len(links) < 3
       AND script_count >= 1:
      return ShellDetected
    // NOTE: the first spec had `script_count > 5`. Real audit against
    // oag.gov.np and psc.gov.np (modern Vue+Vite SPAs) showed they ship
    // with 1-2 module scripts, not 5+. Relaxed to `>= 1`; the tight text
    // and link bounds still prevent false positives on normal pages.
    return HtmlDoc { extracted_text, links }
  elif content_type contains "pdf" or url ends in .pdf:
    return PdfDoc { raw: body }
  elif url ends in known_doc_ext:
    return OtherDoc { ext, raw: body }
  else:
    return Skip
```

**Shell-detected behavior:** flip `source.status` to `js_only`, persist a recipe
patch with `js_render_required: true` (auto-applied for Tiers 3-5, queued for
human review for Tiers 1-2), abort this fetch cycle for the source. The next
cycle uses chromiumoxide.

### 5. Fetch strategy selection

```rust
enum FetchStrategy { Plain, Chromium }

fn choose(recipe: &Recipe, source: &Source) -> FetchStrategy {
    if recipe.js_render_required || source.status == "js_only" {
        FetchStrategy::Chromium
    } else {
        FetchStrategy::Plain
    }
}
```

`Plain` = reqwest, fast, default. `Chromium` = chromiumoxide driving a
long-lived headless Chromium via CDP — open tab, navigate, wait for
`networkidle0`, extract rendered `document.documentElement.outerHTML`, close
tab. Memory: ~100 MB per open tab; we keep max 2 tabs open.

### 6. Budget enforcement (checked before every frontier pop)

```
if source.html_fetched >= recipe.max_html_fetches:   stop("html_cap")
if source.total_fetched >= recipe.max_total_fetches: stop("total_cap")
if now - source.start_time >= recipe.max_elapsed_sec: stop("elapsed_cap")
if source.consecutive_failures >= 20:                stop("dead_source")
```

`stop_reason` persists on the `source_health` row for the cycle.

### 7. Per-domain concurrency model

- N worker tasks (default N=10) in a tokio runtime.
- Each worker owns one source at a time, drained to completion or budget stop.
- Per-domain semaphore (capacity 1) shared across all tasks — but since each
  worker owns its source and no two sources share a domain (source_id is
  keyed by domain), the semaphore is per-source in practice. Keeping the
  primitive per-domain allows future multi-source-per-domain cases.

With 10 concurrent sources at ~5 min average = **~30 min total for 57 sources**
vs ~5 hours sequential. 6x speedup without sacrificing politeness.

### 8. Diff detection + versioning

On fetch success:
```
h = sha256(body)
existing = SELECT doc_id FROM documents
           WHERE source_id=? AND url=? AND superseded_by IS NULL
if existing AND existing.content_hash == h:
    # no change; just touch last_seen
    UPDATE documents SET fetched_at=now WHERE doc_id=existing
elif existing AND existing.content_hash != h:
    # content changed; new version supersedes old
    INSERT new row; UPDATE old SET superseded_by=new.doc_id
    source.last_changed_at = now
else:
    # first time seeing this url
    INSERT new row
```

Removed URLs (404 on re-poll for a previously-200 URL) set `removed_at`.

---

## Failure taxonomy + repair

| Class | Symptom | Action |
|---|---|---|
| Transient | 5xx, timeout, DNS, single fetch | Next cadence retries; no agent |
| Transient-persistent | 3+ consecutive 5xx/timeout | Exponential-backoff the source; double its poll interval temporarily |
| Permanent dead | 410 Gone, domain expired, N=20 consecutive failures | `status=dead`, stop polling, alert |
| Policy block | Robots newly forbids, 403 with WAF signature | `status=dormant`, alert |
| Structural | 200 + 0 extracted links over N polls | Enqueue to repair_queue |
| Shell | First-fetch shell detection | Auto-flip to Chromium strategy (low tiers) or human review (T1-2) |
| Stuck-static | No content_hash change 30d+ on previously-active source | Enqueue to repair_queue |

**Repair-queue entry** (append-only JSONL):

```json
{
  "source_id": "oag_gov_np",
  "detected_at": "2026-04-20T09:00:00Z",
  "failure_class": "shell",
  "evidence": {
    "recent_manifests": [...],
    "current_recipe": {...},
    "sample_html_path": "blobs/oag_gov_np/../239d...html",
    "extracted_chars": 34,
    "script_count": 12,
    "link_count": 0
  },
  "proposed_fix_hint": "js_render_required=true"
}
```

Agent-repair execution is a separate concern (future `crawl-repair` CLI or
external driver). This design only exposes the queue.

---

## Tech stack

- **Rust** (stable), edition 2021
- **Tokio** — async runtime
- **reqwest** — HTTP client for Plain strategy; TLS via `rustls` with
  `danger_accept_invalid_certs` for .gov.np's expired-cert reality
- **chromiumoxide** — CDP client for Chromium strategy
- **scraper** — HTML parsing + CSS selectors
- **publicsuffix** — same-site membership
- **rusqlite** (with `bundled` feature) — storage
- **serde** + **serde_json** — recipe + registry serialization
- **clap** — CLI
- **tracing** + **tracing-subscriber** — structured logging
- **sha2** — content hashing
- **url** — URL parsing/normalization

External binary deps on k2:
- Chromium via `brew install chromium` (one-time, for JS strategy)
- `pdftotext` via `brew install poppler` (for downstream ingest, not crawler itself)

---

## Phased build plan

Tracked as tasks #35-44 (plus #27 for the Python run still finishing).

| Phase | Task | Est. | Output |
|---|---|---|---|
| 0 | #35 | (now) | `CRAWLER.md` (this file) |
| 1 | #36 | 2-3h | `crawler_v2::{types,store,registry}` + SQLite init; `crawl init` CLI |
| 2 | #37 | 2h | `crawler_v2::{url,frontier}` + trap-filter unit tests |
| 3a | #38 | 3h | `crawler_v2::{fetch,parse,shell_detect}` plain path |
| 3b | #39 | 2h | `crawler_v2::fetch` Chromium path via chromiumoxide |
| 4 | #40 | 1h | `crawler_v2::recipe` + `recipes/defaults.json` |
| 5 | #41 | 3h | `crawler_v2::{worker,pool}` + `crawl poll` CLI |
| 6 | #42 | 1h | `crawler_v2::health` + repair_queue.jsonl writer |
| 7 | #43 | 1h | `crawl daemon` + launchd plist on k2 |
| import | #44 | 1h | `crawl import-legacy` pulls Python manifests into SQLite |

**Total: ~14-17 hours.** Phases land incrementally — Phase 1 produces a
usable SQLite-populated registry; Phase 5 produces a working one-shot
crawler; Phase 7 makes it a daemon.

---

## Migration from Python prototype

The Python `scripts/crawl_sources.py` is producing output right now at
`/Volumes/T9/gemma-god/corpus_v2/`. Policy:

1. **Let the Python run finish.** The 5 remaining hours produce a v0 corpus
   we can import rather than discard.
2. **After it finishes**, move artifacts to `corpus_v2/legacy/`:
   ```
   legacy/manifests/<source_id>.jsonl
   legacy/raw/<source_id>/
   legacy/extracted/<source_id>/
   ```
3. **Run `crawl import-legacy`** (task #44): reads the JSONL manifests,
   inserts into `documents` with `priority_at_fetch=NULL` and a note flag
   `ingested_from='python_crawler_v1'`. Blobs get moved (not re-hashed) into
   the new sharded `blobs/` layout.
4. **Natural re-polling supersedes** the legacy rows on the Rust daemon's
   next cycle per tier cadence.

Sources that only got 1-record stubs from Python (oag, psc, moc — JS shells)
stay imported as placeholders and will be re-crawled via the Chromium path
automatically.

---

## Observability

**Structured logging** (tracing crate):
- Per-fetch: source_id, url, status, elapsed_ms, bytes, doc_type
- Per-source-cycle: source_id, pages, pdfs, errors, stop_reason, elapsed_sec
- Per-cycle: sources_run, total_fetches, repair_queue_depth

**Admin CLI**:
- `crawl status` — overall daemon state, next-poll-due sources, queue depths
- `crawl status <source_id>` — single-source detail: recent fetches, hash-change
  history, health window
- `crawl health --since 24h` — rolling per-source success rate, flag anomalies
- `crawl describe <source_id>` — dump resolved recipe/policy (defaults + override)

**Metrics file** (optional, phase 7+):
- Write per-tick summary JSON to `logs/metrics-YYYY-MM-DD.jsonl` for later
  Grafana/dashboard import if we want visualization.

---

## Open questions (TBD during implementation)

1. **Chromium tab-pool size.** Start with 2 concurrent tabs; tune upward if
   JS-only sources back up. Memory ceiling on k2 is the constraint.
2. **Retry policy on transient 5xx.** One retry with backoff is the v1 plan;
   may need to raise to 3 if we see frequent Nepal gov flakiness.
3. **Recipe schema versioning.** `version: 1` field exists; migration rules
   when we add fields are TBD. For now: agent-repair writes new recipes with
   newer versions; loader tolerates older versions by filling defaults.
4. **Robots.txt cache TTL.** Default 24h. May need to honor `Cache-Control`
   from robots.txt fetch.
5. **Subdomain inheritance.** A source at `moha.gov.np` — does the crawler
   follow links to `aaosatbise.moha.gov.np`? Policy: yes by default (same
   registrable domain), overrideable via `allowed_subdomains` in recipe.
