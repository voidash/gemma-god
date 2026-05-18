# CLAUDE.md — project context for the next agent session

This is the project-level brief. The global instructions at
`~/.claude/CLAUDE.md` already cover the user's tone preferences (no
sycophancy, challenge requests, verify before assuming). This file covers
what's true about *this codebase* right now.

---

## Project in one paragraph

Nepal-gov helpdesk knowledge system. Goal is a deployable RAG stack —
typically targeted at a Pi 5 / helpdesk PC — that answers Nepali +
Roman-NE + code-mixed questions using a corpus of ~877 `.gov.np` sources.
The composer model (eventual Gemma 4B SFT, Sonnet/Kimi via API for the
demo) sits on top of a hybrid BM25 + vector retrieval over content the
crawler v2 daemon keeps fresh. Current demo scope: **Jiri Municipality**
(`jirimun.gov.np`) plus ~10 federal parent sources.

---

## Documentation index — read these before doing anything else

| Doc | Read when | What it covers |
|---|---|---|
| `SERVICE_NAVIGATOR_MODUS_OPERANDI.md` | **always, first** | canonical product behavior: intake before RAG, follow-up rules, memory, source routing, human-source policy, gap logging |
| `PROACTIVE_WHATSAPP_OUTREACH.md` | changing missing-info escalation or WhatsApp contact routing | operator-reviewed outreach queue: draft from source gap, official contact discovery, Baileys send, audit/safety rules |
| `SFT_V5_POSTMORTEM_AND_NEXT_PASS.md` | before any SFT/data/eval work | 2026-05-13 v5 run result, smoke failures, and the new planner/composer SFT direction |
| `AGENTS.md` | any coding-agent session | shortest repo-level instruction pointer for future agents |
| `STORY.md` | starting fresh | plain-English narrative of how we got here, the CPT-v1 failure, why we pivoted to RAG |
| `PIPELINE.md` | designing/changing the RAG pipeline | retrieval architecture, polling cadence, recipe schema, eval-set plan |
| `CRAWLER.md` | touching `src/crawler_v2/*` | full crawler design: types, schema, frontier, recipe loader, daemon |
| `BENCHMARKS.md` | running or interpreting evals | every benchmark we run with samples + baseline & CPT v1 numbers + the gaps |
| `DOCUMENT.md` | historical context for a specific decision | engineering log, decisions, dead-ends |
| `PLAN.md` | mostly historical | original training-first plan; superseded by PIPELINE.md but useful for "why did we…" |
| `README.md` | last-resort reader | high-level pitch |

---

## Codebase layout

```
src/
  lib.rs                      # crate root
  legacy_fonts.rs             # Preeti/Kantipur/Sagarmatha → Unicode
  ocr.rs                      # Tesseract+pdftoppm wrapper (unused in v2; Phase-29 era)
  crawler_v2/                 # everything live
    mod.rs                    # module aggregator + re-exports
    types.rs                  # Source, Document, FetchEvent, PollCycle, RepairItem, …
    store.rs                  # rusqlite Store + schema + migrations (CURRENT_VERSION=3)
    blobs.rs                  # content-addressable blob store
    fetch.rs                  # async Fetcher (rustls, gzip/brotli, timeout caps)
    parse.rs                  # content-type → ParsedHtml | Binary | Unsupported
    shell_detect.rs           # JS-shell heuristic (script_count >= 1 + low text)
    throttle.rs               # per-domain semaphore + last-fetched timestamp
    recipe.rs                 # sparse-overrides recipe loader, normalize()
    frontier.rs               # priority frontier (score + depth tiebreak)
    url.rs                    # canonicalize + classify + score + same_site
    chunk.rs                  # chunker + is_internally_repetitive
    text_extract.rs           # Document → text (pdf_extract → pdftotext fallback)
    language.rs               # Devanagari/Latin/Mixed/MojibakeSuspected classifier
    legacy_import.rs          # Python prototype JSONL → SQLite
    health.rs                 # rolling-window verdict (Phase 6)
    repair.rs                 # react_to_verdict + dispatch_one + dry_run + apply (Phase 6)
    agent.rs                  # AgentRuntime trait + ClaudeCodeAgent (subprocess)
    daemon.rs                 # tick loop, PID lock, SIGTERM, CrawlerTickHandler (Phase 7)
    pool.rs                   # multi-source orchestration with semaphore concurrency cap
    worker.rs                 # per-source crawl loop
    registry.rs               # corpora/sources_tiered.jsonl → SQLite

  bin/
    crawl.rs                  # the daemon CLI: init/status/describe/import-legacy
                              # /index-chunks/poll/repair/daemon
    audit_html.rs, audit_urls.rs   # one-shot debugging tools
    crawler.rs, ingest.rs, build_index.rs, query.rs, ocr_batch.rs,
    validate_converter.rs     # Phase-1..Phase-29 era; mostly historical

corpora/
  sources_tiered.jsonl        # 877 gov sources (canonical registry)
  tier_overrides.jsonl        # manual tier promotions / additions

recipes/                      # sparse JSON overrides on the default crawl policy
  README.md                   # convention guide
  jirimun_gov_np.json         # palika example (all defaults + notes)
  lawcommission_gov_np.json   # PDF-heavy example
  supremecourt_gov_np.json    # trap-prone example with deny_paths

ops/
  np.gemma-god.crawler.plist.template  # launchd plist
  install_daemon.sh                    # builds + substitutes + bootstraps via launchctl
  uninstall_daemon.sh

scripts/
  reddit_ingest.py            # arctic_shift archive → cleaned r/Nepal JSONL
  filter_gov_questions.py     # gov-keyword + interrogative filter
  fast_eval.py                # post-checkpoint eval (Belebele 50 + FLORES 30 + Roman-NE 10)
  nepali_baseline.py          # full baseline (Belebele 200 + FLORES 100)
  apply_tier_overrides.py
  consolidate_gov_corpus.py
  download_hf_corpora.py
  indicxlit_romanize.py       # IndicXlit-based Roman-NE transliteration
  pack_cpt_corpus.py          # tokenize + pack for CPT (Phase-19 era)
  seed_source_registry.py
  crawl_sources.py            # original Python prototype crawler; superseded by crawler_v2

examples/
  debug_canon.rs              # URL canonicalization debugging
  probe_pdf_text.rs           # bucket PDFs by extracted-text quality (rich/thin/empty)

tests/
  crawler_v2_*.rs             # ~24 integration suites; 267 tests passing as of session end
```

---

## What's built, what's not

| Phase | What | Status |
|---|---|---|
| 1 | crawler_v2 core (types, schema, blobs) | ✅ |
| 2 | URL canonicalize + frontier + trap filters | ✅ |
| 3 | fetch + parse + shell-detect | ✅ |
| 3b | chromiumoxide JS-render path | ❌ pending (#39) |
| 4 | recipe loader + default policy | ✅ |
| 5 | per-source worker + admin CLI | ✅ |
| 6 | health evaluator + repair queue + agent dispatcher | ✅ Phase 6.0–6.4 done |
| 7 | scheduled daemon under launchd | ✅ Phase 7.0–7.2 done; **not yet launchctl-loaded for production** |
| 28 | RAG: hybrid retrieval API (BM25 + vec) | ❌ pending |
| 29.1 | chunker + filtering pipeline | ✅ |
| 29.2 | embedder + LanceDB vector store | ❌ pending |
| 31 | r/Nepal gov-question pool | partial — filter exists, classifier not run |
| 32 | groundedness eval set (100 items) | ❌ **prerequisite for SFT iteration** |
| Plan-B CPT | PT model + CPT + SFT 3-stage | ❌ unrun; CPT v1 regressed (see BENCHMARKS.md) |
| SFT pilot | LoRA SFT on Gemma 4 IT, ~1k tuples | ❌ not started; data plan: distill from Sonnet/Kimi |

---

## Production state on k2

Machine: `k2` (Mac Studio, M2 Ultra, 64 GB), Tailscale-accessible via SSH.
External drive: `T9` mounted at `/Volumes/T9`.

```
/Volumes/T9/gemma-god/
  bin/
    crawl                           # release-built crawler binary (Apple Silicon)
    probe_pdf_text                  # debugging probe binary
    pdftotext  → ~/miniconda3/bin/pdftotext  (symlink for the env-var override)
  corpus_v2/
    index.db                        # SQLite, schema v3, 519 MB
    blobs/<source>/<hash[:2]>/      # raw fetched blobs
    extracted/<source>/<hash[:2]>/  # readable-text sidecars
    manifests/                      # legacy Python crawler outputs (already imported)
  corpora/
    reddit_nepali.jsonl             # 101k cleaned r/Nepal records (4,217 with gov_kw=True)
    reddit_gov_questions.jsonl      # 1,898 after question-marker filter
  eval/                             # benchmark JSON + .md reports
    belebele.json
    flores_en2ne.json, flores_ne2en.json
    roman_nepali.json
    fast_eval_cpt_v1_step10000.json
    gemma3_nepali_baseline.md       # the 4B-IT baseline (Belebele 63%, FLORES en→ne 38)
    mlx-community__gemma-4-e4b-it-bf16/   # Gemma 4 baseline reports
  checkpoints/                      # CPT/SFT artifacts; cpt_v1 lives here
  recipes/                          # deployed copy (3 hand-written examples)
```

**SQLite counts** (last verified 2026-04-28):

| Table | Rows |
|---|---|
| `sources` | 877 |
| `documents` | 12,278 (was 11,926 + 352 from Jiri poll) |
| `chunks` | 101,022 (was 99,384 + 1,638 from Jiri index) |
| `poll_cycles` | 1 (Jiri only — daemon not launchctl-loaded yet) |
| `repair_queue` | 0 |
| `source_health` | 877 (populated by one daemon tick) |

**Tools installed userland on k2** (no sudo used):

| Tool | Path | Why |
|---|---|---|
| nvm + Node LTS | `~/.nvm/versions/node/v24.15.0/` | needed for claude-code |
| `claude` (claude-code CLI) | `~/.nvm/versions/node/v24.15.0/bin/claude` | repair-queue agent runtime |
| miniconda3 | `~/miniconda3/` | sudo-free package manager |
| `pdftotext` (Poppler) | `~/miniconda3/bin/pdftotext` | PDF fallback parser; symlinked into `/Volumes/T9/gemma-god/bin/` |

**The `k2` user lacks passwordless sudo.** brew install needs sudo and
bails non-interactively. Use conda for userland installs; otherwise have
the user run sudo commands themselves.

---

## Architectural decisions worth remembering

1. **`Store` is `!Sync`** because rusqlite `Connection` is `!Sync`. Holding
   `&Store` across an `.await` produces a `!Send` future, which breaks
   `tokio::spawn` and the daemon's `Send`-bound `TickHandler` trait. Pattern:
   open `Store` in scoped non-await blocks, drop before `.await`.
   Concretely: `dispatch_one` takes `db_path: &Path`, not `store: &Store`.

2. **Cross-platform shell-out for PDF fallback.** `pdf_extract` (the Rust
   crate) panics on certain Nepal-gov budget/policy PDFs (`adobe-cmap-parser`
   bug). We `catch_unwind` and fall back to `pdftotext` (Poppler).
   Configurable via `PDFTOTEXT_BIN` env var; gracefully no-ops if missing.

3. **Migrations are idempotent.** Every migration uses `IF NOT EXISTS` /
   nullable `ALTER`, so re-applying on a fresh DB (where `SCHEMA_SQL`
   already created the artefacts) is safe.

4. **Recipes are sparse overrides.** Default policy in `recipe.rs::default_for`;
   per-source files only set fields that deviate. Missing recipe is fine.
   `repaired_by` and `last_repaired_at` are stamped by the apply pipeline,
   not by hand.

5. **launchd plist injects env vars** because the daemon's PATH doesn't see
   user installs. `install_daemon.sh` resolves absolute paths for `claude`
   and `pdftotext` and substitutes them into the plist template.

6. **Repair queue dispatcher uses git worktrees**, not the main tree.
   `apply_recipe` does `git worktree add -b repair/<source>-<ts>` so the
   commit lands on a branch in an isolated worktree under
   `<repo_root>/.repair-worktrees/`. Operator merges or deletes at their
   convenience. Main worktree is never touched.

7. **Agent runtime is pluggable.** `AgentRuntime` trait wraps subprocess
   invocation of any agent CLI (claude-code, opencode, codex). Currently
   only `ClaudeCodeAgent` is implemented. Tests use mock implementations
   to avoid real subprocesses.

8. **CPT v1 regressed by a textbook mechanism**, not mysteriously — only
   9.5% of training data was instruction-format, so chat behavior was lost.
   See BENCHMARKS.md §3.2. Plan B (PT base + CPT + SFT) is documented but
   unrun.

9. **Scope is currently Jiri-only** for the demo. Daemon and crawler will
   support all 877 sources, but the demo focuses on `jirimun_gov_np` +
   ~10 federal parents.

---

## Build, test, deploy

```sh
# Local build + run
cargo build --release --bin crawl
cargo test                               # 267 passing as of session end

# Test count by file
cargo test 2>&1 | grep -E "^test result:" | awk '{p+=$4; f+=$6} END {print p, f}'

# Deploy binary to k2 (after build)
scp target/release/crawl k2:/Volumes/T9/gemma-god/bin/crawl

# Run a single Jiri poll on k2 (manual, ad-hoc)
ssh k2 'PDFTOTEXT_BIN=/Volumes/T9/gemma-god/bin/pdftotext \
  /Volumes/T9/gemma-god/bin/crawl \
    --db /Volumes/T9/gemma-god/corpus_v2/index.db \
  poll --source jirimun_gov_np \
    --recipes-dir /Volumes/T9/gemma-god/recipes \
    --out-root /Volumes/T9/gemma-god/corpus_v2'

# Run daemon for N ticks (test mode; production uses --max-ticks 0 = run-until-signal)
ssh k2 '/Volumes/T9/gemma-god/bin/crawl \
    --db /Volumes/T9/gemma-god/corpus_v2/index.db \
  daemon \
    --state-dir /tmp/jiri-daemon-state \
    --max-ticks 1 --tick-interval-sec 5 \
    --health-every-n-ticks 1 ...'
```

---

## Common pitfalls observed this session

1. **All sources are due immediately on a fresh DB.** `next_poll_at IS NULL`
   counts as due. Don't run `crawl daemon` (or `poll --all`) on prod
   without thinking — it'll try to crawl all 877 sources at once. Push
   non-target sources to far-future timestamps first if running an
   isolation test.

2. **Snapshot index.db before destructive operations.** `cp index.db
   index.db.bak` is a 519 MB write — fast on SSD. Always do it before
   migration runs or schema-affecting CLI invocations.

3. **launchd plist PATH does NOT include conda or nvm bins.** Either
   substitute absolute paths via `install_daemon.sh` or extend `PATH`
   in the plist's `EnvironmentVariables`. Both are wired now.

4. **rust-analyzer diagnostics often lag the actual compiler.** Trust
   `cargo check` / `cargo test` over the in-IDE error squiggles.

5. **`pdf_extract` panics produce noisy stderr** even when caught. The
   panic message goes to stderr before `catch_unwind` recovers. Functional
   no-op, but log readers should know the panic lines aren't aborts.

6. **HF datasets brotli decoder error** intermittently when downloading
   benchmarks. Fall back to fetching raw `.jsonl` files from
   `huggingface.co/datasets/<repo>/resolve/main/data/<file>.jsonl` via
   `curl`.

7. **Belebele tests *general* Nepali, not gov-domain.** A high Belebele
   score doesn't mean the model is good at the helpdesk task. See
   BENCHMARKS.md §4 for the eval gaps.

---

## What the SFT pilot should look like

2026-05-14 update: the old final-answer-heavy SFT pilot direction below is
superseded by `SFT_V5_POSTMORTEM_AND_NEXT_PASS.md`.

The 2026-05-13 E4B v5 adapter trained successfully but failed smoke testing.
Future SFT should train resolver/intake, answerability, source selection, and
composer behavior over provided context. It should not train the model to
memorize government facts. Exact contacts, fees, office holders, URLs, and dates
belong in deterministic extraction/source-grounded paths.

(Captured before context-switch; if you're picking this up cold:)

1. **Eval gap first.** Build the groundedness eval set (task #32) before
   running SFT. Without it, you can only measure regression on
   Belebele/FLORES, not improvement on the actual task.
2. **Distill, don't hand-write.** 5–10k `(question, retrieved_chunks,
   teacher_answer)` tuples generated via Sonnet or Kimi K2.6, with the
   teacher prompted to cite chunk URLs. Cost ~$5–15 in API.
3. **Mix three slices**: ~70% task tuples (RAG-grounded answers),
   ~20% Roman-NE handling pairs, ~10% Alpaca-NE for chat preservation.
4. **LoRA, not full FT.** At this data scale full FT overfits. LoRA fits
   on k2 (1–2 h via MLX) or H100 (10–15 min).
5. **Targets**: Roman-NE degen 3/10 → ≤1/10; Belebele within 2 pts of
   baseline (regression check); groundedness eval newly defined target.
6. **Eval after every checkpoint** via `scripts/fast_eval.py`. Dump
   results into `eval/<run_label>.json` and append to the score-history
   table in BENCHMARKS.md.

---

## Open questions to ask the user at session start

- Are we proceeding with the SFT pilot, or building the groundedness eval
  set first?
- Is the demo: Jiri-only, or Jiri + ~10 federal parents?
- Composer for the demo: Sonnet/Kimi via API (no training needed), or
  on-device Gemma 4 (training needed)?
- Should the daemon be loaded into `launchctl` to start auto-running, or
  stay in manual `crawl daemon --max-ticks N` mode?
