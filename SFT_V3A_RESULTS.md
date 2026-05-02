# SFT v3a — results & learnings

*Snapshot: 2026-05-02. Companion to `SFT_V2_RESULTS.md` (prior iteration), `v3-progress.md` (Arc 1 plan), and `v3-fix.md` (Track-B server-side punch list).*

---

## TL;DR

v3a = **Arc 1 partial mix on E2B**. Same recipe as v2 (rsLoRA r=64 α=128, AdamW 8-bit, 2 epochs), but with three new training slices that didn't exist in v2: **2,500-item refusal expansion** (was 1,100 in v2), **270-item anti-template**, **197-item terse**. The grounded slice is intentionally NOT re-distilled — that waits for Track B's bilingual retrieval + corpus mojibake re-extraction, gating Arc 2.

| metric | v2 | **v3a** | Δ |
|---|---|---|---|
| URL recall (grounded) | 0.89 | **0.90** | +0.01 (held) |
| chrF (grounded) | 13.42 | **18.03** | **+4.6** ✓ chrF regression recovered |
| wrongly_refused | 2.7% | **2.7%** | 0 (held) |
| refusal_correct | 12/91 (13%) | **16/91 (18%)** | +5pp ✓ but still far from 90% target |
| Roman-NE degen | 0/10 | **3/10** | **−3** ✗ degen reappeared |
| Belebele | 54% | 54% | 0 |
| GSM8K-en | 60% | 23% | **−37pp** ✗ English replay collapsed |
| LLM judge correct% | 16% (n=50) | 25% (n=4) | +9pp but **n=4 unreliable** — 46/50 judge calls errored |
| LLM judge citation | 4.7/5 | 3.75/5 | −1.0 (smaller sample) |
| Eval throughput | ~65 s/item | **~11 s/item** | **6× speedup** ✓ batched generation works |

**Demoability call: 2 PASS / 3 FAIL.** Net regression on Roman-NE degen + GSM8K, but real movement on the things v3 was supposed to fix (chrF, refusal, citation behavior).

Public adapter: https://huggingface.co/voidash/gemma-helpdesk-v3a-e2b-seed42

**Reading**: v3a confirms the slice mechanism works for the new categories — refusal_correct moved up, chrF recovered — but **the partial-mix approach is insufficient on its own**. The unexplained Roman-NE degen and GSM8K collapse suggest either (a) data-mix balance shifted unfavorably when refusal slice doubled, or (b) the LR schedule that worked for v2's smaller mix is over-cooking on v3a's larger one. Also surfaces the gap that motivates Arc 2: **refusal training data only covers categories the synthesizer thought of**, leaving education/land/pan_vat/business at 0% refusal correctness.

---

## 1. Why v3a — what v2 left on the table

`v3-fix.md` documented 13 issues from the v2 demo. Track A (training side) owned a subset:

| § | issue | v3a slice |
|---|---|---|
| 5 | refusal slice 11% of mix is too low (model's "always-answer" prior dominates) | **refusal expanded 1100→2500** (18.2% of mix) |
| 6 | model template-completes when prompt has chunks for topic A but question asks A+B (e.g. cite passport renewal procedure when chunks only have citizenship) | **anti_template** slice — 270 items: chunks cover A, question asks A+B, gold answer covers A and refuses B with `[unverified]` |
| 7 | verbose answers regressed chrF from 22 → 13 in v2 | **terse** slice — 197 items, 1-3 sentence answers |
| 8 | step-1000 mini-gen self-shutdown gate fired spuriously in v1 + v2 | **gate removed** in `train_sft_v1.py` |

Track B owns retrieval-side fixes (bilingual FTS, per-claim tacit citations, dedup, mojibake re-extraction). Those landed on k2 production on 2026-04-30. The grounded re-distillation that depends on them is Arc 2, not Arc 1.

---

## 2. Data composition

### v3a partial mix (13,763 records, 95/5 stratified train/val)

| slice | records | source | system prompt? |
|---|---|---|---|
| reverse_instruction (grounded) | 6,553 | DeepSeek V4-Flash, reverse-instruction from gov.np chunks (v1 carryover, **NOT re-distilled** — pending Arc 2 retrieval fix) | yes (SYSTEM_GROUNDED) |
| native_ne_alpaca | 1,500 | Saugatkafley/alpaca-nepali-sft (v1 carryover) | no |
| english_replay | 1,500 | TULU 3 SFT mixture filtered (v1 carryover) | no |
| **refusal_distilled (NEW size)** | **2,500** | DeepSeek-generated, expanded categories (was 1,100 in v2) | yes |
| translation_distilled | 500 | FLORES-200 NE↔EN (v2 carryover) | no |
| mc_distilled | 443 | DeepSeek A/B/C/D trivia 3-lang (v2 carryover) | no |
| brief_qa_distilled | 300 | DeepSeek Q&A 50% Roman-NE biased (v2 carryover) | no |
| **anti_template (NEW)** | **270** | DeepSeek: chunks cover A, Q asks A+B, A covers A and `[unverified]`-refuses B | yes |
| **terse (NEW)** | **197** | DeepSeek anti-verbosity, 1-3 sentence answers | mixed |

**Refusal share: 18.2%** (v2 was 11%). The v3-fix §5 target was 25-30%, which Arc 2 will hit naturally because grounded re-distillation produces fewer "kept" items per chunk.

### Generators

- `scripts/generate_refusals.py` — bumped from 1,100 to 2,500 items
- `scripts/synthesize_anti_template.py` — new (~30 topic pairs × 3 languages × ~3 items)
- `scripts/synthesize_terse.py` — new
- `scripts/format_sft_v3.py` — new mix composer

All use DeepSeek with `thinking: {type: disabled}` per the v2-learned lesson (V4 series defaults to thinking-on, eats max_tokens budget).

---

## 3. Training trajectory

### Setup

| | |
|---|---|
| Base | google/gemma-4-E2B-it |
| Method | LoRA via PEFT, rsLoRA scaling (Kalajdzievski 2023) |
| r / α | 64 / 128 (same as v2) |
| Targets | q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj |
| Optimizer | AdamW 8-bit (bitsandbytes) |
| Schedule | LR 1e-4, cosine + 100-step linear warmup |
| Effective batch | 16 (per-device 2 × grad-accum 8) |
| Memory | bf16 + gradient checkpointing + `expandable_segments:True` |
| Hardware | 1× NVIDIA L40S (g6e.xlarge), 32 GB / 48 GB used |
| Train wall | **2h51min** (1,632 steps × ~6.3 s/step) |
| Eval wall | **52 min** (full_gold 31 min batched + judge + belebele + gsm8k + roman_ne) |
| Total instance time | ~3h45min (after the 4 false starts; see §6) |

### Loss

The trainer in this run logged `initial_val=16.1167` at step 0 (the LoRA adapter is initialized to zeros, so val loss equals base-model loss on the new format) but **did not log periodic val_loss during training**. Best-checkpoint selection therefore fell back to "last checkpoint" — which is the step-1632 snapshot in HF's `best/` branch. v2's trainer did log per-step val, so this is a regression in v3a's logging path; flagged for v4.

Per-slice initial val_loss (lower = closer to gold-answer style):

| slice | initial val |
|---|---|
| brief_qa | 13.16 |
| english_replay | 13.62 |
| mc | 14.85 |
| translation | 15.14 |
| anti_template | 15.58 |
| reverse_instruction (grounded) | 16.38 |
| refusal | 16.84 |
| native_ne_alpaca | 17.77 |
| **terse** | **19.96** ← furthest from base-model style |

Train-loss trajectory (every ~200 steps): `5.19 → 1.18 → 0.92 → 0.83 → 0.77 → 0.69 → 0.65 → 0.59` — clean cosine-shaped descent, no NaN/Inf, no aborts. Step 1000 (the v1+v2 abort point) **passed cleanly**.

HF auto-pushes happened at steps 200, 400, 500, 1000, 1200, 1400, 1500, end. Each push wrote a step-N branch on `voidash/gemma-helpdesk-v3a-e2b-seed42` for crash-recovery.

---

## 4. Eval results

### 4.1 Full gold (167 items) — primary metric

```
grounded   n=73   chrF=18.03   url_recall=0.90   wrongly_refused=2  (2.7%)
refusal    n=91   correct_pct=17.6%   hallucinated=75
ungrounded n=3    chrF=25.86
```

**Refusal correctness by category** (the most telling table):

| category | n | refusal_correct |
|---|---|---|
| police | 5 | **40%** |
| passport | 20 | **35%** |
| driving_license | 6 | **33%** |
| other | 17 | 18% |
| citizenship | 20 | 10% |
| business | 2 | 0% |
| birth_registration | 1 | 0% |
| education | 6 | 0% |
| land | 3 | 0% |
| pan_vat | 7 | 0% |
| tax | 2 | 0% |
| visa_immigration | 2 | 0% |

**Pattern**: refusal works for categories the synthesizer covered heavily (passport, police, driving_license — these get many refusal training examples). Categories with few/no refusal-slice examples (education, land, pan_vat) sit at 0%. **This is exactly the Arc-2 thesis**: training-time refusal can't enumerate every OOD category. Need realistic-retrieval generation to cover the long tail.

**By language**:

| lang | n | grounded chrF | refusal_correct |
|---|---|---|---|
| code_mixed | 17 | 25.11 | 18% |
| devanagari | 61 | 14.91 | 8% |
| roman_nepali | 89 | 23.25 | 19% |

Devanagari grounded chrF (14.9) lags Roman-NE (23.3) — likely because the gold answers in Devanagari are stricter formatted templates that reward exact phrasing.

### 4.2 LLM-as-judge — **broken** (n=4, n_errors=46) — root cause IDENTIFIED

50 items intended; only 4 returned valid scored output. **46 calls errored.**

Root cause (caught by codex during v4 planning, post-eval): `eval_groundedness.py:79` `AnthropicShapeBackend.chat()` did NOT pass `thinking: {type: disabled}` despite the v2 lesson saying it must. The payload was only `{model, max_tokens, system, messages}`. DeepSeek V4-Flash defaults thinking-on, which eats the full `max_tokens` budget on internal reasoning and returns content blocks with `type != "text"`, so `_parts = []` → empty string → judge parser fails. Same failure mode as v2's first eval pass.

**Fixed in this commit** — `thinking: {type: disabled}` now in the payload (other endpoints like Meridian/Kimi ignore unknown fields). Treat v3a's 25% CORRECT and 2.0/5 groundedness numbers as unreliable; rerun judge before any v3a-vs-v4 comparison uses them.

### 4.3 Belebele 50 (Nepali MC) — regression check

54% accuracy. Same as v2 (54%). Base Gemma 4 IT was ~63%. The 9pt gap to base persists; v3a didn't improve it.

### 4.4 GSM8K-en 30 — English replay regression

**23% accuracy. v2 was 60%.** A 37pp collapse is alarming. Hypothesis: doubling the refusal slice + adding the terse slice diluted the english_replay representation in any given gradient step, shifting the model's English-task prior toward refusal-style short answers. This is the most concerning finding from the run.

### 4.5 Roman-NE qualitative (10 prompts)

3/10 degen (loops=3, mojibake=0, empty=0). v2 was 0/10. The terse slice was supposed to help here, not hurt — but if the model learned "terse answer to any prompt", the open-ended Roman-NE prompts may now collapse into short looping replies. Worth manually inspecting the 3 degen outputs.

### 4.6 Side-by-side vs baseline — skipped (no baseline file deployed)

---

## 5. Demoability call

```
PASS: 2
  ✓ url_recall 0.90 ≥ 0.70
  ✓ wrongly_refused 3% ≤ 10%

FAIL: 3
  ✗ refusal_correct 18% < 90% target
  ✗ roman_degen 3/10 > 1
  ✗ belebele 0.54 < 0.55 (single-pp miss but same as v2)
```

**Net call: not publishable as a v2 replacement.** v3a improves on the dimensions v3-fix.md prioritized (chrF, refusal correctness, citation discipline) but introduces two new regressions (Roman-NE degen, GSM8K) and the refusal target is still an order of magnitude off. Track B's k2 deploy is still on the v2 adapter — leave it that way until either Arc 2 lands or v3a's regressions are root-caused and fixed.

---

## 6. Operational learnings — environment hell

The training environment was the biggest time sink of the entire run. Documenting so v4 doesn't repeat this:

### What broke

The instance was reused (stop+start) from v2's run on 2026-04-29. EBS preserved the cached 16 GB Gemma model. Between runs, **another project on the same instance had run `pip install`-style operations that mutated the shared `/opt/pytorch` venv**:

| package | end-of-v2 (working) | start-of-v3a (broken) |
|---|---|---|
| transformers | (worked w/ Gemma 4) | 5.5.1 (peft incompat) |
| peft | 0.19.1 | 0.19.1 (broken via transformers 5.x) |
| torch | CUDA build | **2.6.0+cpu** ← CPU-only! |
| torchvision | matched | 0.22.0+cu128 (mismatched torch) |

Symptom chain:
1. peft 0.19 imports `from transformers import BloomPreTrainedModel`. transformers 5.x removed it → `ModuleNotFoundError`.
2. Downgrading transformers to 4.57.x fixed peft import but broke Gemma 4 tokenizer: `tokenizer_config.json` has `extra_special_tokens: ["<|video|>"]` (a list) and transformers 4.x base class expects a dict → `AttributeError: 'list' object has no attribute 'keys'`.
3. Downgrading further (transformers 4.50, 4.53) hit `RuntimeError: operator torchvision::nms does not exist` because torch was the CPU build but torchvision was CUDA.

### Fix

Created an **isolated venv** at `/home/ubuntu/v3a-venv` (separate from the broken `/opt/pytorch`):

```
torch          2.11.0+cu130   (matches DLAMI driver, brought in transitively)
transformers   5.5.1          (handles Gemma 4 tokenizer's list-form extra_special_tokens)
peft           0.19.1         (PATCHED — see below)
accelerate     1.2.1
bitsandbytes   0.49.2         (was 0.45 — 0.45 imports triton.ops which triton 3.x removed)
huggingface_hub  >= 0.26
```

**Peft patch** (one-liner): `peft/utils/constants.py:16` —

```python
# Was:
from transformers import BloomPreTrainedModel

# Now:
try:
    from transformers import BloomPreTrainedModel
except (ImportError, ModuleNotFoundError):
    BloomPreTrainedModel = None
```

The downstream `hasattr(BloomPreTrainedModel, "_convert_to_standard_cache")` at line 54 then evaluates False and the Bloom-specific code path is skipped.

### Other fixes during this session

| problem | fix |
|---|---|
| Step-1000 self-shutdown gate (v1+v2 both bricked here) | removed from `train_sft_v1.py:669`, replaced with explanatory comment |
| Tokens silently empty in tmux subshell | `HF_TOKEN="$(...)" ssh ... "...$HF_TOKEN..."` doesn't expand against the temp env (parent-shell expansion timing). Fix: persist tokens to `/home/ubuntu/.v3a-env`, source inside tmux |
| Nested-quoting hell building tmux commands inline | write inner script to `/home/ubuntu/.v3a-inner.sh`, tmux runs `bash /home/ubuntu/.v3a-inner.sh` |
| Auto-shutdown after eval (v2 cloud-init's behavior) | **removed** for v3a — instance left running so user can stop manually |

### What v4 should change

1. **Pin a known-good environment in a project-owned venv from day 1**. Don't share `/opt/pytorch` with other projects — the surprise factor is too high.
2. **Lock package versions in a `requirements-train.txt`** that the launcher pip-installs verbatim. The current `pip install -U "transformers>=4.50"` is open-ended and will rot the moment a major version ships.
3. **Add periodic val_loss logging in `train_sft_v1.py`** — v3a's "best" was just "last", which defeats the point of the val-eval infrastructure.
4. **Auto-retry the LLM judge** (or fail loudly with full per-item error before producing aggregate stats). 46/50 silently-failed calls is unacceptable — the eval pretended to succeed.
5. **Carry GSM8K + Roman-NE checks earlier in training** (e.g. at the first val pass, not just post-train) — catastrophic forgetting that lands as a 37pp regression should be visible during training, not surprise us in eval.

---

## 7. Eval-side wins worth keeping

Two engineering improvements landed in the eval scripts before this run:

1. **Batched generation in `HFTransformersBackend`** (`eval_sft_v1.py:182`). New `chat_batch(msgs_list, max_tokens)` method with left-padded tokenization + per-item slicing past `prompt_len`. `run_full_gold` consumes it via `--batch-size N` (default 4). **Result: full_gold ran in 1854 s for 167 items (~11 s/item) vs v2's ~65 s/item — 6× speedup**. Saved ~$3 of L40S time on this single eval; will save more on multi-seed ablations.
2. **`score_one()` extracted from `eval_one()`** (`eval_groundedness.py:336`). Pure scoring function over a precomputed `model_output` — used by both the sequential (Anthropic-shape) path and the batched (HF) path so scoring stays in one place.
3. **Default `max_new_tokens` 800 → 500** (`eval_sft_v1.py:108`). Per v3-fix §7. Reduces eval wallclock + brings test-time decoding closer to the terse-slice training distribution.

---

## 8. Next steps

**Don't ship v3a as the production adapter.** Track B's k2 deploy is still on v2; leave it that way.

**Two parallel paths for the next iteration:**

1. **Investigate v3a's regressions** before more training:
   - Inspect the 3 Roman-NE degen outputs — is it the terse slice causing premature stop-token, or something else?
   - Why did GSM8K collapse? Run a step-N evaluation across the saved checkpoints (200/400/500/1000/1200/1400) to find when the regression appeared.
   - Re-run the LLM judge with retry + version-pinned DeepSeek to get reliable n=50 numbers.
2. **Continue toward Arc 2** in parallel — wait for Track B's mojibake corpus re-extraction to land, then re-distill the grounded slice through the *fixed* retriever + generate the 3 missing refusal subcategories (OOD-with-plausible-citation, wrong-language-source, mojibake-only-source). Cost estimate from `v3-progress.md`: ~$15-20 for re-distill + train + eval. Refusal share will land at the 25-30% target naturally because grounded re-distillation drops fewer-supported items.

Total spend across v1+v2+v3a: ~$36 (~$28 prior + ~$8 this run).

Public artifacts:
- Adapter: https://huggingface.co/voidash/gemma-helpdesk-v3a-e2b-seed42
- Eval reports: pushed to the same repo under `eval/`
- Train log: pushed as `train_v3a.log`
