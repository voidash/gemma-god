# v3-progress.md — Arc 1 done, Arc 2 pending Track B

Companion to `v3-fix.md`. Tracks what the SFT-training side (Track A) has finished and what's waiting on the deploy/retrieval side (Track B). Demo got cancelled on 2026-04-29, so we have time to do v3 right rather than rushed.

---

## Arc 1 — done (no Track B dependency)

| § | item | status | artifact |
|---|---|---|---|
| 8 | Remove buggy step-1000 mini-gen gate | ✅ done | `scripts/train_sft_v1.py` (replaced with explanatory comment) |
| 32 | Audit existing 167-item gold vs §32 spec | ✅ done | covered — see audit below |
| 5 partial | Expand refusal slice (categories that don't need fixed retrieval) | ✅ done | `corpora/sft_v3_refusals.jsonl` (2500 items) |
| 7 | Anti-verbosity slice | ✅ done | `corpora/sft_v3_terse.jsonl` (197 items) |
| 6 | Anti-template-completion slice | ✅ done | `corpora/sft_v3_anti_template.jsonl` (270 items) |
| (compose) | v3 partial mix train/val | ✅ done | `corpora/sft_v3_{train,val}.jsonl` (13,077 / 686) |
| (push) | v3 data on HF | ✅ done | https://huggingface.co/datasets/voidash/gemma-helpdesk-data |

### v3 partial mix composition (13,763 total)

```
slice                      train  val
─────────────────────────────────────
reverse_instruction       6226   327   ← v1 carryover, should be re-distilled in Arc 2
refusal_distilled (v3)    2375   125   ← was 1100 (11%) in v2, now 2500 (18.2%)
native_ne_alpaca          1425    75   ← v1 carryover, no change
english_replay            1425    75   ← v1 carryover, no change
translation_distilled      475    25   ← v2 carryover
mc_distilled               421    22   ← v2 carryover
brief_qa_distilled         285    15   ← v2 carryover
anti_template (NEW)        257    13   ← v3-fix §6
terse (NEW)                188     9   ← v3-fix §7
─────────────────────────────────────
refusal share: 18.2% (v2 was 11%, v3-fix §5 target is 25-30%)
```

### §32 audit — our gold IS sufficient

The v3-fix doc says §32 is "still unbuilt." It isn't — `eval/gov_helpdesk_gold_v1.jsonl` covers it.

| spec asks | what we have |
|---|---|
| 100 items | 167 ✓ over-coverage |
| half Devanagari / half Roman+English | 64 / 103 (close to 50/50) |
| half in-corpus / half OOD | 73 grounded / 94 refusal+ungrounded |
| golden URLs marked | 73/73 grounded items have URLs ✓ |

If Track B wants to calibrate the §4 BM25 relevance gate on this, they need to add per-item BM25 scores. That's the new work — not constructing a new eval set.

### v3-fix §6 example for Track B reference

The anti-template slice teaches: **chunks cover topic A, question asks about A AND B, gold answer covers A and refuses B**. Sample from `sft_v3_anti_template.jsonl`:

```json
{
  "question": "How do I replace my citizenship certificate? Also, what is the process for replacing a lost passport?",
  "chunks": [
    {"url": "https://moha.gov.np/citizenship-replacement", "text": "..."},
    {"url": "https://moha.gov.np/citizenship-replacement-fees", "text": "..."}
  ],
  "answer": "To replace your citizenship certificate, file a police report and submit an application at your district administration office with photos and NPR 500 fee [https://moha.gov.np/citizenship-replacement]. Regarding passport replacement, [unverified] I cannot find an authoritative source for this in the available sources."
}
```

30 topic pairs × 3 languages × ~3 items each = 270 items.

---

## Arc 2 — pending Track B (deploy/retrieval fork)

These are blocked on Track B's fixes from `v3-fix.md`. Listed in the order Track B should land them so we can proceed:

| § | what Track B needs to ship | unblocks |
|---|---|---|
| 1 | bilingual retrieval in `Retriever.search` (50-term anchor map OR sentence-transformer embeddings) | Re-distillation of grounded slice + 2 missing refusal categories |
| 2 | mojibake corpus audit + re-extract via `pdftotext -layout` + extended `legacy_fonts.rs::detect_legacy` | Quality of grounded re-distillation chunks; mojibake-only-source refusal category |
| 3 | per-claim tacit citation IDs (pseudo-ID form recommended) | Tacit corpus integration in v3 SFT |
| 4 | server-side BM25 relevance gate threshold calibration | Inference-time refusal complement to training-time refusal slice |

Once §1 + §2 are done, Track A will:

1. **Re-distill the grounded slice** using fixed retrieval. SFT teacher (Sonnet/Kimi/DeepSeek) gets the SAME chunks at distillation time as the model will see at inference time. This is the core fix for the train/serve mismatch v2 silently grew.
2. **Generate the 3 missing refusal categories** that depend on retrieval realism:
   - OOD-but-plausible-citation (retrieval surfaces tangentially-related chunks)
   - Wrong-language-source (Roman-NE question, only Devanagari chunks)
   - Mojibake-only-source (chunk is Preeti remnants — refuse rather than confabulate)
3. **Compose v3 final mix**: replace `reverse_instruction` slice with re-distilled version + add the 3 refusal categories. Refusal share should land at 25-30%.
4. **Train v3a on E2B**, eval against gold + new BM25-gated calibration.

Cost estimate: ~$15-20 for re-distillation + training + eval. ~6-8h wall.

---

## Engineering side-quests done in this session

- **Removed step-1000 mini-gen gate** (§8) — fired spuriously in both v1 and v2, never produced useful signal. Replaced with comment explaining why.
- **DeepSeek thinking-disabled** baked into `eval_groundedness.py` AnthropicShapeBackend — the v2 LLM judge had 49/50 empty bodies due to V4 series defaulting to thinking-on. Already patched on the AWS instance during v2 eval rerun; the local repo's copy has it.

---

## Things still wrong with the trainer (deferred to Arc 2 or v4)

1. **Eval throughput is poor** (~65 sec/item on greedy single-batch decode). Migrating `HFTransformersBackend` to batched generation OR vLLM is a one-time engineering investment that pays back ~$3 per eval run. Worth doing before the v3a training run so the eval after it is fast.
2. **Verbose-output regression at inference** isn't fully addressed by training-only fixes. v3-fix §7 also recommends dropping default `max_new_tokens` from 800 → 500 at eval time. Should land in `eval_sft_v1.py` before v3a's eval.

---

## Where to look in the repo

- This file (Arc 1 progress)
- `v3-fix.md` (the punch list from Track B's deploy)
- `SFT_V2_RESULTS.md` (what v2 eval told us)
- `STATE.md` (the architecture + history snapshot)
- `corpora/sft_v3_*.jsonl` (the new slice files; pushed to HF too)
- `scripts/synthesize_anti_template.py` + `synthesize_terse.py` + `generate_refusals.py` (the generators)
- `scripts/format_sft_v3.py` (the v3 mix composer)
- `scripts/train_sft_v1.py` (still the trainer; kept name for compat — the gate is removed)

---

## Quick "ready to train" status

| component | status |
|---|---|
| v3 partial training data | ✅ on disk + on HF |
| Trainer (gate removed) | ✅ ready |
| Refusal slice at target proportion | ⚠️ 18.2% vs target 25% (will hit target after Arc 2 grounded re-distillation) |
| Re-distilled grounded slice | ❌ pending Track B §1 + §2 |
| Eval infra speedup | ❌ pending engineering side-quest |

**Recommendation**: do NOT train v3a now. Wait for Track B's retrieval fix, then re-distill grounded and generate the missing refusal categories. Training on the partial mix would lock in the train/serve mismatch v3 is supposed to fix.

Status is "data ready, infrastructure ready, waiting on retrieval fix."
