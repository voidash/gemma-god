# SFT v4-minimal+ — prep complete, ready to launch

*Snapshot: 2026-05-03. Companion to `SFT_V3A_RESULTS.md` (prior iteration), `SFT_V2_RESULTS.md`, `STATE.md`. Documents the v4 prep work in this session: Track B mojibake re-extraction, codex-vetted scale-down from full rebuild to "minimal+", and the launch-ready v4 mix.*

---

## TL;DR

v3a regressed on Roman-NE degen (3/10) + GSM8K (−37pp) and the refusal ceiling stuck at 18%. Codex's original v4 plan called for full retrieval-realistic rebuild (~$13 in API). The user pushed back with "why full rebuild?" — codex agreed: the rebuild is not justified UNTIL v4-minimal+ proves insufficient end-to-end (with the BM25 relevance gate). v4-minimal+ is what we built this session.

| | v3a | v4-minimal+ |
|---|---|---|
| API spend (data) | ~$3 (refusal + anti-template + terse synth) | **$2** (anti-template only) |
| Total records | 13,763 | **13,747** |
| Refusal share | 18.2% | 18.2% / 22.5% incl. anti-template |
| Grounded slice | v1 carryover w/ embedded mojibake chunks | **filtered v1 carry** via SQLite labels (8542→6297 after format) |
| Anti-template | 270 with FAKE invented URLs | **600 with REAL retrieved chunks** |
| English replay | 1500 dirty flan_v2 (multilingual noise) | **1549 numinamath_tir** (math anchor for GSM8K) |
| Open-ended terse | 139 items (suspected Roman-NE degen culprit) | **DROPPED** |
| Trainer | best/ overwritten by periodic-push (bug) | best/ ONLY updated on val-improve, explicit `--checkpoint-steps` |
| Env | shared `/opt/pytorch` (corrupted by other project between v2/v3a) | **isolated `/home/ubuntu/v4-venv`** + pinned requirements |

Public artifact target: https://huggingface.co/voidash/gemma-helpdesk-v4a-e2b-seed42 (after launch)

---

## 1. Track B mojibake re-extraction (commit `22464eb`)

The headline blocker. v3a couldn't reach Arc 2 because the corpus had 14% mojibake-contaminated chunks. Track B (the deploy-side agent) had been working on this; they were no longer active so this work folded into the SFT track.

### What was actually wrong

`v3-fix.md §2` said "re-extract via `pdftotext -layout`" — **that turns out to be wrong**. The Nepal-gov PDFs embed Preeti as a TrueType font with WinAnsi encoding; pdftotext faithfully decodes the broken font→char mapping. Same mojibake out. Mixed Preeti+Kalimati fonts in the same word means hybrid tokens like `)ा*धकरण` (should be `प्राधिकरण`) are unrecoverable post-extraction — the Devanagari chars in the token came from a different font and can't be re-mapped through Preeti.

**Detect+drop is the only winning move.**

### What landed

`src/crawler_v2/language.rs::classify` extended to flag Devanagari/Mixed chunks contaminated by hybrid mojibake tokens:
- embedded Latin alpha mid-word (`सHपादन` should be `सम्पादन`)
- Preeti glyph chars `* / ) ( [ ] { } | : ; = +` (`)ा*धकरण`)
- doubled matras `ुु ाा ीी` impossible in well-formed Devanagari (`अनुुवादक` should be `अनुवादक`)

New helper `devanagari_with_hybrid_mojibake_ratio` computes ratio of mojibake-bearing tokens / Devanagari-bearing tokens. Threshold 0.10 → MojibakeSuspected → indexer drops the chunk.

`src/legacy_fonts.rs::classify_word` got an explanatory comment on why hybrid tokens are NOT routed to Preeti recovery (would produce different garbage, not recovery).

### Before / after on k2 corpus

| | pre rebuild | post rebuild |
|---|---|---|
| total chunks | 101,022 | **135,262** |
| severe+heavy mojibake (≥20% bad tokens) | 542 (0.5%) | **49 (0.04%)** |
| +moderate (5-20%) | 2,821 (2.8%) | **1,419 (1.05%)** |

`v3-fix.md §2`'s "<1% mojibake" target met decisively for severe+heavy (corpus grew because re-indexing also processed previously-chunkless docs — 4,245 attempted, 1,175 ok, 13,356 dropped as mojibake).

`chunks_fts` rebuilt from the new chunks via the documented `DROP TABLE chunks_fts; CREATE VIRTUAL TABLE ... INSERT INTO ... SELECT ...` pattern (Track B's server has `/admin/reindex` that does this for production).

### Approaches that didn't work (rejected, documented for next agent)

- **`pdftotext -layout` on source PDFs** — produces same mojibake (font's WinAnsi encoding is the broken thing).
- **Looser legacy_fonts gate in `text_extract.rs`** (accept conversion if Devanagari char count grew by 100+) — broke things further. Reverted.
- **Force-classifying hybrid tokens as Convert** in `classify_word` — re-ran Preeti map on actual Devanagari producing different garbage. Reverted.

---

## 2. Trainer fixes (commits `b34dc06`, included in v4-minimal+)

v3a's "best/ checkpoint was actually the last-step weights" regression. Root cause: `_save_best_and_push` was called from BOTH the new-best path AND the periodic-push path at line 718. Step-1500's periodic push overwrote `best/` with non-best weights.

### What changed in `scripts/train_sft_v1.py`

- Split into `_save_to(subdir, reason)` general helper + `_save_best_and_push` that ONLY saves to `best/`.
- Periodic-push path no longer overwrites `best/` — when `--checkpoint-steps` is set, saves to `step{N}/` subdirs; when unset, just re-pushes the existing `best/` as a crash-recovery snapshot.
- New `--checkpoint-steps "0,200,400,600,800,1000,1200,1400"` arg per codex v4 spec — explicit checkpoint saves for downstream behavioral-gate selection.
- `val_loss` ALWAYS logged per-eval (v3a only logged on new-best, so trajectory was invisible without parsing state.json).
- Crash handler saves to `crashed/` not `best/`.
- Training-complete saves to `final/` not `best/`.

---

## 3. Codex v4 plan → user pushback → v4-minimal+

### Codex's original spec (2026-05-02)

16,000-record full rebuild:
- 5,500 grounded — re-distill via production `Retriever.search`
- 3,600 refusal — 6 retrieval-realistic subcategories
- 600 anti-template — REAL chunks (vs v3a's fake)
- 350 grounded-terse, 700 brief QA, 3000 English replay (math/instr/MC/reasoning), carryovers

Recipe deltas: LR 5e-5 (was 1e-4), warmup 200 (was 100), 1.5 epochs, dropout 0.05, isolated venv, behavioral-gate best selection.

Estimated API spend: ~$13.

### User pushback (this session)

> "but again why do we need full rebuild?"

Walking through v3a's failures honestly:

| v3a failure | Where the fix actually belongs | Needs new data? |
|---|---|---|
| Roman-NE degen 3/10 | Drop the 139 open-ended terse items | **No** — already done in `assemble_v4_carryovers.py` |
| GSM8K −37pp | Replace dirty flan_v2 with numinamath/no_robots/sciriff | No — TULU pulls, $0 |
| Refusal ceiling 18% | Codex's own pushback: "90% refusal is wrong scope — should be end-to-end (server-side BM25 gate)" | **No — server-side fix** (Track B's v3-fix.md §4, not yet shipped) |
| Belebele flat 54% | Recipe change (LR, warmup) might help | No — recipe change, $0 |
| chrF regression | Anti-template + terse already moved chrF v3 14 → v3a 18 | Already covered |
| best/ was last/ | Trainer bug | **Fixed** in `b34dc06` |

### Codex's response to "is plan D defensible?"

> "Plan D is defensible only as `v4-minimal`, a bugfix/ablation run. It is not evidence that retrieval-realistic distillation is unnecessary unless it passes an end-to-end eval with the relevance gate."

Plus two specific bugs codex caught in the proposed plan:

1. **Wrong filter heuristic.** `scripts/audit_mojibake.py` predates the in-tree `language.rs::devanagari_with_hybrid_mojibake_ratio` classifier. They're not equivalent. Use the SQLite `chunks.language` column instead — it's populated by the indexer with the authoritative labels.
2. **Dev_guard pollution.** The original `eval/dev_guard_v4.jsonl` sampled 10 anti-template items from `corpora/sft_v3_anti_template.jsonl` — those have FAKE invented URLs. Eval would have rewarded the model for matching fake citations.

Both fixed in this session.

### Anti-template — codex picked (c) rebuild

> "Choose (c). Rebuild the 270 → 600 with real chunks. If absolute zero API, choose (b) and drop them. Do **not** keep fake chunks."

The 600-item anti-template rebuild was the cheapest of the rebuild items at ~$2. Generated on k2 via `synthesize_anti_template_v4.py` — 600/600 success in 11 min, 0 errors.

### Decision criterion for whether full rebuild is ever needed

Per codex, v4-minimal+ "passes" if ALL hold:
- Roman-NE degen ≤1/10
- GSM8K ≥50% (n=30, near v2's 60%)
- Belebele ≥54%
- grounded chrF ≥18, URL recall ≥0.90
- grounded wrongly_refused ≤5%
- **with relevance gate enabled**: full-gold refusal_correct ≥80% AND dev_guard refusal ≥70%, while wrongly_refused stays ≤5%

**If model-only refusal stays mediocre but end-to-end passes → skip full refusal rebuild. If end-to-end fails → fix the BM25 relevance gate (Track B §4) BEFORE spending on retrieval-realistic refusal SFT.**

---

## 4. Final v4 mix composition

### Slices (commits `c1ba8b8`, `ca180df`)

| Slice | Records | Provenance |
|---|---:|---|
| v4_grounded_v3carry | 6,297 | `filter_v3_grounded_via_db.py` joined `sft_v1_grounded.jsonl` (9,166) against current SQLite chunks.language. 8,542 records survived (93.2% retention). 624 dropped because their chunk_ids no longer exist post-rebuild (chunk_id is content-hashed; re-extraction produced different text → different IDs → "missing"). ZERO survivors flagged mojibake_suspected — the rebuild + classifier work end-to-end. |
| refusal_distilled | 2,500 | v3 carry as-is. Phrase-teaching only — codex's view is that the boundary fix belongs to the server-side BM25 gate. |
| native_ne_alpaca | 1,500 | v1 carryover (Saugatkafley/alpaca-nepali-sft) |
| v4_english_replay | 1,549 | numinamath_tir from multi-seed TULU pulls. **The codex spec called for math + instruction + MC + reasoning buckets, but TULU 3's parquet shards are source-clustered AND streaming.shuffle only randomizes within the loaded shard's window. Seeds 50/100/150/250/300 yielded 0 records (their shards held only sources outside ALLOW). Only seeds 42 + 200 hit content (both numinamath).** Accepting math-anchor-only English replay for v4-minimal+ — broader diversity deferred since direct-subset pulls would be a separate effort. Math anchor IS specifically what fixes the GSM8K regression that codex/v3a flagged. |
| v4_anti_template | 600 | NEW — `synthesize_anti_template_v4.py` on k2 with REAL retrieved chunks. 3-step: pick seed chunk for topic A → propose related topic B not covered → compose 2-part question A+B → teacher answers A from chunks, refuses B with `[unverified]`. |
| translation_distilled | 500 | v2 carryover (FLORES-200) |
| mc_distilled | 443 | v2 carryover. (Codex spec was 550; +107 top-up deferred — `format_sft_v4` warns but doesn't bail.) |
| brief_qa_distilled | 300 | v2 carryover. (Codex spec was 700; top-up deferred.) |
| v4_grounded_terse | 58 | Pruned from sft_v3_terse (197 → 58 grounded-terse). The 139 open-ended terse items DROPPED — suspected Roman-NE degen culprit per v3a analysis. |

**Total: 13,747 records → 13,062 train + 685 val (5% val frac).**

**Refusal share: 18.2% by source field, 22.5% including anti-template.** Under codex's 25-30% target but defensible per his own pushback that 90% refusal target is end-to-end (server-side gate territory).

### Eval set (commits `55b8a20`, `ca180df`)

`eval/dev_guard_v4.jsonl` — 56 items:
- 32 grounded (incl. 10 anti-template with REAL chunks now)
- 21 refusal — over-weighted on the categories v3a hit 0% (education×3, land×3, pan_vat×3, business×2, tax×2, visa_immigration×2)
- 3 ungrounded_attempt

For trainer's in-loop eval at step-400 / step-800 / final per codex's gate spec.

---

## 5. Trainer + env scaffolding

### `requirements-train.txt`

Pinned the v3a-tested combo to avoid the "/opt/pytorch corrupted between runs" debugging loop:

```
transformers==5.5.1     # handles Gemma 4 tokenizer's extra_special_tokens-as-list
peft==0.19.1            # NEEDS PATCH (BloomPreTrainedModel optional import)
accelerate==1.2.1
datasets==3.2.0
bitsandbytes==0.49.2    # 0.45 imports triton.ops which triton >=3.x removed
huggingface_hub>=0.26
sentencepiece, sacrebleu, protobuf
```

torch+torchvision installed separately from `https://download.pytorch.org/whl/cu130` — unconstrained pip would pull CPU wheel transitively from PyPI default index.

### `scripts/setup_v4_venv.sh`

Idempotent bootstrap on the AWS box:
1. Create `/home/ubuntu/v4-venv` if missing
2. Install torch from cu130 index FIRST (otherwise CUDA dies)
3. Install pinned stack from `requirements-train.txt`
4. Patch `peft/utils/constants.py` to make `BloomPreTrainedModel` import optional
5. Smoke-test imports + CUDA

One command on a fresh box. No more shared `/opt/pytorch` corruption.

### `scripts/format_sft_v4.py`

16k-record mix composer with:
- Pre-flight check that all slice files exist (--allow-missing for partial composition during prep)
- Per-slice deltas vs `TARGET_COUNTS` shown in summary
- Refusal-share assertion with target 25-30%
- Composition-by-source breakdown
- Stratified 95/5 train/val split

---

## 6. Launch runbook (when AWS GPU frees up)

```sh
# 1. Restart the AWS instance (currently stopped, EBS preserved per stop-not-terminate rule)
aws --profile devnet-staging --region us-east-1 ec2 start-instances \
    --instance-ids i-04ccdae9413c072bd

# Wait until State=running, get IP
./scripts/launch_aws_train.sh status
IP=$(...)

# 2. SCP prereqs (8 files)
scp requirements-train.txt scripts/setup_v4_venv.sh scripts/train_sft_v1.py \
    scripts/eval_sft_v1.py scripts/eval_groundedness.py \
    corpora/sft_v4_train.jsonl corpora/sft_v4_val.jsonl \
    eval/dev_guard_v4.jsonl eval/gov_helpdesk_gold_v1.jsonl \
    ubuntu@$IP:/home/ubuntu/

# 3. Bootstrap venv (idempotent, ~10 min on fresh box, <1 min if v4-venv exists)
ssh ubuntu@$IP 'bash setup_v4_venv.sh'

# 4. Launch training in tmux with codex recipe
ssh ubuntu@$IP 'tmux new-session -d -s v4 "
source /home/ubuntu/v4-venv/bin/activate
mkdir -p data eval scripts
mv sft_v4_*.jsonl data/
mv dev_guard_v4.jsonl gov_helpdesk_gold_v1.jsonl eval/
mv train_sft_v1.py eval_sft_v1.py eval_groundedness.py scripts/
python scripts/train_sft_v1.py \
  --train data/sft_v4_train.jsonl \
  --val data/sft_v4_val.jsonl \
  --model-id google/gemma-4-E2B-it \
  --output /home/ubuntu/checkpoints/sft_v4a_e2b_seed42 \
  --seed 42 \
  --hf-repo voidash/gemma-helpdesk-v4a-e2b-seed42 \
  --max-wall-hours 6.0 \
  --epochs 2 \
  --lr 5e-5 \
  --warmup-steps 200 \
  --lora-dropout 0.05 \
  --checkpoint-steps \"0,200,400,600,800,1000,1200,1400\" \
  2>&1 | tee train_v4.log
"'

# 5. Eval after training (uses the new --batch-size for ~6x speedup vs v3a)
ssh ubuntu@$IP 'source /home/ubuntu/v4-venv/bin/activate && \
  python scripts/eval_sft_v1.py \
    --base google/gemma-4-E2B-it \
    --adapter /home/ubuntu/checkpoints/sft_v4a_e2b_seed42/best \
    --label sft_v4a_e2b_seed42 \
    --gold eval/gov_helpdesk_gold_v1.jsonl \
    --batch-size 8 \
    --out-root eval/reports'
```

### Cost estimate

- Train: ~3-4h on g6e.xlarge ($1.86/hr) ≈ $6-8
- Eval: ~30 min batched ≈ $1
- Total: ~$7-9 GPU + $0 API (data already done)

### What we're NOT doing in this v4 launch

- No retrieval-realistic distillation. `scripts/distill_grounded_v4.py` and `synthesize_refusal_v4.py` are committed and ready as opt-in escalation paths if v4-minimal+ eval doesn't meet codex's gates.
- No multi-seed for English replay diversity — TULU 3's streaming-shuffle clustering won the argument; will need direct-subset pulls (separate effort) for math+instruction+MC+reasoning split.
- No `--checkpoint-steps` post-train selection ablation. The trainer saves them, but v4-minimal+ just uses `best/` for eval. If gates fail on best/, we can eval each step-N/ to find an earlier checkpoint that passes more.

---

## 7. Files inventory

### New (this session)

```
src/crawler_v2/language.rs               # mojibake-classifier extension
src/legacy_fonts.rs                      # comment on hybrid-token strategy
SFT_V4_PREP.md                           # this doc
SFT_V3A_RESULTS.md                       # v3a writeup (prior session, this session committed)
requirements-train.txt
scripts/setup_v4_venv.sh
scripts/audit_mojibake.py                # mojibake heuristic, refined
scripts/filter_v3_grounded_via_db.py     # v3 grounded → v4 carry via DB labels
scripts/assemble_v4_carryovers.py        # terse pruning + mc/brief_qa copy
scripts/assemble_v4_english_replay.py    # multi-seed TULU dedup
scripts/build_dev_guard_v4.py
scripts/synthesize_anti_template_v4.py   # 600 items REAL chunks, ran on k2
scripts/synthesize_refusal_v4.py         # opt-in, not run for v4-minimal
scripts/distill_grounded_v4.py           # opt-in, not run for v4-minimal
scripts/format_sft_v4.py
scripts/pull_tulu_subset.py              # ALLOW pattern fix + per-source cap + shuffle
src/bin/{crawl,audit_html,audit_urls}.rs # Track B handoff
src/crawler_v2/                          # full Track B crawler (50 files, 13k LOC)
tests/crawler_v2_*.rs                    # 24 integration test files
eval/dev_guard_v4.jsonl                  # 56-item curated dev set (force-added; eval/ is gitignored)
```

### Modified

```
scripts/eval_groundedness.py             # AnthropicShape thinking:disabled fix
scripts/eval_sft_v1.py                   # batched chat + score_one + max_tokens 800→500
scripts/train_sft_v1.py                  # val_loss always logged, best/ no overwrite, --checkpoint-steps
```

### Generated artifacts (gitignored, on disk)

```
corpora/sft_v4_train.jsonl              # 13,062 records, ready for upload
corpora/sft_v4_val.jsonl                # 685 records
corpora/sft_v4_grounded_v3carry.jsonl   # 8,542 records (filtered from v1 grounded)
corpora/sft_v4_anti_template.jsonl      # 600 records (REAL chunks)
corpora/sft_v4_english_replay.jsonl     # 1,549 records (numinamath_tir)
corpora/sft_v4_grounded_terse.jsonl     # 58 records (pruned from v3 terse)
corpora/sft_v4_brief_qa.jsonl           # 300 records (v2 carryover)
corpora/sft_v4_mc.jsonl                 # 443 records (v2 carryover)
corpora/sft_v4_tulu_seed{42,200}.jsonl  # source pulls (1,549 records combined)
```

### Commits this session

```
b34dc06  v4 prep: pinned env, mix composer, retrieval-realistic distill, trainer fixes
55b8a20  v4 prep: refusal + anti-template generators, dev_guard, carryover assembly
22464eb  Track B crawler handoff + mojibake-classifier fix
1bd38ef  Mojibake audit script — refined heuristic (embedded Latin + doubled matras)
5ee1833  pull_tulu_subset: enforce ENGLISH_SOURCE_ALLOW + per-source cap + shuffle
af3517c  SFT v3a: results writeup + batched eval + judge thinking-disabled fix
c1ba8b8  v4-minimal: filter v3 grounded via SQLite labels, repoint composer
ca180df  v4-minimal: english_replay assembler + dev_guard refresh + composer pointers
```

---

## 8. Total spend

| Item | $ |
|---|---:|
| Mojibake corpus rebuild (k2 only, no API) | 0 |
| Anti-template generation (DeepSeek) | ~2 |
| Multi-seed TULU pulls (HF, free) | 0 |
| **v4 data prep total** | **~$2** |
| v4 training (when launched, est.) | ~$7-9 |
| **v1+v2+v3a+v3 mojibake fix+v4 prep** | **~$38** |

Versus codex's original v4 plan at ~$13 API: **saved ~$11** by switching to v4-minimal+.

---

## 9. What's unresolved

These are real and may matter for v4 outcomes:

1. **English replay is math-only.** Codex spec'd 1200 math + 1200 instruction + 400 MC + 200 reasoning. We have 1549 math. If GSM8K recovers but Belebele drops or Roman-NE relapses, this is a likely cause — the model loses general English instruction-following because the only English we replayed was math word problems. Mitigation: add an explicit-subset pull script (no_robots, sciriff, ai2_arc) as a separate task.
2. **Refusal slice is still 2500 v3-carry phrase-teaching.** Codex called this out: "synthetic empty/partial refusal mostly teaches the phrase, not the decision boundary." If end-to-end refusal_correct (after BM25 gate) doesn't hit ≥80%, the next move is fixing the gate (Track B §4), NOT spending on retrieval-realistic refusal SFT — per codex.
3. **Server-side BM25 relevance gate not shipped.** Track B's v3-fix.md §4 — this is the missing piece for the end-to-end refusal target. If we want to actually validate the codex pass criterion, the gate has to land on k2 production first.
4. **Trainer behavioral abort gates not implemented.** Codex spec'd "step-400 gate: GSM8K-50 ≥40%, Roman degen ≤1, abort if violated." The trainer has wall-clock + NaN abort hooks but not behavioral. Deferred — if v4-minimal+ trains cleanly, behavioral gates aren't needed; if it doesn't, we'll see it in train_v4.log.
5. **`mc` and `brief_qa` slices are under codex targets.** 443 vs 550 and 300 vs 700. format_sft_v4 warns but doesn't bail. Top-ups would be ~$1 if the v4-minimal eval suggests we need more.

---

## 10. Decision tree after v4 eval

```
v4 eval results land
│
├── ALL gates pass (codex criterion §3)
│       → ship v4 to production, retire v2 adapter on k2
│       → schedule cleanup of distill_grounded_v4 + synthesize_refusal_v4
│         scripts (no longer needed)
│
├── Roman-NE degen >1 OR GSM8K <50%
│       → English replay was insufficient — add direct-subset pulls
│         (no_robots, ai2_arc) and re-train
│
├── Composer-only refusal_correct LOW but wrongly_refused LOW too
│       → BM25 gate is the missing piece — implement Track B §4 BEFORE
│         spending on retrieval-realistic refusal SFT
│
├── wrongly_refused HIGH
│       → grounded train/serve mismatch IS biting — escalate to
│         distill_grounded_v4 (the script is already in the tree at
│         scripts/distill_grounded_v4.py, ~$5-7 to run)
│
└── chrF <18 OR URL recall <0.90
       → grounded slice quality issue — check that filter_v3_grounded
         retention wasn't too aggressive; loosen if needed
```
