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

### Benchmark run (in-progress, kicked off 2026-04-18)

Running `scripts/nepali_baseline.py` on k2. Four benchmarks:
1. **Belebele Nepali** (200 MC, accuracy)
2. **FLORES-200 EN→NE** (100 pairs, chrF++)
3. **FLORES-200 NE→EN** (100 pairs, chrF++)
4. **Roman-Nepali qualitative** (20 hand-crafted gov queries)

Output to `/Volumes/T9/gemma-god/eval/`. Log at `baseline.log`.

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
