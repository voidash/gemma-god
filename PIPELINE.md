# PIPELINE.md — dynamic RAG corpus for Nepal gov information

Design doc, 2026-04-19. Supersedes the training-first plan in `PLAN.md` for
everything downstream of data ingestion. The Rust corpus pipeline
(classify / Preeti convert / OCR / crawl) stays; it becomes the input layer
of the living corpus rather than feeding a CPT run.

Related:
- `DOCUMENT.md` — engineering log (2026-04-19 entry captures the pivot)
- `STORY.md` — plain-English narrative
- `PLAN.md` — original training-centric plan (kept as historical reference)

---

## Goal

A self-updating, queryable, citeable knowledge base of Nepal government
information. Input: ~850 .gov.np domains + their PDFs. Output: a hybrid
BM25 + vector index that takes a Nepali / Roman-NE / English / code-mixed
query and returns top-k passages with source URLs and publish dates.

Non-goal: teaching a language model the facts. Facts live in the corpus.
The model's job is query understanding and grounded answer composition via
Meridian → Sonnet; a local Gemma 4 fallback is optional and deferred.

---

## Architecture at a glance

```
 ┌─────────────────────┐
 │ digobikas AJAX dump │   one-time seed of ~850 sources
 └──────────┬──────────┘
            ▼
 ┌─────────────────────┐
 │  sources registry   │   SQLite table, tier-ranked, next_poll_at per row
 └──────────┬──────────┘
            │            ┌──────────────────┐
            ▼            │  repair queue    │
 ┌─────────────────────┐ │  (structural     │
 │  scheduled poller   │─┤   breakage only) │
 │  (Rust, launchd)    │ └────────┬─────────┘
 └──────────┬──────────┘          │
            ▼                     ▼
 ┌─────────────────────┐  ┌───────────────────────┐
 │  recipe-driven      │  │  claude-code headless │
 │  deterministic      │  │  rewrites recipe JSON │
 │  fetcher            │  │  → git commit + PR    │
 └──────────┬──────────┘  └───────────────────────┘
            ▼
 ┌─────────────────────┐
 │  extract / clean    │   reuses src/*.rs (Preeti, OCR, classify)
 └──────────┬──────────┘
            ▼
 ┌─────────────────────┐
 │  diff + version     │   content_hash compare, supersede on change
 └──────────┬──────────┘
            ▼
 ┌─────────────────────┐
 │  chunk + embed      │   500-tok chunks, BGE-M3, LanceDB
 └──────────┬──────────┘
            ▼
 ┌─────────────────────┐
 │  hybrid retrieval   │   BM25 + vec, RRF fusion, tier tiebreak
 └──────────┬──────────┘
            ▼
 ┌─────────────────────┐
 │  Meridian → Sonnet  │   composes grounded answer with citations
 └─────────────────────┘
```

---

## Data model

### `sources` (SQLite)

Seeded from digobikas. One row per gov domain.

| field | notes |
|---|---|
| `source_id` | stable primary key, slug-style (e.g. `moha_gov_np`) |
| `domain` | bare `moha.gov.np` (no scheme, no path) |
| `homepage_url` | full URL from digobikas (may include `/en` or `/np`) |
| `name_en`, `name_np` | from digobikas |
| `office_type` | `Federal` \| `Province` \| `Local level` |
| `province` | `null` for Federal, else province name |
| `tier` | 1–5 (see table below) |
| `poll_interval_hours` | derived from tier, overridable |
| `first_seen`, `last_polled`, `last_changed`, `last_failure_at` | timestamps |
| `consecutive_failures` | for transient-retry vs structural-repair gating |
| `status` | `active` \| `dormant` \| `dead` |

### `documents` (SQLite)

One row per fetched URL at a point in time. Old versions stay; `superseded_at`
points at the replacement row.

| field | notes |
|---|---|
| `doc_id` | stable hash |
| `source_id` | FK |
| `url` | absolute |
| `content_hash` | sha256 of normalized extracted text |
| `fetched_at` | timestamp |
| `superseded_at`, `removed_at` | nullable |
| `doc_type` | `html` \| `pdf` \| `scanned_pdf` \| `img` |
| `title`, `date_published` | best-effort from selectors or PDF metadata |
| `language` | `dev` \| `en` \| `roman_ne` \| `mixed` |
| `raw_blob_path` | on-disk path under T9 |
| `extracted_text_path` | on-disk path under T9 |

### `chunks` (LanceDB)

Retrieval-time unit. Metadata denormalized so filter+fetch is one round trip.

| field | notes |
|---|---|
| `chunk_id` | `{doc_id}:{idx}` |
| `doc_id` | FK |
| `text` | 500–800 tokens, 10% overlap |
| `embedding` | BGE-M3 fp16, 1024-d |
| `char_start`, `char_end` | for span-level citations |
| `url`, `tier`, `date_published`, `language` | denormalized |

---

## Polling schedule

| Tier | Who | Count | Interval | Polls/day |
|---|---|---|---|---|
| 1 | Gazette, Constitution, Acts | ~5 | **6h** | 20 |
| 2 | Federal ministries | 25 | **12h** | 50 |
| 3 | Departments / autonomous offices | ~40 | **24h** | 40 |
| 4 | Province-level offices | ~75 | **3.5 days** | 22 |
| 5 | Local palikas (all 753) | ~750 | **48h** | 375 |

**~500 polls/day total.** One check every ~3 min on average. Per-domain
rate limit: 1 req/s. Randomized within the bucket to avoid thundering herds.

---

## Recipe schema (v1 — minimal)

One JSON file per source under `recipes/`. Versioned in git. Every field
optional except `source_id` and `entry_points`. Fields get added only when an
actual breakage proves we need them — no speculative schema.

```json
{
  "source_id": "moha_gov_np",
  "version": 1,
  "entry_points": ["https://moha.gov.np/en/"],
  "pagination": null,
  "link_selectors": null,
  "pdf_selectors": null,
  "content_selectors": null,
  "date_extractor": null,
  "language_hint": null,
  "preeti_convert": false,
  "respect_robots": true,
  "notes": ""
}
```

**Default behavior** when selectors are `null`: the fetcher walks the
entry_points, extracts all links one hop deep (same-host only), snapshots
every linked HTML/PDF. This "dumb mode" is how every recipe starts life.
Smart selectors get added only when dumb mode misses something important
(observed post-crawl) or drifts (detected post-repair-trigger).

**Why per-site, never shared:** two palikas running the same Joomla theme
still get two independent files. When the theme updates, breakage is
isolated to the specific palikas our poller hits first. Diversity of
recipes = diversity of failure modes we can repair incrementally. One
shared-template recipe = 500 simultaneous breakages.

---

## Failure classes

The fetcher records, per poll attempt: HTTP status, byte count, extraction
count (docs emitted), extraction signal (not-junk-heuristic). Triggers are
computed over the rolling window.

| Symptom | Class | Action |
|---|---|---|
| HTTP 5xx / timeout / DNS fail, <3 consecutive | transient | do nothing; next cadence retries |
| HTTP 5xx / timeout, ≥3 consecutive | transient-persistent | back off, increase interval 2×, keep retrying |
| HTTP 200 + 0 extracted docs for ≥5 polls on previously-productive source | **structural** | enqueue to repair queue |
| HTTP 200 + extraction but junk-heuristic fails (wrapper instead of content) | **structural** | enqueue to repair queue |
| content_hash unchanged 30d+ on a historically-active source | suspicious | enqueue to repair queue (possibly stuck on page 1) |
| Robots.txt newly forbids us | policy | mark dormant, alert |

Transient cases **never** invoke an agent — they retry on schedule and
usually self-heal when the gov site comes back.

---

## Repair loop (structural failures only)

```
structural failure detected
    → enqueue (source_id, last N failure logs, fresh HTML sample)
    → dispatcher drains queue every 1h
    → spawn `claude-code --print` (headless, via Meridian)
        input: current recipe + failure evidence + recipe schema + 3 example working recipes
        output: proposed updated recipe JSON
    → dry-run the proposed recipe against the fresh sample
        if dry_run_extracted ≥ 1 AND passes junk-heuristic:
            tier 3-5: auto-apply, git commit "repair(domain): v{n} → v{n+1}"
            tier 1-2: route to human review queue (wrong citations = legal problem)
        else:
            dead-letter, alert, human review
```

Repair is rare, slow, expensive, human-auditable. It is never in the hot path.

---

## Compute envelope

Full stack runs on k2 (M2 Ultra, 64 GB).

| Component | Cost |
|---|---|
| Poller (Rust, async) | ~50 MB resident, idle between polls |
| Fetcher (per-poll) | 1–2 HTTP GETs for diff check; ~10–50 GETs on change |
| Network sustained | ~1500 req/day total; ~25 min active fetch spread over 24h |
| Extractor (existing Rust) | CPU-bound, ms/doc |
| Embedder (BGE-M3 via MLX, fp16) | ~2 GB VRAM; ~500 chunks/sec |
| First-pass embed (~170k chunks) | ~6 minutes one-time |
| Delta embed (25 changes/day × 50 chunks) | ~2 seconds/day |
| Disk | ~5–8 GB total on T9 (raw blobs + extracted text + LanceDB + SQLite) |

No separate box. `launchd` runs the poller under user session on k2.

---

## Stage-by-stage execution order

1. **#23** Document the pause — this file + DOCUMENT.md + STORY.md. ✅ (in progress)
2. **#24** This doc. ✅ (in progress)
3. **#25** Seed source registry from digobikas → `corpora/sources.jsonl`.
4. **#26** Tier assignment heuristic; produce `corpora/sources_tiered.jsonl`
   for human eyeball review on Tiers 1–3.
5. **#27** First-pass crawl of Tier 1+2 (~30 sources) via existing Rust
   crawler. Generates the initial doc set.
6. **#29** Chunk + embed that doc set into LanceDB.
7. **#30** Hybrid retrieval API (BM25 + vec + RRF + tier tiebreak). Rust lib.
8. **#28** Scheduled poller with diff-based re-ingest + structural-failure
   detection. Includes repair-queue dispatcher + claude-code invocation.
9. Expand crawl to Tier 3–5 (separate batch per tier to manage throughput).
10. **#31** Scrape r/Nepal gov questions from our existing Reddit dump.
11. **#32** Build 100-item human-reviewed eval set via retrieval → Sonnet
    → review.
12. **#33** Baseline Gemma 4 E4B IT on Belebele + FLORES + Roman-NE.
13. Decide: does local Gemma 4 answer-composition meet bar? If yes, local
    fallback path. If no, Meridian → Sonnet is the only composer; Gemma 4
    stays paused.

---

## Eval-set plan (task #32)

100 items, human-reviewed. Pipeline:

1. Filter r/Nepal Reddit dump → gov-procedure questions.
2. Retain top-voted answer as a *hint* (not ground truth).
3. For each question: retrieval → top-k chunks → Sonnet composes answer.
   Sonnet prompt: "Answer using only these sources. Cite each claim with
   [source_url]. If no source covers a claim, drop it or mark `unverified`."
4. Human (ashish) reviews each draft: fact-check the answer against the cited
   gov URL; fix or drop.
5. Lands in `eval/gov_helpdesk_gold_v1.jsonl`.

Metrics:
- **Retrieval recall@k** — did we fetch a chunk whose URL matches the
  ground-truth source? Measures retrieval.
- **Answer chrF** — composed answer vs reference. Measures retrieval + composer.
- **Human rubric** — 10-item held-out set graded on (a) correctness,
  (b) citation quality, (c) handles-no-answer-gracefully.

Train set (SFT, if Gemma 4 comes off ice): larger (~5–10k), same pipeline,
no human review, kept with provenance so bad slices can be dropped later.

---

## Open decisions

- **Embedder:** BGE-M3 (default) vs jina-embeddings-v3. Benchmark both on a
  50-item Nepali retrieval probe before locking in.
- **Repair gate for Tier 1–2:** default is always-human-review. Confirm.
- **Meridian access:** gateway URL + auth discovery pending; needed at stages
  7 (for repair-time claude-code) and 11 (for eval composer).
- **Storage root:** `/Volumes/T9/gemma-god/corpus_v2/` planned. Confirm.
- **Gemma 4 baseline timing:** runs independently of the pipeline, can kick
  off any time on k2 (~45 min). Not a blocker.
