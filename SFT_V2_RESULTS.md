# SFT v2 — results & learnings

*Snapshot: 2026-04-29. Companion to STATE.md (project overview) and the v1 results writeup at `~/.claude/projects/.../memory/project_sft_v1_results.md`.*

---

## TL;DR

SFT v2 was the first iteration after v1 surfaced two clear gaps: **the model couldn't refuse (0/91)** and **Roman-Nepali prompts degenerated** (2/10). v2 added four new training slices to address those gaps + preserve general capability:

- **refusal slice** (1,100 items, 11% of mix) — fixes 0/91 refusal
- **translation slice** (500 FLORES pairs) — addresses chrF regression
- **MC short-answer slice** (443 items) — teaches terse output format
- **brief Q&A slice** (300 items, biased Roman-NE) — fixes Roman-NE degen

Trained on **Gemma 4 E2B-IT** (cheaper iteration than v1's E4B), 11,896 records total, 2 epochs.

| metric | v1 E4B | v2 E2B | Δ |
|---|---|---|---|
| URL recall (grounded) | 0.89 | **0.89** | 0 (held) |
| wrongly_refused | 0% | 2.7% | +2.7pt (minor side-effect) |
| **refusal_correct** | **0/91 (0%)** | **12/91 (13.2%)** | **+13.2pt** ✓ |
| Roman-NE degen | 2/10 | **0/10** | **−2** ✓ FIXED |
| GSM8K-en | 50% | **60%** | **+10pt** ✓ |
| Belebele | 60% | 54% | −6pt |
| chrF (grounded) | 22.09 | 13.42 | −8.67 |
| LLM judge correct% | 80% (n=5) | 16% (n=50) | larger n = more reliable |

**Reading**: 3 wins (refusal mechanism works, Roman-NE fixed, English replay better), 2 misses (refusal short of 90% target — slice underweight; chrF regression worsened). Adapter is publishable, but v3 is needed to reach the demoability threshold.

Public adapter: https://huggingface.co/voidash/gemma-helpdesk-v2-e2b-seed42

---

## 1. Why v2 — the v1 critique that drove the design

v1 left us with three independent problems, each rooted in a missing slice in the SFT mix:

| problem (v1 eval) | root cause | v2 fix |
|---|---|---|
| 0/91 on refusal items | training mix had ZERO refusal examples — every record was "given chunks, write a grounded answer" | 1,100 refusal items in 3 categories × 3 languages |
| 2/10 Roman-NE degeneration | 989 Roman-NE items existed but all came with chunks — model never saw bare Roman-NE conversational prompts | 300 brief Roman-NE Q&A items (no chunks) |
| ~11pt drop on Belebele/INCLUDE/FLORES | model over-trained on "verbose grounded answer" output style; produces full sentences when MC tasks expect a single letter, paraphrases when FLORES expects a translation | translation slice (500), MC short-answer slice (443) |

The deeper diagnosis from v1 (see `STATE.md` §8 for the rescored numbers):
- ~3-5pt of the Belebele/INCLUDE drop was **eval extraction artifact** (SFT writes the option's text, not the letter)
- ~5-8pt was real wrong-pick regression
- the FLORES drop was mostly paraphrase drift, not real translation capability loss
- + a tokenizer artifact: model emits trailing `-----` padding when it should emit EOS

v2 targeted the data-side fixes for the regression. The eval-extraction + EOS issues are still open for v3.

---

## 2. Data composition

### v2 mix (11,896 records, 95/5 stratified train/val)

| slice | records | source | system prompt? |
|---|---|---|---|
| reverse_instruction (grounded) | 6,553 | DeepSeek V4-Flash, reverse-instruction from gov.np chunks (v1 carryover) | yes (SYSTEM_GROUNDED) |
| native_ne_alpaca | 1,500 | Saugatkafley/alpaca-nepali-sft (v1 carryover) | no |
| english_replay | 1,500 | TULU 3 SFT mixture filtered (v1 carryover) | no |
| **refusal_distilled** | **1,100** | DeepSeek-generated, 60% empty / 25% partial / 15% off-domain | yes |
| **translation_distilled** | **500** | FLORES-200 dev, NE↔EN aligned pairs | no |
| **mc_distilled** | **443** | DeepSeek-synthesized A/B/C/D trivia in 3 langs | no |
| **brief_qa_distilled** | **300** | DeepSeek-generated, 50% Roman-NE biased | no |

Per-language balance: refusal slice 40% Devanagari / 30% Roman-NE / 30% English; brief_qa 50% Roman-NE / 25% Devanagari / 25% English; MC ~33/33/33; translation 50% NE→EN / 50% EN→NE.

### Generators (cost ≈ $3 of DeepSeek)

- `scripts/generate_refusals.py` — 246 DeepSeek calls, 330s wallclock
- `scripts/extract_flores_pairs.py` — no API, deterministic from FLORES dev (excluded the 30 indices used by `nepali_capability_eval.py` to prevent leakage)
- `scripts/synthesize_mc.py` — 114 DeepSeek calls, 129s wallclock; 443/500 kept after dedup
- `scripts/synthesize_brief_qa.py` — 67 DeepSeek calls, 79s wallclock

All four have the same shape: DeepSeek with `thinking: {type: disabled}` (the V4 series defaults to thinking-on, eats token budget), n_per_call=10, validation regex per language, dedup by question hash.

### Decisions worth noting

- **Why E2B not E4B?** Faster iteration (~1.5h vs 2.5h training, ~6sec/step vs 9sec/step). Plus E2B is the realistic deployment target (Pi 5, mini PC) — E4B is too big for the on-device story.
- **Why epochs=2 not 5?** v1 showed val loss bottoms at epoch ~1 (step 500 of ~568/epoch). Past epoch 2, model overfits. We'd waste compute.
- **Why DeepSeek V4-Flash, not Sonnet/Kimi?** Cost. V4-Flash is ~10× cheaper than Sonnet for generator output where quality is "good enough" rather than "must be perfect."
- **Why thinking-disabled?** V4 series with thinking-on consumes the max_tokens budget on internal reasoning, returning empty content for our generation task. Burned this lesson hard in v1; remembered it for v2 generators; FORGOT it for the eval LLM-judge backend → 49/50 empty bodies on first eval pass (fixed via re-run).

---

## 3. Training trajectory

### Setup

| | |
|---|---|
| Base | google/gemma-4-E2B-it |
| Method | LoRA via PEFT, rsLoRA scaling (paper-grounded: Kalajdzievski 2023) |
| r / α | 64 / 128 |
| Targets | q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj |
| Trainable | (~similar 2% as v1, ~80M for E2B) |
| Optimizer | AdamW 8-bit |
| Schedule | LR 1e-4, cosine + 100-step linear warmup |
| Effective batch | 16 (per-device 2 × grad-accum 8) |
| Memory tricks | bf16 + gradient checkpointing + `expandable_segments:True` |
| Hardware | 1× NVIDIA L40S (g6e.xlarge) |
| Best step | 600 (val 0.848) |
| Wall time | ~2h training + ~3h eval = ~5h instance time |

### Per-slice loss progression

The clearest evidence v2 was teaching the right things — slices that started highest dropped fastest:

| slice | initial (step 0) | final (step ~1000 abort) | Δ |
|---|---|---|---|
| reverse_instruction (grounded) | 1.19 | 0.50 | −0.69 (held v1 task quality) |
| **refusal_distilled** | 5.69 | **0.43** | **−5.26** 🎯 (model learning to refuse) |
| **mc_distilled** | 7.75 | **0.27** | **−7.48** 🎯 (terse MC format learned) |
| translation_distilled | 3.50 | 1.31 | −2.19 |
| brief_qa_distilled | 5.06 | 2.37 | −2.69 |
| native_ne_alpaca | 4.81 | 1.65 | −3.15 |
| english_replay | 5.32 | 1.70 | −3.62 |

The two "🎯" slices show the slice mechanism works — for the things v1 couldn't do at all (refuse, write a single letter), v2 drove training loss to near-zero.

### Val history

| step | val loss | notes |
|---|---|---|
| 0 | 2.952 | initial baseline (higher than v1's 1.62 because v2 has the harder slices) |
| 200 | 0.907 | first eval, post-warmup |
| 400 | 0.898 | continued descent |
| **500** | **0.887** | new best, pushed |
| **600** | **0.848** | new best, this is what got eval'd |
| 800 | 0.869 | starting to creep up — overfitting region |

The premature step-1000 abort (see §6) actually saved us from more overfitting.

---

## 4. Eval results

### Full Gold (167 items)

```
grounded n=73:  chrF 13.42  url_recall 0.89  wrongly_refused 2 (2.7%)
refusal  n=91:  correct 12/91 (13.2%)  hallucinated 79
```

### LLM-as-judge (DeepSeek V4-Flash, n=50, thinking:disabled)

```
groundedness:           3.12 / 5
citation_correctness:   4.70 / 5   ← model cites well
helpfulness:            2.98 / 5
verdicts: 8 CORRECT / 35 PARTIAL / 7 INCORRECT  (16% correct)
```

The high citation_correctness (4.70/5) confirms the URL-recall metric: when the model produces an answer, it cites the right URLs. The middling helpfulness (2.98) reflects that answers are *partially* correct but rarely complete enough to be marked CORRECT.

### Regression checks

| benchmark | v2 E2B | v1 E4B | reading |
|---|---|---|---|
| Belebele (n=50) | 54.0% | 60% (n=50) | -6pt; mc_distilled didn't fully prevent over-elaboration |
| GSM8K-en (n=30) | 60.0% | 50% | +10pt; English replay even more effective on E2B |
| Roman-NE degen (n=10) | **0/10** | 2/10 | **fixed** — brief_qa slice worked |

### Side-by-side vs Sonnet baseline

Skipped — `eval/reports/sonnet-4-6-baseline.json` wasn't on the v2 instance. Will run separately if needed.

---

## 5. Honest reading

### What worked

1. **Refusal slice teaches.** From 0/91 to 12/91 isn't the target but it's *provable signal* that the refusal mechanism transfers from training to inference. With ~25-30% slice instead of 11%, v3 should hit higher.
2. **Roman-NE degen FIXED.** Brief Q&A slice did exactly what it was supposed to do. Cleanest win of v2.
3. **English replay over-delivered.** GSM8K +10pt vs v1, despite v2's mix being more diverse (less English share). The model retained / improved English math capability.
4. **URL recall held at 0.89.** Adding 4 new slices didn't damage the v1 task quality.
5. **Citation correctness 4.70/5 from judge.** When the model writes answers, the URLs are right.

### What didn't

1. **Refusal at 13% << 90% target.** 1,100 items wasn't enough to overcome the 6,553-item grounded slice's "always answer" prior. The model learned the refusal *format* (low loss on the slice) but doesn't apply the *decision* often enough at inference. Two paths for v3:
   - Increase refusal slice to 25-30% (cheaper)
   - Reduce grounded slice + reweight (more aggressive)
2. **chrF dropped further** (22→13.4). v2 model is *more* verbose than v1, not less, even with the brief_qa slice. The signal: training on multiple slices made the model "talk more" overall. Need a "be concise" instruction tag or shorter targets for v3.
3. **Belebele worsened slightly** (-6pt vs v1's -11.7pt unfixed; eval-fixed v1 was -8.4pt). MC slice helped some but not enough.
4. **wrongly_refused went 0%→2.7%.** Side-effect of teaching refusal — model now refuses on 2 grounded items it shouldn't. Acceptable trade-off; will re-tune in v3.
5. **Helpfulness 2.98/5 from judge.** Model produces partial answers — citation right, content present, but missing the "fully correct" mark. Suggests some content drift from the gold style.

### What we *can't* tell yet

- **E2B vs E4B comparison apples-to-apples.** v2 was on E2B; v1 was on E4B. Without running v2 on E4B (or v1 on E2B), we can't isolate "did E2B-vs-E4B base change the result?" from "did v2-vs-v1 data change the result?" For v3, run on the same base across iterations.
- **General Nepali capability vs base E2B.** We didn't run `nepali_capability_eval.py` on v2 yet. The v1 capability bench cost ~$1 — would do for v2 too if user wants.
- **Real-world UX.** Eval items are constructed; real citizen prompts differ. No A/B against Hello Sarkar 1111.

---

## 6. Hard-won bugs in this run

Three new ones (the others from v1 didn't recur thanks to the v1 fixes):

### 6.1 step-1000 mini-gen gate STILL buggy — caused premature abort at step 1000

The same `prompt_msgs_text` reconstruction bug that killed v1 fired again — produced empty `'generation error: '` strings, hit the abort threshold of 4-of-5, training stopped. Per-slice losses had already pulled refusal/MC down to near-zero by then; the best checkpoint at step 600 was already saved. So practical impact: small. But I should have removed/fixed this gate before v2.

**Fix for v3**: rip out the step-1000 mini-gen gate entirely. Val loss + per-slice tracking already catches divergence; the gate has never produced a useful signal.

### 6.2 LLM judge backend didn't pass `thinking: {type: disabled}`

DeepSeek V4-Flash defaults to thinking-on. With max_tokens=400 for the judge call, all the budget went to internal thinking, content body returned empty. 49/50 calls flagged as parse_fail. Fixed by patching `eval_groundedness.py`'s `AnthropicShapeBackend` to pass `thinking: {type: disabled}` and re-running the judge step (~$0.05, ~2 min).

**Fix for v3**: bake thinking-disabled into the AnthropicShapeBackend by default. Already in the generator scripts; just propagate to the backend used by eval.

### 6.3 Eval throughput on SFT model is poor (~65 sec/item vs v1's 25 sec/item)

v2 model produces ~2× more output tokens than v1 (model is more verbose), and we run greedy single-batch decode at max_new_tokens=800 default. GPU was at 24% util — single-batch autoregressive decoding doesn't saturate the L40S. Cost: ~$3 extra eval time vs v1.

**Fix for v3**:
- Drop default max_new_tokens for full_gold to 500
- Add batched generation in `HFTransformersBackend.chat()` — accept a list, return a list, use `tokenizer.padding_side='left'` + attention mask
- Or migrate eval to vLLM (proper continuous batching, ~5× faster on the same hardware)

---

## 7. Cost breakdown

| activity | spend | note |
|---|---|---|
| v1 carryover (failed runs) | ~$0.50 | huggingface-cli + Gemma4ClippableLinear bugs |
| v1 actual training + eval | ~$13 | E4B 2.5h training + 1.5h eval |
| v2 data generation (DeepSeek) | ~$3 | 4 generators, 467 calls total |
| v2 training (E2B) | ~$3 | 2h on g6e.xlarge |
| v2 eval | ~$5 | 3h on g6e.xlarge — slow per-item |
| Nepali capability bench (v1) | ~$1 | 30 min E4B + 10 min E2B base |
| LLM judge re-run (v2) | $0.05 | 50 DeepSeek calls + 2 min instance time |
| **Total to date** | **~$25** | |

---

## 8. Deployment thoughts (Pi 5, alternatives)

The deployment target per CLAUDE.md is "Pi 5 / helpdesk PC." E2B is the right base for this:

| target | E2B INT4 fits? | tok/s estimate | Verdict |
|---|---|---|---|
| Pi 5 4GB | tight | ~1 | Don't |
| Pi 5 8GB | comfortable | ~1-3 | Demoable, slow UX |
| Pi 5 16GB | plenty | ~1-3 | Same speed (memory bandwidth bound) |
| Mac Mini M2 base ($600) | yes | ~30-50 | Best perf/$ for actual deployment |
| Mini PC w/ iGPU ($300) | yes | ~5-10 | Reasonable middle |
| Pixel 8/9 phone | yes (MediaPipe LLM) | usable | Mobile app angle |

**Path to Pi GGUF (~30 min work, not yet done):**
1. Merge LoRA adapter into base via `peft.merge_and_unload()`
2. `convert_hf_to_gguf.py` (llama.cpp tool)
3. `llama-quantize` to Q4_K_M (~2.5 GB output)
4. Run with `llama-server` on Pi

This is a v3 deliverable — useful for the demo and adds a real artifact to the public HF repo.

---

## 9. v3 plan (paper-grounded, this time)

The user explicitly asked for v3 to be properly grounded in research, not gut-feel like v1/v2. The plan:

### v3a — paper-grounded recipe sweep (~$25, ~6h)

Six ablation runs on E2B with v2 data, 2 epochs each, comparing:

| run | variable | hypothesis | citation |
|---|---|---|---|
| baseline | r=64, rsLoRA, LR 1e-4, eff_batch 16 | v2 numbers | (existing) |
| r=32 | smaller r | DoRA paper: lower r competitive | Liu 2024 (2402.09353) |
| r=16 | even smaller r | low-resource literature | various |
| DoRA | magnitude+direction split, r=64 | claimed better than rsLoRA at low data | Liu 2024 |
| LR 5e-5 | half LR | safer for 8B base; v1 step-80 spike was warmup noise | LoRA paper sweep |
| eff_batch 32 | grad_accum 16 | reduce loss curve noise | Aya / TULU defaults |
| 400-step warmup | longer warmup | underwarmup is suspect cause of v1 step-80 spike | LoRA fine-tuning practice |

Outcome: a `RESEARCH_v3.md` table with our specific numbers per ablation. Pick winning combo.

### v3b — refusal slice rebalance (~$5)

Bump refusal slice from 11% to 25%, retrain with v3a winning recipe. Test if refusal_correct moves from 13% → 60%+.

### v3c — fix verbose-output regression (~$5)

Add ~300 "be concise" examples to mix (questions that should get one-line answers) + drop default max_new_tokens to 500 in eval. Test if Belebele regression closes.

### v3d — eval infrastructure speedup (one-time engineering)

Batched HFTransformersBackend OR vLLM migration. Saves ~$3/eval run, accelerates v3 sweep meaningfully.

### v3e (optional) — GGUF conversion + Pi smoke test

Quantize the chosen v3 winner, run on Pi 5 8GB, document tok/s + memory. Adds a real "this works on a $80 device" artifact.

**Total v3 budget**: ~$35 across all phases. Returns: a publishable adapter with citations + Pi-ready GGUF.

---

## 10. What's published

- **Adapter**: https://huggingface.co/voidash/gemma-helpdesk-v2-e2b-seed42
  - `adapter_config.json` + `adapter_model.safetensors` at root
  - `chat_template.jinja` + `tokenizer.json` etc. at root
  - Updated `README.md` with v2 numbers + known limitations + how-to-use
- **Eval reports**: `eval/sft_v2_e2b_seed42/{SUMMARY.md,full_gold.json,llm_judge.json,belebele.json,gsm8k.json,roman_ne.json,side_by_side.{json,md}}`
- **Training data**: https://huggingface.co/datasets/voidash/gemma-helpdesk-data
  - `sft_v2_train.jsonl` + `sft_v2_val.jsonl` (the composed mix)
  - Per-slice files for inspection / re-mixing
- **State at the project level**: STATE.md (architecture + history), this file (SFT_V2_RESULTS.md), the model README.md
- **Memory** (`~/.claude/projects/-Users-cdjk-github-llm-gemma-god/memory/`):
  - `project_sft_v1_results.md` — v1 takeaways
  - `project_v4_v5_roadmap.md` — function calling + tacit-knowledge corpus parked
  - `feedback_aws_stop_not_terminate.md` — preserve EBS during iteration

---

## 11. Open threads / things to watch

1. **Track B (tacit-knowledge corpus)** is forked off — interview template + ASR pipeline being built separately. When that lands, retrieval gets a second corpus and v4 can layer function-calling on top.
2. **Function calling for v4** — Gemma 4's chat template natively supports `<|tool_call>...<tool_call|>` grammar. Plan parked in memory.
3. **The whole helpdesk product story** — v1/v2 are SFT exercises; the actual citizen utility comes from tacit knowledge + UX layer. SFT is necessary but not sufficient for shipping.
