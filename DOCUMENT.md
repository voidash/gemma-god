# gemma-god — Engineering Log

A chronological record of decisions, findings, and non-obvious technical reality.
New entries at the bottom. Complements `PLAN.md` (forward-looking) and
`survey/observations.md` (domain survey).

---

## 2026-04-18 — Day 1

### Project framing (from conversation)

Goal: A Nepali government-knowledge question-answering engine for citizens,
built for the Gemma hackathon (~1 month horizon). **Not** a chatbot on top of
RAG. A *knowledge engine* with four properties:

1. **Page-level provenance** — every answer cites `(doc, page, verbatim snippet,
   `link#page=N`)`. Page + snippet is the granularity; character-bbox tracking is
   out of scope.
2. **Conversational understanding** — the engine asks clarifying questions
   instead of guessing when the query is vague. Retrieval is downstream of
   understanding, not the whole story.
3. **Closed-loop knowledge growth** — when corpus lacks coverage, an AI agent
   can be dispatched to WhatsApp / email / voice the relevant gov contact
   person. Human reviewer approves before acquired facts enter canonical corpus.
4. **Trust-aware ingestion** — every fact tagged by provenance (`scraped` /
   `converted` / `ocr` / `human-verified` / `agent-acquired`) with confidence
   score.

Full architecture plan: see `PLAN.md`.

### Phases 1-F (corpus pipeline, shipped 2026-04-18)

- **Phase 1** — gov-site survey (15 sites): 10 live, 4 broken-TLS,
  1 dead (`nepal.gov.np` itself, ironic). Shared CDN at
  `giwmscdnone.gov.np`. All findings in `survey/sites.yaml`,
  `survey/observations.md`.
- **Phase A (classifier)** — `src/detector.rs`. Classifies each PDF into
  A / BPreeti / BLegacyUnknown / C / E / Mixed / XInvalid by tier. 9 ground-
  truth integration tests green.
- **Phase B (Preeti converter)** — `src/legacy_fonts.rs`. Port of GPL-3.0
  `casualsnek/npttf2utf` mapping. 13/13 BPreeti docs produce legible Nepali.
  Critical finding: raw Devanagari ratio is misleading — `nepali_word_hits()`
  (count of known high-frequency Nepali words) is the real success signal.
- **Phase C (mixed-doc)** — `convert_mixed()` adds token-level classification
  so English + already-Unicode sections are preserved. Per-segment post-rules
  (not global) prevent corruption of English via rule 4/7 interactions.
- **Phase D (OCR)** — `src/ocr.rs`. Tesseract + nep traineddata from
  `tessdata_best` (12 MB). 5/5 Tier C PDFs OCR'd; 65 125 Devanagari chars
  unlocked from previously-unreadable docs.
- **Phase E (crawler)** — `src/crawler.rs`. TLS-tolerant fetch via curl `-k`,
  regex-based PDF-link extraction. 65 new PDFs discovered from 22 seed index
  pages; 3 dead URLs flagged on HEAD revalidation.
- **Phase F (RAG retrieval)** — per-chunk ingestion + BM25 index. 46 026 chunks,
  212 161 unique terms, 57 MB index, sub-second query. End-to-end validated:
  `"company registration"` → OCR (Office of Company Registrar) manuals with
  source URLs; `"आर्थिक वर्ष"` → NRB Preeti-converted circulars.

### Plan revision after feedback

The user pushed back on my initial "hackathon demo" framing. Actual goal is a
proper engine, not a 4-week prototype. Revised scope:
- page+snippet citation fidelity (not character bboxes)
- conversational understanding (LLM asks clarifying Q's when vague)
- real-time knowledge acquisition via AI agents (NOT autonomous — human-
  approved ingestion only)
- bilingual CPT including Romanized Nepali (not pure-Devanagari)

### Research: Nepali benchmarks

Earlier framing ("Nepali benchmarks are sparse") was wrong. Actual landscape:
- **NLUE** (arxiv 2411.19244, Nov 2024) — 12 NLU datasets, classification/NLI.
- **NepaliGPT benchmark** (arxiv 2506.16399, Jun 2025) — 4 296 Nepali QA pairs,
  perplexity + ROUGE + causal-coherence metrics.
- **Belebele Nepali** (Meta) — 900 MC reading-comprehension Qs.
- **Global-MMLU** (arxiv 2412.03304) — 42 languages incl. Nepali, cultural-
  sensitivity splits.
- **MLMM-evaluation** (nlp-uoregon) — 26 langs incl. Nepali for ARC / MMLU /
  HellaSwag translated.
- **FLORES-200** — standard EN↔NE translation eval.
- **Aya / Bactrian-X** — multilingual instruction-tuning with Nepali subset.
- **Saugatkafley/alpaca-nepali-sft** — 52k Devanagari instruction pairs, public.
- **IRIISNEPAL corpus** (arxiv 2411.15734) — 27.5 GB Nepali news (largest
  pretraining corpus).

Critical warning from **arxiv 2412.13860** — naive Nepali CPT on Llama 3 8B
dropped MMLU from 0.61 to 0.35. Catastrophic forgetting is real. Mitigations:
bilingual next-token objective, 20% English replay buffer, small LoRA rank
(16–32).

Romanized Nepali landscape (specifically):
- **arxiv 2604.14171** — Llama/Mistral/Qwen3 on Romanized Nepali, with train
  set built via IndicXlit transliteration of `Saugatkafley/alpaca-nepali-sft`.
  Qwen3-8B best post-fine-tune: base PPL 27.9 → 2.95, BERTScore 0.56 → 0.75.
- **IndicXlit** (AI4Bharat) — 11M-param multilingual transliteration model.
  `pip install ai4bharat-transliteration`. Permits orthographic variation
  (chha/cha/chaa), matching real user typing.
- **NepEMO** (arxiv 2512.22823) — 4 462 Reddit posts Jan 2019–Jun 2025, 961
  explicitly code-mixed (Eng + Devanagari Nepali + Roman-Nepali).

### Gemma 3 4B smoke test on Nepali — harsh verdict

Ran `mlx-community/gemma-3-4b-it-bf16` via mlx-lm on k2 with 3 prompts.
Details in `survey/gemma3_nepali_smoke.md`. Composite ~1.3 / 5:
- `नेपालको राजधानी के हो?` → `काठोका` (misspelled Kathmandu as `काठोका`
  instead of `काठमाडौं`). Factually wrong.
- Company registration Devanagari → understandable but mixed-script leakage
  (`Партнерships`), Hindi vocabulary leaking (`पंजीकरण` vs Nepali `दर्ता`).
- `mero nagarikta banauna...` (Roman) → catastrophic repetition loop,
  hallucinated agency ("Janakalyan Samiti").

**Verdict: CPT required, bilingual + replay-buffer recipe per the literature.**
No naive Nepali-only CPT.

### Infrastructure (k2 Mac Studio)

- Accessed via Tailscale: `ssh k2` (alias in `~/.ssh/config`, key-auth).
- M2 Ultra, 64 GB RAM, macOS 14.6, APFS internal.
- External 2 TB Samsung T9 SSD — was exFAT, reformatted to APFS via
  backup → diskutil eraseDisk → restore, round-trip SHA-256 verified on
  1 647 files. Preserved ~785 MB of existing Gaussian 16 (`g16_main`) data.
- LMStudio IS installed under admin user `khatradev`. We're using
  `mlx_lm.server` under `k2` for headless consistency.
- Homebrew owned by `mukesh:admin` (pre-existing).
- Stack on k2:
  - Python 3.11.15 (brew), uv 0.11.7 (standalone installer at
    `~/.local/bin/uv`)
  - venv at `~/.venvs/gemma-god/` with mlx 0.31.1, mlx-lm, huggingface_hub,
    sacrebleu, datasets
  - HF cache at `/Volumes/T9/hf_cache/` (9.3 GB incl. Gemma 3 4B bf16)
  - HF token in `~/.cache/huggingface/token` and `/Volumes/T9/hf_cache/token`,
    `HF_TOKEN` env var in `~/.zshrc`
  - Non-interactive SSH doesn't source `.zshrc`; must explicitly
    `export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"` at start of
    remote commands.

### Benchmark run (partial, 2026-04-18)

Running `scripts/nepali_baseline.py` on k2. Four benchmarks planned; partial
results:

1. **Belebele Nepali — 200 MC: accuracy 0.630** ✅ (done in 81 s)
2. **FLORES-200 EN→NE — blocked.** `openlanguagedata/flores_plus` is gated on
   HF Hub; `facebook/flores` fallback also failed. Need to swap mirror or
   request access. Not a blocker for the main conclusion.
3. **FLORES-200 NE→EN — same as above.**
4. **Roman-Nepali qualitative — in progress** (20 hand-crafted gov queries).

Output to `/Volumes/T9/gemma-god/eval/`. Log at `baseline.log`.

### Key mid-run insight: comprehension ≠ generation

The **0.630 Belebele score diverges sharply from the smoke-test verdict**. The
smoke test measured generation (all three prompts were free-form Nepali output)
and failed hard — misspelling Kathmandu, collapsing on Romanized input,
mixed-script leakage. Belebele measures comprehension (read passage in Nepali,
pick A/B/C/D) and the same model scored 2.5× random-baseline (25% → 63%).

This bifurcates the CPT plan:

- **Comprehension is adequate.** Don't teach it from scratch. CPT recipe must
  at minimum *preserve* the 0.63.
- **Generation is the weak axis.** CPT should emphasize language-modeling loss
  on Nepali output text.
- **Implication for forgetting risk.** Targeted generation-side CPT poses
  lower risk to English reasoning than wholesale bilingual pretraining,
  because we're not trying to rebuild the comprehension stack.

This tracks with known LLM behavior: models generally understand a language
better than they can generate it, especially for low-resource languages where
pretraining data is thin. Gemma 3's multilingual training gave it reading
ability; fluent generation is the next step.

### Final baseline numbers (2026-04-18)

| Benchmark | n | Metric | Score | Time |
|---|---|---|---|---|
| Belebele Nepali (`npi_Deva`) | 200 | MC accuracy | **0.630** | 81 s |
| Roman-Nepali qualitative | 20 | manual review | ~75% usable | 66 s |
| FLORES-200 EN↔NE | — | chrF++ | **blocked** | — |

Model load (cold): 169 s. Raw artifacts in `survey/eval/` (gitignored).

### Roman-Nepali observations

Out of 20 hand-crafted gov-domain Roman-Nepali queries:

- ~4/20 fully degenerate (repetition loops, hallucinated nonexistent agencies)
- 1/20 switched to Indonesian/Malay entirely — language-confusion artifact
- ~15/20 produced *some* useful content; most of these code-switched to
  Devanagari Nepali output even though input was Romanized. The model appears
  to treat Romanized Nepali input as a signal to respond in Devanagari, which
  is a useful accidental prior — but its Devanagari output is still often
  wrong on specifics (wrong ministry, wrong process name, etc.)

Examples:
- `passport renew garna kaha janu parcha?` → response lists "गृह विभाग"
  (Home Dept) but the correct answer is "राहदानी विभाग" (Dept of Passport).
  Right structure, wrong agency.
- `company registration kasari garne?` → coherent 3-stage Devanagari answer,
  roughly correct in broad strokes.

### FLORES resolved + final numbers

Initial run failed: `openlanguagedata/flores_plus` is gated, and the `datasets`
library doesn't reliably honor `HF_TOKEN` for gate checks (tested on `datasets`
4.8.4 — upgrade didn't help). `facebook/flores` also fails with "Dataset
scripts are no longer supported" error (HF refuses to execute old loading
scripts).

**Resolution:** bypass the `datasets` library entirely. `hf_hub_download`
respects `HF_TOKEN` correctly. Fetch `dev/eng_Latn.jsonl` and `dev/npi_Deva.jsonl`
directly (they're line-aligned, one sentence per line in each language).

**HF account mistake to not repeat.** There were TWO HF accounts at play:
- `trishuli` (email `thapa_aashish@proton.me`) — token `hf_YCp...` was found on
  cdjk@100.117.21.47 at `~/.cache/huggingface/token`. This token does NOT have
  access to flores_plus.
- `voidash` (no email set) — token `hf_CvO...` at
  cdjk@100.117.21.47 `~/.ssh/.env_tokens`. This is the account that accepted
  the flores_plus gate. Use this for any gated-dataset work.

The k2 HF token was updated to `hf_CvO...` (voidash) in ~/.cache/huggingface/token,
/Volumes/T9/hf_cache/token, and ~/.zshrc.

### Final FLORES numbers

| Direction | chrF++ | BLEU |
|---|---|---|
| EN → NE (generation)           | **38.15** | 6.94  |
| NE → EN (comprehension→English) | **55.88** | 28.79 |

### Complete baseline picture for Gemma 3 4B on Nepali

| Axis | Benchmark | Score | Read |
|---|---|---|---|
| Comprehension (MC) | Belebele NE 200-Q | **0.630 acc** | usable |
| Comprehension (translate to English) | FLORES NE→EN 100 pairs | **55.88 chrF++** | usable |
| Generation (translate from English) | FLORES EN→NE 100 pairs | **38.15 chrF++** | weak |
| Generation (free-form NE) | Smoke + Roman qualitative | ~1.3/5 smoke, ~75% Roman-usable | fails in domain |

The split is stark: ~0.630 accuracy + 55.88 chrF++ going Nepali-in, English-out
vs 38.15 chrF++ the other way. Comprehension is usable; generation is what
needs fixing. For context, dedicated MT models (NLLB-200) hit En→Ne chrF++ in
the 50s; Gemma 3 4B at 38 is reasonable for a generalist LLM but short of
translation-specialist quality.

### CPT targets (numbers to beat after training)

- Belebele ≥ 0.60 — preserve comprehension
- NE → EN chrF++ ≥ 55 — preserve translate-to-English pipeline
- EN → NE chrF++ ≥ 45 — meaningful lift on generation (~18% relative)
- Roman-Nepali qualitative: catastrophic failures from ~25% → <10%
- No regression on base-model English MMLU (mitigate catastrophic forgetting
  via 20% English replay + bilingual next-token objective + small LoRA rank)

### Decision on LLM-based distillation (Gemini): skipped entirely for now

Considered using Gemini 2.5 Flash for paraphrase augmentation (CPT) or
SFT-example generation. After discussion, dropped both for now:
- Paraphrase adds zero net-new information — just surface variation of the
  same meaning. Training-budget is better spent on natural-distribution text.
- SFT data generation could still benefit from LLM distillation later, but
  we're not there yet — first we need CPT to fix base-model Nepali, then
  decide SFT recipe from results.

Revisit when we plan the SFT phase.

### Corpus assembly plan (small-tier ~80 M tokens)

| Slice | % | Source |
|---|---|---|
| Gov Devanagari | 25% | `survey/corpus_chunks.jsonl` (tiers A + BPreeti-converted + Mixed + C-OCR) |
| Wikipedia Nepali | 20% | HF `wikipedia:20240301.ne` |
| Reddit Roman-NE | 20% | /r/Nepal 10-yr archive filtered |
| Reddit code-mixed + NepEMO | 10% | same + HF download |
| IndicXlit synthetic Roman | 5% | Deterministic transliteration of gov/Wiki subset |
| English replay | 20% | fineweb-edu sample |

Natural text only. No LLM distillation in CPT mix.

### Reddit r/Nepal ingest — done 2026-04-18

`scripts/reddit_ingest.py` streaming decode + filter + dedup pass over 73
`.zst` JSONL archive files (arctic_shift format, `{kind, raw}` wrap) from
`/Users/cdjk/github/llm/new-place/data/raw/`.

| Metric | Count |
|---|---|
| Records seen | 6,869,085 |
| Non-empty bodies | 4,933,617 |
| Deleted/removed | 461,808 |
| Bot authors | 161,451 |
| Too short (<30 ch) | 1,384,067 |
| Too long (>8000 ch) | 413 |
| English (skipped) | 4,631,923 |
| Duplicates | 126,710 |
| **Kept** | **101,790** |

Language split of kept records:
- Roman-Nepali: 68,099
- Devanagari: 23,868
- Code-mixed: 9,823
- By kind: 80,892 comments + 20,898 submissions
- Gov-keyword pre-flagged: 4,217 (4.1% of kept)

Output: `corpora/reddit_nepali.jsonl`, 52.5 MB. Elapsed: 332 s. Rough token
estimate: ~12–15 M tokens (close to the 16 M target for the Reddit slice).

**Classifier fix learned the hard way:** first pass used loose substring
matching on short Roman-NE markers (`ma`, `ta`, `yo`), which false-positived
on English words containing those letters (`mister`, `mistakes`, `you`) —
4,748 out of 5,000 test-mode "Roman-NE" were actually English. Fixed with
word-bounded regex match + tightened marker list (all ≥ 4 chars) + require
`ne_hits >= 3 AND ne_hits > eng_hits`. Re-validated on 5k sample — all three
classes show genuine-looking examples.

**Author-field gotcha:** some arctic_shift records have `raw.author` as a
dict (richer profile object) rather than a string. Guard with
`isinstance(raw_author, str)` before the bot-author set membership test —
otherwise TypeError on `dict in frozenset(str)`.

### Decision for CPT based on this baseline

- **Target: preserve Belebele ≥ 0.60** (comprehension) while meaningfully
  improving generation quality (measured by a post-CPT smoke test + follow-up
  qualitative eval).
- **Corpus emphasis:** Nepali output text (IRIISNEPAL news, gov prose, our
  Preeti-converted corpus) with ~20% English replay.
- **Include Romanized Nepali** via IndicXlit transliteration of
  Saugatkafley/alpaca-nepali-sft to fix the Roman-collapse pattern.
- **Small LoRA rank** (16–32) on Gemma 3 4B; bilingual next-token objective.
- **Training volume:** start with ~100M tokens. Full CPT run estimate 6–12 hrs
  on M2 Ultra via MLX.

### Decision forks resolved today

- ✅ Use `mlx_lm.server` over LMStudio (admin permissions + headless fit)
- ✅ CPT required (smoke test damning)
- ✅ CPT must include Romanized Nepali + code-mixed (user keyboard reality)
- ✅ Run numeric baseline before designing CPT recipe
- ⏳ CPT model size (4B vs 12B) — decide after baseline numbers
- ⏳ Exact corpus mix for CPT — plan when baseline completes

### Session credentials (redacted)

Several credentials were shared during session setup for remote-machine access
and API tokens. Values are NOT recorded here and were never written to any
git-tracked file. Key auth is now established for the dev boxes; credentials
should be rotated at session end as standard hygiene.
