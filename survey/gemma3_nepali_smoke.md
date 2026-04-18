# Gemma 3 4B — Nepali smoke test

**Date:** 2026-04-18
**Host:** k2 (Mac Studio M2 Ultra, 64 GB), via `mlx-lm` in `~/.venvs/gemma-god`
**Model:** `mlx-community/gemma-3-4b-it-bf16` (bf16, ~9.3 GB) cached at `/Volumes/T9/hf_cache/`
**Load time:** 263 s (first load from disk), <5 s inference per prompt after load
**Environment:** `HF_HOME=/Volumes/T9/hf_cache`, HF token installed, MLX 0.31.1

## Three-prompt smoke test

### Q1 — Devanagari factual knowledge
**Prompt:** `नेपालको राजधानी के हो? एक वाक्यमा जवाफ दिनुहोस्।` (What is Nepal's capital? Answer in one sentence.)
**Expected:** `नेपालको राजधानी काठमाडौं हो।`
**Got:** `नेपालको राजधानीकाठोका हो।`
**Issues:**
- Misspelled काठमाडौं as काठोका
- Missing space before the city name
- Factually wrong (the word produced is not a real place)

**Score: 1 / 5.** Can't spell Nepal's own capital.

### Q2 — Devanagari gov-domain question
**Prompt:** `म कम्पनी दर्ता गर्न चाहन्छु। मलाई के के लाग्छ? संक्षेपमा भन्नुहोस्।` (I want to register a company. What do I need? Answer briefly.)
**Got:** Multi-point bulleted answer about company registration requirements.
**Issues:**
- Structurally reasonable and grammatically plausible
- Contains `Партнер्सhips` (Cyrillic-Latin-Devanagari hybrid; pretraining-data bleed)
- Uses `पंजीकरण` (Hindi register form) instead of the Nepali `दर्ता`
- Uses `सामाग्री` (wrong word) where Memorandum of Association is meant
- Output was truncated at max_tokens=200 mid-sentence

**Score: 2.5 / 5.** Fluent-sounding but semantically drifting Nepali; vocabulary is borrowed wrong from Hindi.

### Q3 — Romanized Nepali
**Prompt:** `mero nagarikta banauna ko lagi kun office janu parcha?` (For making my citizenship, which office do I go to?)
**Got:** Degenerates into `"Tikai JSS janu parcha."` repeated 5 times. Invents an agency `Janakalyan Samiti (JSS)`.
**Issues:**
- Catastrophic repetition loop
- Hallucinated agency
- Doesn't identify the correct answer (CDO office / जिल्ला प्रशासन कार्यालय)
- Doesn't understand Romanized Nepali as a language variant

**Score: 0.5 / 5.** Fails catastrophically on Romanized input.

## Verdict

**Composite: ~1.3 / 5.** Well below the 2.5 threshold agreed on for the SFT-only path. We're in CPT territory.

## Implication for the plan

Base Gemma 3 4B in bf16, with no adaptation, is NOT viable for a Nepali gov helpdesk:
- Cannot reliably produce correct Nepali vocabulary
- Cannot spell canonical proper nouns (Kathmandu)
- Cannot handle Romanized Nepali at all
- Code-mixed (Q2) shows pretraining bleed from other languages

**CPT is required.** But naive CPT on Nepali-only data causes catastrophic forgetting of English/reasoning capability (arxiv 2412.13860, MMLU 0.61 → 0.35). So CPT must be:
- **Bilingual next-token objective** (alternating English + Nepali sentences) per SarvamAI's findings
- **Replay buffer** with ~20% English general-domain data interleaved
- **Small LoRA rank** (16–32) with frozen base, not full fine-tune
- **Include Romanized Nepali** and code-mixed examples in training mix (arxiv 2604.14171 methodology — Qwen3-8B showed base PPL 27.9 → 2.95 after this treatment)

## Next steps

1. **Run the full benchmark baseline** (Belebele Nepali, mlm-eval MMLU Nepali, FLORES-200, custom 40-Q) to get *numeric* scores to beat after CPT. Without numbers we can't tell whether CPT helped.
2. **Prepare CPT corpus** (trilingual: Devanagari + Romanized + English + code-mixed):
   - IRIISNEPAL 27.5 GB Nepali news (Devanagari)
   - Our converted gov corpus (BPreeti + OCR)
   - Saugatkafley/alpaca-nepali-sft (52k Devanagari instructions) + IndicXlit-transliterated Roman variant
   - NepEMO Reddit posts (real code-mixed samples)
   - English replay data (e.g., a sample of OpenOrca or Dolma-en)
3. **Fine-tune compute plan** — MLX LoRA on k2 should work for 4B + small rank. Time estimate: 8–16 hours depending on token budget.
4. **Evaluation after CPT** on the same baseline to measure uplift.

## Also noted during setup

- LM Studio IS installed on k2 under `khatradev` admin account (`~/khatradev/.lmstudio/`, with mlx-llm-mac-arm64 backend). Could be used if we want a GUI browse-and-compare workflow, but headless `mlx_lm.server` under k2 is what we're standardizing on.
- APFS reformat of T9 succeeded; symlinks work (critical for HF Hub cache structure).
- `cdjk@100.117.21.47` HF token installed to `~/.cache/huggingface/token` and `$HF_HOME/token` on k2, `HF_TOKEN` persisted in `~/.zshrc`.
- 263 s cold load time for bf16 Gemma 3 4B — acceptable for long-running server process, not interactive per-query.
