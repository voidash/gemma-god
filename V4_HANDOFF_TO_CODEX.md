# v4 results + handoff brief for codex

*Snapshot: 2026-05-03 ~10:00 NPT (UTC+5:45). Companion to `SFT_V4_PREP.md` (full prep writeup) and `SFT_V3A_RESULTS.md` (prior iteration). v4 trained, evaled, mixed bag. AWS instance still hot.*

---

## TL;DR

v4-minimal+ trained successfully — clean run, val 16.19 → 0.95, best at step 1600 (very late, no overfit). Eval shows **major refusal+GSM8K wins but two new regressions** that block demoability. **Need codex's read on the v4b plan: which of two competing fixes to prioritize, in what order, with what budget.**

| | v2 | v3a | **v4** | codex gate | pass |
|---|---|---|---|---:|:---:|
| **refusal_correct** | 13% | 18% | **89.0%** 🎯 | ≥80% | **✓** |
| **GSM8K-en** | 60% | 23% | **60.0%** 🎯 | ≥50% | **✓** |
| Belebele | 54% | 54% | **56%** | ≥54% | ✓ |
| chrF (grounded) | 13.4 | 18.0 | 17.21 | ≥18 | ✗ −0.79 |
| URL recall | 0.89 | 0.90 | 0.863 | ≥0.90 | ✗ −0.04 |
| **wrongly_refused** | 2.7% | 2.7% | **19.2%** | ≤5% | **✗✗** |
| **Roman-NE degen** | 0/10 | 3/10 | **8/10** 🚨 | ≤1/10 | **✗✗✗** |
| LLM judge | n=4 (broken) | n=4 (broken) | **skipped** (no DeepSeek key on AWS box) | n≥48 | — |

---

## 1. v4 training run summary

### Recipe (per your codex spec, executed cleanly)

```
base:           google/gemma-4-E2B-it
LoRA:           rsLoRA r=64 α=128, dropout=0.05
optimizer:      AdamW 8-bit
LR:             5e-5 (was 1e-4 in v3a)
warmup:         200 steps (was 100)
schedule:       cosine
epochs:         2 (codex spec was 1.5; trainer has no fractional support;
                 explicit checkpoint saves at 200/400/.../1400 + best/final
                 lets us pick early-step-best post-train)
batch:          per_device 2 × grad_accum 8 = effective 16
total steps:    1631 (1630 nominal)
data:           13062 train / 685 val
checkpoints:    --checkpoint-steps "200,400,600,800,1000,1200,1400"
hf_repo:        none (per your launch review — kept local until eval clears)
venv:           isolated /home/ubuntu/v4-venv (clean from setup_v4_venv.sh)
```

### Trajectory (val_loss now logged per-eval, fixing v3a invisibility)

```
step    0:   val=16.1937 (initial, LoRA all-zeros)
step  200:   val= 1.4399  ← LR warmup done
step  400:   val= ~1.18  (extrapolated from logs)
step  800:   val= 1.0445
step 1000:   val= 1.0136
step 1200:   val= 0.9812
step 1400:   val= 0.9604
step 1600:   val= 0.9548  ← BEST
step 1631:   val= 0.9550  ← FINAL (essentially same)
```

**Val kept dropping all the way to step 1600** — 98% of training. No overfit signal. Lower LR + longer warmup + dropout 0.05 produced a cleaner descent than v3a's LR 1e-4 (which usually plateaued at step ~800).

### Per-slice initial val loss (confirms source-field fix from launch review)

```
english_replay         12.43  ← lowest, math is closest to base-model style
mc_distilled           14.12
v4_anti_template       15.84
v4_grounded_v3carry    16.41
translation_distilled  16.49
refusal_distilled      17.18
native_ne_alpaca       17.50
brief_qa_distilled     18.16
```

`english_replay` shows up as a key — the spike-gate at line 729 that you flagged is now armed correctly (would have fired if english_replay loss spiked 2× during training; didn't).

### Wall + cost

- Train: 3h09m on g6e.xlarge L40S
- Eval: ~33 min (full_gold + belebele + gsm8k + roman_ne; judge skipped)
- Total: ~3h45m × $1.86/hr ≈ **$7**
- Plus v4 prep API: $2 (anti-template only)
- **v4 total: $9**

### What's on disk on AWS (instance still running)

```
/home/ubuntu/checkpoints/sft_v4a_e2b_seed42/
├── best/                 ← step1600 weights (val 0.9548)
├── final/                ← step1631 weights (val 0.9550)
├── step{200,400,600,800,1000,1200,1400}/   ← all 7 explicit saves
├── state.json            ← val_history + best_step etc
├── training_report.json
└── training_report.md

/home/ubuntu/eval/reports/sft_v4a_e2b_seed42/
├── SUMMARY.md
├── full_gold.json
├── belebele.json
├── gsm8k.json
├── roman_ne.json
└── side_by_side.{md,json}
```

NOT pushed to HF — per your launch review, kept local until eval clears. With 5 of 7 gates failing, **probably should NOT push to HF** as the production v4 adapter; needs another iteration.

---

## 2. Eval results — full breakdown

### Full gold (167 items, batched eval, ~16 min — 6× v3a's wallclock per the chat_batch work)

```
GROUNDED  n=73
  chrF:           17.21    (target ≥18 — close miss)
  url_recall:     0.863    (target ≥0.90 — close miss)
  wrongly_refused: 14 (19.2%)  ← target ≤5%; THIS IS THE NEW REGRESSION

REFUSAL   n=91
  correct:        81 (89.0%)   ← target ≥80%; HUGE WIN, was 18% in v3a
  hallucinated:   10 (11.0%)

UNGROUNDED_ATTEMPT  n=3   (small sample, skipped here)
```

### Belebele NE (50 items)

```
accuracy: 56.0% (28/50)   ← v3a was 54%, slight improvement
```

### GSM8K-en (30 items)

```
accuracy: 60.0% (18/30)   ← v3a was 23%, RECOVERED to v2's level
```

### Roman-NE qualitative (10 prompts)

```
n_degen: 8/10
  loops:    8
  mojibake: 1
  empty:    0
target: ≤1
v1: 2/10, v2: 0/10, v3a: 3/10, v4: 8/10  ← WORST OF ALL ITERATIONS
```

### LLM judge — skipped

The eval script reports "skipped: no judge backend or no gold results" — DeepSeek API key not on the AWS box (we ran the data-side scripts on k2 where the key is). Not a v4 problem; an eval-deployment gap. To get judge numbers, either scp the key to AWS box and re-run `eval_sft_v1.py` with `--judge-only` (if such flag exists, or just rerun full eval), OR rerun eval on a box with the key.

### Side-by-side — skipped (no baseline file deployed)

---

## 3. The two failures, with hypotheses

### Failure A: Roman-NE degen 8/10 — catastrophic

**Most surprising finding.** v2 had it at 0/10 (the brief_qa Roman-NE slice fixed it). v3a regressed to 3/10. **v4 went all the way to 8/10 — worse than v1's baseline.**

**Hypotheses (need codex's read on which to prioritize):**

1. **Open-ended terse drop hypothesis.** v3 had 197 terse items: 58 grounded-terse + 139 open-ended. v4-minimal+ kept the 58, dropped the 139 (suspected v3a Roman-NE culprit per the v3a writeup). But 100+ of those 139 were Roman-NE conversational (no chunks). They were the model's main "respond conversationally to Roman-NE without chunks" signal. Without them, when the model sees a bare Roman-NE prompt, it has no training analog — defaults to grounded-cite-or-refuse pattern, but no chunks → loops trying to produce Devanagari content for a Roman-NE prompt.

2. **Numinamath replay hypothesis.** v3a english_replay was 1500 dirty flan_v2 (multilingual noise). v4 replaced with 1549 numinamath_tir — pure math word problems with `\(`, `\frac{}{}`, `\boxed{}` notation. The model may have learned "any English-script prompt → emit math notation." When given Roman-NE (English-script Nepali), it tries to apply math-output style → garbage loops.

3. **Compound: both.** The brief_qa Roman-NE (300 items, 50% Roman-NE) was carried over from v2, but at 13.7k total it's only ~2% of the mix — not enough to anchor Roman-NE behavior on its own once the open-ended terse 100+ Roman-NE items were removed.

I think (3) is most likely. Mitigation: bring back open-ended terse Roman-NE items (~100), OR scale up brief_qa to 700 (codex spec'd 700, we kept 300 v2 carry).

### Failure B: wrongly_refused 19.2% — train/serve mismatch on grounded

**Exactly what you predicted in the codex review.** Filtered v3 grounded slice has each (question, gold-chunk) tuple where the chunk is the SEED that generated the question. At inference, retrieval surfaces relevant-but-imperfect chunks. Model has learned "if chunks aren't a near-exact match for the question, refuse" — but that includes legit cases where retrieval surfaced a relevant chunk.

**Symptom**: 14 of 73 grounded items refused when they should have answered. The model knows HOW to cite (URL recall 0.86 for the items it did answer is reasonable). It's gun-shy.

**Mitigation per your decision tree**: `scripts/distill_grounded_v4.py` is already in the tree, ready to run. Two-step: generate Q from seed chunk, then run prod retrieval to get top-K, give teacher the RETRIEVED chunks. Cost ~$5-7, ~2h.

---

## 4. The big positive that complicates the v4b decision

**Refusal_correct 89% is a MASSIVE win.** v2 was 13%, v3a was 18%, v4 is 89%. Per codex's prior view, this would have required retrieval-realistic refusal SFT (the synthesize_refusal_v4.py script, ~$3-4) AND the BM25 server-side gate.

**v4 hit 89% with NEITHER — just v3 phrase-teaching refusal data + the better recipe (LR 5e-5, warmup 200, dropout 0.05).** This contradicts your earlier "synthetic empty/partial refusal mostly teaches the phrase, not the decision boundary" — phrase teaching IS sufficient if the model is given enough room to actually learn it (lower LR, longer warmup).

**Implication**: the synthesize_refusal_v4.py script may not be needed at all. v4 already proves the refusal mechanism works.

But: the wrongly_refused 19.2% suggests the model over-learned the refusal pattern. The DECISION BOUNDARY between "refuse" and "cite" is now too aggressive on the refuse side. So either:
- (a) more grounded examples to balance (this is what distill_grounded_v4 provides — and it's retrieval-realistic, fixing both train/serve mismatch AND the refuse/cite imbalance), OR
- (b) tune refusal share down (currently 22.5% incl. anti-template; could drop to 15-18%)

---

## 5. State of the tree, ready to run

All scripts committed. Recent commits:

```
827a03f  format_sft_v4: hardcode english_replay source for spike-gate match
6b988ae  SFT_V4_PREP.md: full writeup
ca180df  v4-minimal: english_replay assembler + dev_guard refresh
c1ba8b8  v4-minimal: filter v3 grounded via SQLite labels
55b8a20  v4 prep: refusal + anti-template generators, dev_guard, carryover assembly
b34dc06  v4 prep: pinned env, mix composer, retrieval-realistic distill, trainer fixes
22464eb  Track B crawler handoff + mojibake-classifier fix
af3517c  SFT v3a writeup + batched eval + judge thinking-disabled fix
1bd38ef  Mojibake audit script
5ee1833  pull_tulu_subset ALLOW + per-source cap + shuffle
```

### Scripts available for v4b

- `scripts/distill_grounded_v4.py` — retrieval-realistic grounded distillation. Two-step: gen Q from seed → prod retrieval → teacher answers from RETRIEVED. Estimated $5-7, ~2h. Uses k2's cleaned corpus + bilingual FTS retrieval. **Ready to run.**
- `scripts/synthesize_refusal_v4.py` — 5 query families × retrieval-realistic refusal. Estimated $3-4, ~1h. **Ready to run, but probably NOT needed given v4's 89% refusal_correct already.**
- `scripts/synthesize_anti_template_v4.py` — already executed for v4 (600 items, on disk). Could re-run with different topic-B distribution if anti-template balance matters.
- `scripts/pull_tulu_subset.py` — TULU pulls. Worth retrying for no_robots/sciriff if Roman-NE is hypothesis (1) or (3). Caveat: streaming-shuffle clusters tightly; need direct-subset pulls for guaranteed diversity.

### What's NOT in the tree but might be needed

- **Direct-subset HF dataset pulls** for English instruction (no_robots), reasoning (sciriff), MC (flan-MC). Current `pull_tulu_subset.py` only hits TULU 3's streaming surface and only seed=42/200 returned content (both numinamath). For Roman-NE fix hypothesis (1)+(3), need a separate puller.
- **Open-ended Roman-NE QA generator** if we want to recover the 139 dropped items. Would need a small script (probably <100 LOC, similar to brief_qa generator).
- **Refusal-share knob in format_sft_v4.py** if the v4b decision is "tune refusal share down to 15-18%."

---

## 6. v4b options — codex's call

Three competing remediation plans. **Be terse — pick ONE and explain.**

### Option v4b-α: distill_grounded_v4 only (~$7, ~3h prep + 3h train + 30m eval)

Hypothesis: Failure B (wrongly_refused) is the dominant problem; Failure A (Roman-NE degen) is partly downstream of Failure B (model over-refusing → more loops on Roman-NE).

Action:
1. Run `distill_grounded_v4.py --n 5500` on k2 ($5-7, 2h)
2. Replace `corpora/sft_v4_grounded_v3carry.jsonl` with the new retrieval-realistic file in `format_sft_v4.py`
3. Re-train v4b
4. Eval

If Roman-NE STILL degens, escalate to v4b-γ.

### Option v4b-β: Roman-NE recovery only (~$2, ~2h prep + 3h train + 30m eval)

Hypothesis: Failure A is the dominant problem; the over-refusal is a separate compositional issue we can ignore for now since refusal_correct is huge.

Action:
1. Generate ~200 open-ended Roman-NE QA items via DeepSeek (small script, ~$1)
2. Run multi-seed direct-subset TULU pulls for no_robots/sciriff (free, may not work due to streaming-shuffle)
3. Re-compose v4 mix with restored conversational signal
4. Re-train v4b
5. Eval

If wrongly_refused stays HIGH, escalate to v4b-α next iteration.

### Option v4b-γ: both fixes in one shot (~$10, ~4h prep + 3h train + 30m eval)

Hypothesis: both A and B are real and independent. Spend the budget once, get a clean v4b.

Action: do both v4b-α and v4b-β data work in parallel, compose, train, eval.

### What I'd push back on

I think v4b-α is most defensible — wrongly_refused is the single biggest regression and codex predicted it specifically. But: Roman-NE 8/10 is bad enough that it could be the dominant user-visible failure, in which case v4b-β buys more user-perceived quality.

Also worth weighing: v4 already PROVES refusal_correct + GSM8K wins are real. v4b's job is fixing the regressions, not adding more capability. Don't over-engineer.

---

## 7. Specific questions for codex

1. **Pick v4b-α / β / γ — which and why?**
2. **Is your earlier "synthetic refusal teaches phrase not boundary" hypothesis falsified by v4's 89%?** If yes, kill `synthesize_refusal_v4.py` from the opt-in escalation list.
3. **Is 17.21 chrF (vs 18 target) close enough to call grounded healthy, or does it suggest the same train/serve mismatch issue?** (URL recall 0.863 vs 0.90 target same question.)
4. **Roman-NE 8/10 — which hypothesis (1, 2, 3) does the data support best, and what's the minimum-cost fix?**
5. **Should we push v4 to HF as `voidash/gemma-helpdesk-v4a-e2b-seed42` even though it fails 5 of 7 gates?** It IS a meaningful step forward on refusal+GSM8K and the iteration history matters for the writeup. v3a is on HF and that one was net-FAIL too.
6. **Anything else you'd push back on in this brief.**

---

## 8. Operational state

- AWS instance `i-04ccdae9413c072bd` is **still running** ($1.86/hr). Should I stop it now and restart for v4b, or keep hot? Recommend stop — v4b prep is k2-side ($) work, AWS only needed for ~3h train.
- k2 cleaned corpus available for `distill_grounded_v4.py` runs.
- No DeepSeek key on AWS box (eval judge skipped). Adding it to ~/.fmw on AWS is a one-line scp + rerun if you want judge numbers for v4.
- All 9 explicit + best + final + state.json + training_report checkpoints are on AWS — preserved if instance is stopped (EBS persists).
- Total session spend so far: $9 (v4 prep + train + eval).
- Total project spend cumulative: ~$47 (v1+v2+v3a+v3-mojibake+v4).

Repo: `/Users/cdjk/github/llm/gemma-god`
Eval reports: `/home/ubuntu/eval/reports/sft_v4a_e2b_seed42/` on AWS box (3.82.114.223 currently)
