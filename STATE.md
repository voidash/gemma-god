# State of the project — Nepal Government Helpdesk

*Snapshot: 2026-04-29. Companion to STORY.md (narrative), PIPELINE.md (RAG design), CRAWLER.md (crawler v2), BENCHMARKS.md (eval reference), DOCUMENT.md (engineering log).*

---

## 1. What we're building

A small, **deployable** Nepal-government helpdesk knowledge system. Citizens type questions in Devanagari Nepali, Roman-Nepali, English, or code-mixed; the system answers with **citations to the actual `.gov.np` page** that supports each claim, or refuses cleanly when no authoritative source covers the question.

Concretely:

```
            ┌────────────────────────────────────────────┐
            │  user question (Devanagari / Roman / EN)   │
            └────────────────┬───────────────────────────┘
                             │
                  ┌──────────▼──────────┐
                  │   Hybrid retrieval  │   BM25 + vector over chunks
                  │   (top-K = 5)       │   from gov.np corpus
                  └──────────┬──────────┘
                             │
            ┌────────────────▼──────────────────┐
            │  Composer LLM                     │
            │  ─────────────                    │
            │   • SFT v1: Gemma 4 E4B-IT + LoRA │   ← deployed today
            │   • Demo path: Sonnet 4.6 / Kimi  │     (API-side composer)
            └────────────────┬──────────────────┘
                             │
                ┌────────────▼────────────┐
                │  Grounded answer +      │
                │  inline [URL] citations │
                │  OR clean refusal       │
                └─────────────────────────┘
```

The composer **must** cite the chunk URL after each factual claim and refuse — not hallucinate — when no chunk meaningfully addresses the question. Refusal templates are language-matched ("मलाई यो प्रश्नको आधिकारिक स्रोत भेटिनँ" / "Yo prashnako adhikarik srot bhetina" / "I cannot find an authoritative source").

**Demo scope**: Jiri Municipality (`jirimun.gov.np`) plus ~10 federal parents (MOHA, MOFA, NRB, Nepal Police, IRD, DOFE, EDCD, etc.).

---

## 2. Architecture in detail

### 2.1 The crawler (built, working)

Lives under `src/crawler_v2/`. Replaces an earlier Python prototype with a Rust daemon that's been running on the k2 Mac Studio (M2 Ultra, 64 GB) under launchd.

| Module | Job |
|---|---|
| `types.rs` | Source / Document / FetchEvent / PollCycle / RepairItem dataclasses |
| `store.rs` | rusqlite Store + schema (CURRENT_VERSION = 3), idempotent migrations |
| `blobs.rs` | content-addressable blob store (raw fetches), sidecars in `extracted/` |
| `fetch.rs` | async fetcher (rustls, gzip/brotli, timeout caps, per-domain throttle) |
| `parse.rs` | content-type → ParsedHtml \| Binary \| Unsupported; PDF via `pdf_extract` with `pdftotext` fallback (`pdf_extract` panics on certain Nepal-gov budget PDFs — caught with `catch_unwind`) |
| `shell_detect.rs` | JS-shell heuristic (script_count ≥ 1 + low text) — flags SPA pages we can't render today |
| `chunk.rs` | passage chunker + repetition filter |
| `text_extract.rs` | Document → text |
| `language.rs` | Devanagari / Latin / Mixed / Mojibake-suspected |
| `legacy_fonts.rs` | Preeti / Kantipur / Sagarmatha → Unicode (gov.np still ships Preeti PDFs) |
| `legacy_import.rs` | Python prototype JSONL → SQLite |
| `recipe.rs` | Sparse-overrides recipe loader. Default crawl policy in `default_for`; per-source files (`recipes/jirimun_gov_np.json` etc.) only set fields that deviate. |
| `frontier.rs` | priority frontier (score + depth tiebreak) |
| `url.rs` | canonicalize + classify + score + same_site |
| `health.rs` | rolling-window verdict (Phase 6) |
| `repair.rs` | `react_to_verdict` + `dispatch_one` + `dry_run` + `apply` (Phase 6) |
| `agent.rs` | `AgentRuntime` trait; subprocess wrapper around claude-code / opencode / codex |
| `daemon.rs` | tick loop, PID lock, SIGTERM, `CrawlerTickHandler` (Phase 7) |
| `pool.rs` | multi-source orchestration, semaphore concurrency cap |
| `worker.rs` | per-source crawl loop |
| `registry.rs` | `corpora/sources_tiered.jsonl` → SQLite |

**Production state on k2** (`/Volumes/T9/gemma-god/`):

| Table | Rows |
|---|---|
| `sources` | 877 |
| `documents` | 12,278 |
| `chunks` | 101,022 |
| `poll_cycles` | 1 (Jiri only — daemon not yet `launchctl`-loaded for full production) |
| `source_health` | 877 |

### 2.2 Retrieval (designed, not yet built)

`PIPELINE.md` covers it: hybrid BM25 + vector over the chunks table, returning top-5 with URL + text. The vector path is pending (LanceDB embedder, task #29.2). For the demo, BM25 alone is enough — Jiri-scope corpus is small.

### 2.3 The composer (where SFT v1 lives)

Two paths:

- **API-side composer**: Sonnet 4.6 or Kimi K2.6 via the Anthropic-shape Messages API. Used to build the gold eval set and to be the *fallback* if the on-device model isn't ready.
- **On-device composer**: SFT v1 = `voidash/gemma-helpdesk-seed42` — LoRA r=64 over `google/gemma-4-E4B-it`. Trained 2026-04-28/29.

The same `SYSTEM_GROUNDED` prompt is used in training, eval, and serving — so the model sees the strict-grounding contract identically across the lifecycle.

### 2.4 Eval pipeline

Two scripts, two purposes:

- **`scripts/eval_groundedness.py`** — runs *any* backend (Meridian/Kimi/DeepSeek/HF) against the 167-item gold set; reports URL recall, refusal correctness, chrF, hallucination, per-language and per-category breakdowns.
- **`scripts/eval_sft_v1.py`** — adds a model-loading layer (HF transformers + PEFT) plus 5 more parts: LLM-as-judge groundedness via DeepSeek, Belebele 50, GSM8K-en 30, Roman-NE degeneration check, side-by-side baseline-vs-SFT for human review.
- **`scripts/nepali_capability_eval.py`** (new today) — the published Nepali benchmarks (Belebele 60, INCLUDE-base-44 Nepali 60, FLORES-200 NE↔EN 30 each, XLSum 15) plus per-benchmark wallclock. Used to verify SFT didn't damage general Nepali capability.

---

## 3. The training journey — CPT, then the pivot to SFT

### 3.1 Plan A: CPT on Nepali (failed)

**The plan** (PLAN.md, the historical plan): take Gemma 3 4B base, do continued pre-training (CPT) on a curated Nepali corpus (Wikipedia NE + r/Nepal scraped + IndicXlit-romanized text), then a small SFT pass on top.

**CPT v1 failed by a textbook mechanism**, not mysteriously:

> Only ~9.5% of CPT training data was instruction-format. The base model lost its chat behavior entirely — Belebele dropped, FLORES dropped, the model started generating raw Nepali text without responding to prompts.

This is well-known: continued pre-training on too-non-instructional data = catastrophic forgetting of the instruct fine-tune that the base model already had. BENCHMARKS.md §3.2 has the numbers.

### 3.2 Plan B: pure RAG + SFT on top of Gemma 4 IT

We pivoted because CPT v1 had no upside under the constraint we're under (small data, small compute, controllable outputs). The new plan:

1. **Build the corpus first**, not the model — crawler v2 + curation.
2. **Use a strong instruct base** (Gemma 4 E4B-IT, released 2026-04-02) instead of trying to teach Nepali to a base model.
3. **SFT only** — no CPT — to teach the helpdesk *task* (cite + refuse), not the *language* (the IT model already speaks Nepali well per its baseline).
4. **Build the eval set first**, before any SFT iteration. You can't iterate on SFT without something to measure.

### 3.3 The current SFT v1 (delivered today)

| | |
|---|---|
| Base | `google/gemma-4-E4B-it` (8 B params with embeddings, ~4.5 B effective via Per-Layer Embeddings) |
| Method | LoRA via PEFT, with rank-stabilized scaling (rsLoRA) |
| r / α | 64 / 128 |
| Target modules | q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj |
| Trainable | 162 M / 8.1 B = 2.0% |
| Optimizer | AdamW 8-bit |
| Schedule | LR 1e-4, cosine + 100-step warmup |
| Mix | per-device 2, grad-accum 8 (effective 16), max-seq 2048 |
| Memory | bf16 + gradient checkpointing + `expandable_segments:True` (L40S 48 GB) |
| Hardware | 1× NVIDIA L40S, AWS g6e.xlarge |
| Best step | step 500 (~epoch 1) |
| Wall time | 2.5 h |

Adapter: https://huggingface.co/voidash/gemma-helpdesk-seed42 (now public).

---

## 4. Papers we leaned on

We did three reading passes and documented findings in `FINETUNE_RESEARCH.md`. The papers that actually shaped decisions:

### Method choices

- **rsLoRA** ([Kalajdzievski 2023, 2312.03732](https://arxiv.org/abs/2312.03732)) — rank-stabilized LoRA with α/√r scaling. We use it because at r=64, vanilla LoRA's α is hard to tune; rsLoRA makes the update magnitude scale-invariant in r.
- **QLoRA + NF4 quantization** ([Dettmers 2023](https://arxiv.org/abs/2305.14314)) — read, decided not needed: L40S 48 GB has enough headroom for bf16 + LoRA r=64. We pay a bit of memory but get cleaner gradients.
- **DoRA** ([Liu 2024](https://arxiv.org/abs/2402.09353)) — magnitude/direction decomposition of LoRA. Strong on math, less clearly better on language tasks at our scale. Held in reserve for v2 if rsLoRA plateaus.

### Data strategy

- **MURI reverse-instruction** ([Köksal 2024, 2409.12958](https://arxiv.org/abs/2409.12958)) — given a passage, generate the *question* it answers, then turn into an SFT triple. We adapted this for the corpus we have: from a gov.np chunk, ask DeepSeek to reverse-engineer the citizen question + grounded answer + skip flag. This is how `sft_v1_grounded.jsonl` got built.
- **MedInjection-FR** ([2603.06905](https://arxiv.org/abs/2603.06905)) — for medical QA, native+translated training mix (NAT+TRAD) consistently beats native-only. Our analog: native_ne_alpaca (1.5k Devanagari) + grounded_distilled (6.5k Sonnet/DeepSeek) — two teacher styles. Also: their LLM-as-judge correlated r=0.61 with human experts, justifying our DeepSeek judge.
- **GemMaroc** (5k SFT for Moroccan Arabic), **Lebanese AI** (3k), **Romanized Nepali** (9k) — comparable low-resource SFT runs. They all trained at 3k–10k SFT. We landed at 9k. The literature said don't go bigger without seeing diminishing returns first.
- **Anti-forgetting English replay** — common practice (TULU, Aya, etc.). 15–20% English replay is standard. We used 15% (1.5k from TULU 3 SFT mixture, filtered out `oasst1_converted` because it smuggled in non-English).

### Architecture / inference (Gemma 4 specifics)

- **Per Layer Embeddings (PLE)** in Gemma 4 — additional learnable embeddings per layer, frozen for v1 since LoRA targets attention + MLP projections only.
- **Shared KV Cache** in Gemma 4's late layers — relevant for inference memory at long contexts; doesn't affect SFT.

### Eval methodology

- **Belebele** ([Bandarkar 2023](https://arxiv.org/abs/2308.16884)) — 122-language MC reading comprehension. We use the `npi_Deva` config.
- **INCLUDE-base-44** ([Romanou 2024](https://arxiv.org/abs/2411.19799)) — Cohere Labs' 44-language regional knowledge MC. The Nepali subset is professional certification + region-specific knowledge — a stronger test than Belebele.
- **FLORES-200** ([NLLB Team 2022](https://arxiv.org/abs/2207.04672)) — translation. We use `openlanguagedata/flores_plus` (the legacy `facebook/flores` paired config is brittle).
- **XLSum** ([Hasan 2021, ACL](https://aclanthology.org/2021.findings-acl.413/)) — multilingual summarization. Nepali split has 725 test items.
- **chrF / chrF++** ([Popović 2015](https://aclanthology.org/W15-3049/)) — character n-gram F-score, tokenization-free, the right primary metric for multilingual generation.

---

## 5. Eval set creation

The 167-item gold set is the *prerequisite* for everything else. Without it, you can only measure regression on Belebele/FLORES, never improvement on the actual task. Pipeline:

### 5.1 Question pool

| Source | Count | How |
|---|---|---|
| r/Nepal scrape | 101k cleaned posts (`reddit_nepali.jsonl`) | `scripts/reddit_ingest.py` from arctic_shift archive |
| Gov-keyword filter | 4,217 | `scripts/filter_gov_questions.py` — kw + interrogative |
| Question filter | 1,898 | `corpora/reddit_gov_questions.jsonl` |
| Sonnet classifier (gov topic + answerable + good-faith) | 112 yes_* | `scripts/classify_gov_questions.py` (prompt-batched, ~$3 of Sonnet) |

### 5.2 Build & enrichment

- `scripts/build_groundedness_eval.py` — match each question to top-K retrieved chunks via the existing BM25 over the corpus. Generate a draft answer + draft citations.
- `scripts/generate_grounded_eval.py` — use Sonnet to flesh out answers with strict-grounding rules.
- `scripts/enrich_refusals.py` — for refusal items, fall back to verified gov office contacts (`corpora/gov_office_contacts.json` — 13 entries: MOHA, MOFA, nepalpassport, DOTM, IRD, DOFE, customs, nepalpolice, plus Hello Sarkar 1111). When the model refuses, the response should give the citizen the next concrete step (call this hotline, visit this office), not a dead-end "I don't know."
- `scripts/clean_mojibake.py` — remove conjoined Latin+Devanagari tokens (e.g., "bhएको" — looks like data corruption from copy-paste between scripts).
- `scripts/merge_eval.py` — combine all slices into `eval/gov_helpdesk_v1_unified.jsonl` (167 review-ready).

### 5.3 Human review

- `scripts/review_eval.py` — terminal review tool; abandoned because monospace font can't render Devanagari well.
- **`scripts/review_web.py`** — browser-based UI (chosen approach). Operator types `a` (approve) / `e` (edit) / `d` (drop) / `s` (skip) / `q` (quit) per item. Output: `eval/gov_helpdesk_gold_v1.jsonl` with 169 unique IDs across 177 records (last-write-wins).

### 5.4 Final composition

| Type | Count | Notes |
|---|---|---|
| grounded | 73 | RAG-style; gold answer + gold URLs; chrF / URL recall measured |
| refusal | 91 | No source meaningfully addresses; gold = enriched refusal text + Hello Sarkar fallback |
| ungrounded_attempt | 3 | Edge cases — partial info, model should hedge |
| **total** | **167** | |

### 5.5 Baselines run on the gold set

- **Sonnet 4.6** (via Meridian local OAuth proxy): URL recall 84%, refusal correct 99%, hallucinated 1%. (`eval/reports/sonnet-4-6-baseline.json`)
- **Kimi K2.6** (via Moonshot): statistically tied with Sonnet, 2.7× faster. Used as the cheaper composer fallback for the demo.

The Sonnet baseline is what SFT v1 is trying to approach. Sonnet is the ceiling; we want the on-device model to get within ~10 points across metrics.

---

## 6. Mass data generation

Three distinct generation jobs, three different teachers:

### 6.1 Sonnet 4.6 — gold eval answers (~$3 spent)

For the 167-item eval set: the strict-grounding system prompt + retrieved chunks → gold answer with citations. Sonnet's strength: it follows the "cite each claim, refuse if unsupported" contract reliably, which is exactly the contract we want the small model to learn. Failures (~5% of items) were caught in human review.

### 6.2 Kimi K2.6 — independent baseline (~$5 spent)

Same task, same chunks, different teacher. Used to verify that our Sonnet gold isn't just memorizing Sonnet's idiosyncrasies. Kimi's outputs are statistically indistinguishable from Sonnet on URL recall and refusal correctness, with one exception: Kimi cites with bare `[1] URL` at the end vs Sonnet's inline `[https://...]` brackets — handled by `extract_citations` in `eval_groundedness.py` (catches both forms).

### 6.3 DeepSeek V4-Flash — SFT v1 grounded slice (~$5 spent)

This is where the bulk of training data came from. **Reverse-instruction at scale**:

```
For each chunk c in our corpus:
  Ask DeepSeek to:
    1. Read this gov.np chunk
    2. Reverse-engineer the citizen question this chunk answers
    3. Write a grounded answer citing the chunk URL
    4. Or, if the chunk isn't useful for any reasonable question,
       skip with skip=true + skip_reason
```

We used DeepSeek V4-Flash (not V4-Pro):

- V4-Pro had `thinking-on` by default which ate the token budget; turning thinking off (`thinking:{type:disabled}`) helped but was still slow.
- V4-Flash is ~2× faster than V4-Pro and quality is fine for this task.

Per-source allocation favored sources where the corpus was rich (low skip rate): `jirimun_gov_np`, `moha_gov_np`, `edcd_gov_np`, `nrb_gov_np`. Result: **6,553 items kept** (out of ~14k attempted; ~46% kept after the skip filter).

**One bug we fixed**: 24% of items had a literal `[URL]` in the answer text — DeepSeek interpreted the example placeholder in our prompt literally instead of using the actual chunk URL. Post-processing substitution `[URL] → [chunks[0].url]` was safe because each reverse-instruction record has exactly one source chunk.

### 6.4 Two anti-forgetting / style-anchor slices

| Slice | Records | Source | Why |
|---|---|---|---|
| `native_ne_alpaca` | 1,500 | [Saugatkafley/alpaca-nepali-sft](https://huggingface.co/datasets/Saugatkafley/alpaca-nepali-sft) | A second teacher's Devanagari style. Stops the model from drifting toward DeepSeek's stylistic biases. Saugatkafley is translated Alpaca but provides 52k records of real Devanagari surface form, which is what the anchor slice needs. |
| `english_replay` | 1,500 | [allenai/tulu-3-sft-mixture](https://huggingface.co/datasets/allenai/tulu-3-sft-mixture) | Anti-forgetting English replay (15% of train mix, per literature). Filtered to `flan_v2_converted`, `no_robots`, `numinamath`, etc. — explicitly *excluding* `oasst1_converted` which is multilingual and would dilute the English signal. |

The Anudesh-Nepali alternative we initially tried had only ~0.4% Nepali coverage and a bad regex misclassifying Hindi/Marathi as Nepali — switched to Saugatkafley.

---

## 7. SFT v1 results (the headline)

### 7.1 Training trajectory

| step | overall val | grounded | english_replay | native_ne |
|---|---|---|---|---|
| 0 (initial) | 1.622 | 0.853 | 3.139 | 3.583 |
| 200 | 0.807 | 0.501 | 1.479 | 1.501 |
| 400 | 0.791 | 0.505 | 1.384 | 1.481 |
| **500 (best)** | **0.767** | **0.494** | **1.339** | **1.421** |
| 600 | 0.845 | — | — | — |
| 800 | 0.826 | — | — | — |

- **52% val loss reduction** from initial.
- All three slices learn — including English (3.14 → 1.34, *no* catastrophic forgetting).
- Val starts creeping back up at step 600/800 — early-stop region.

### 7.2 Eval on `gov_helpdesk_gold_v1` (167 items)

| Metric | SFT v1 | Target | Verdict |
|---|---|---|---|
| URL recall (grounded) | **0.89** | ≥ 0.70 | ✅ |
| Wrongly refused (grounded) | **0%** | ≤ 10% | ✅ |
| Belebele Nepali (n=50) | 58% | ≥ 55% | ✅ |
| GSM8K-en | 50% | (no regression target) | ✅ — English replay preserved |
| LLM judge groundedness | 4.20 / 5 | — | strong |
| LLM judge citation correctness | 5.00 / 5 | — | perfect on the 5-item subset |
| LLM judge verdict CORRECT% | 80% | — | strong |
| **Refusal correct (refusal items)** | **0%** | ≥ 90% | ❌ — see below |
| Roman-NE degeneration | 2 / 10 | ≤ 1 | ❌ |
| chrF (grounded vs gold) | 22.09 | (no target — informational) | low surface match despite right URLs |

**3 pass / 2 fail signals.** The refusal-correct = 0% is the dominant failure: the model never refuses on the 91 refusal items. Cause: the SFT mix has zero refusal training examples, so the model learned "given chunks, write an answer with citations" and applies this even when the chunks are empty or don't address the question. URL recall stays high *because* the citation pattern was learned, but the question of "should I answer or refuse?" was never posed during SFT.

### 7.3 Hard-won bugs (all surfaced during this run)

1. **`huggingface-cli` deprecated on the AMI**. The DLAMI's `huggingface_hub ≥ 0.34` removes the legacy CLI entirely — only `hf` works. Cost: $0.09 + 3 min wasted on a bootstrap that died at the data-pull step.
2. **`Gemma4ClippableLinear` blocks PEFT**. Gemma 4 wraps every Linear in a custom inference-clipping module; PEFT's LoRA injector only recognises stock `nn.Linear`. Fix: walk the model and replace each wrapper with its inner `linear` attribute *before* LoRA injection (and again, mirror the unwrap in the eval before calling `PeftModel.from_pretrained`).
3. **`apply_chat_template(tokenize=True)` returns version-dependent types** — sometimes `list[int]`, sometimes a dict, sometimes a list of `Encoding` objects. The trainer's invariant ("prompt_ids is a strict prefix of full_ids") broke silently and 9076 of 9076 records were skipped as `no_assistant`. Robust fix: `tokenize=False` to format text, then `tokenizer.encode(text, add_special_tokens=False)` since the template emits its own BOS + turn markers.
4. **CUDA OOM at step 0**. Gemma 4 BF16 + LoRA r=64 + per-device-batch 4 + max_seq 2048 = 41.79 GB used, can't allocate 6.22 GB more on L40S 48 GB. Fix: per-device-batch 2, grad-accum 8, gradient checkpointing, `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True`. Effective batch stays 16.
5. **The step-1000 mini-gen self-test gate had a bug** — the prompt-from-tokens reconstruction produced empty exception messages, the gate fired on `['generation error: ', 'generation error: ', ...]` and aborted training prematurely. The step-500 best checkpoint was already saved, so we lost epochs 2–5 but kept the best adapter.
6. **Cloud-init scripts inherit a minimal PATH** — `hf`, `python` are not visible unless the script `source`s `/opt/pytorch/bin/activate` first. The post-eval watcher's `hf upload` calls failed silently because of this.

### 7.4 Total spend

~$13 across all attempts (failed + successful runs + two eval sessions). Stopped instance preserves the EBS volume with the cached 16 GB Gemma 4 model + the trained adapter + all logs — restartable for v2 iteration without re-downloading anything. EBS preservation cost: ~$0.50/day.

---

## 8. Where we are right now

**Public artifact**: https://huggingface.co/voidash/gemma-helpdesk-seed42 — adapter + tokenizer + chat template + SUMMARY.md + per-item eval JSONs.

**Nepali capability bench** — apples-to-apples on base E4B and SFT v1 (same prompts, same sampling, same n):

| Benchmark | Ref E4B | Our base E4B | SFT v1 | Δ (SFT − base) |
|---|---|---|---|---|
| Belebele (npi_Deva, n=60) | 85.0% | 71.7% | 60.0% | **−11.7** |
| INCLUDE-base-44 (Nepali, n=60) | 43.3% | 43.3% | 33.3% | **−10.0** |
| FLORES-200 NE→EN (chrF, n=30) | 61.72 | 58.99 | 46.96 | **−12.03** |
| FLORES-200 EN→NE (chrF, n=30) | 54.08 | 50.23 | 39.49 | **−10.74** |
| XLSum Nepali (ROUGE-L, n=15) | 12.68 | 11.53 | 10.67 | −0.86 |
| Wallclock total | 110.2s | 283.4s | 911.7s | +628.3s |

Reading:
- **Our base ≈ reference E4B** on every metric except Belebele (13-pt gap, methodology). INCLUDE matches exactly. The reference numbers come from a different prompt/sampling pipeline; our pipeline is what was used for both columns of the SFT comparison, so the Δ is honest.
- **SFT v1 vs our base**: ~11-pt regression on general Nepali across reading comprehension, knowledge, and translation. XLSum barely moved (−0.86) — that's the closest task to the SFT objective.
- **SFT v1 is 3.2× slower** at inference. The SFT model is more verbose (it's been trained to write structured grounded answers) even on MC tasks where "reply with the letter" is the instruction.

The trade-off: SFT v1 gained URL recall (0.89) and refusal-attempt-correctness (no wrongful refusals) on the gov-helpdesk task, at the cost of ~11 points general Nepali capability. Acceptable for a *helpdesk-only* deployment; v2 should aim to recover some of this.

Files: `eval/nepali_capability/{sft_v1_seed42,e4b_base}.json` on HF.

---

## 9. SFT v2 — the obvious next move

The v1 result told us exactly what v2 needs to fix. Required:

1. **Add a refusal slice (~1000–1200 items, ~11% of train)**, broken into:
   - ~600 *empty-retrieval* (gov-domain question, `Sources: (no candidate sources surfaced)`) → refusal in the question's language.
   - ~300 *off-domain* (non-gov question + irrelevant chunks) → refusal.
   - ~200 *partial* (chunks have some info but don't fully answer) → `[unverified]` hedge or refusal.
   - Language distribution: 40% Devanagari / 30% Roman-NE / 30% English.
2. **Fix or remove the step-1000 mini-gen gate**. Val-loss + per-slice tracking already catches divergence; the gate's only purpose was a sanity check on actual generations and it's never worked correctly.
3. **Roman-NE expansion** — the Saugatkafley anchor is Devanagari-only. Adding ~500 Roman-NE items (transliterate gov questions, or use Reddit Roman-NE prompts) should fix the 2/10 degeneration.

Optional (if time):
4. Train fewer epochs — val bottomed at step 500 (~epoch 1) and crept up after. 2–3 epochs is the sweet spot.
5. Try LR=5e-5 with shorter warmup — avoid the warmup loss spike at step 80.

**Expected SFT v2 cost**: ~$10 for one seed. If refusal fix lands, another ~$10–15 for seeds 137/271 in parallel for a publishable mean+std table.

---

## 10. Doc index (for continuity)

| File | Read when |
|---|---|
| **STATE.md** (this file) | starting fresh / writing the report |
| `STORY.md` | want the plain-English narrative including the CPT-v1 failure |
| `PIPELINE.md` | designing or changing the RAG pipeline / retrieval |
| `CRAWLER.md` | touching `src/crawler_v2/*` |
| `BENCHMARKS.md` | running or interpreting evals |
| `DOCUMENT.md` | historical context for a specific decision / engineering log |
| `PLAN.md` | mostly historical — original training-first plan |
| `FINETUNE_RESEARCH.md` | the 5-pass paper-reading log + recipe v0.4 |
| `README.md` | high-level pitch |
| `CLAUDE.md` | project context for the next agent session |

Memory: project-level memories live in `~/.claude/projects/-Users-cdjk-github-llm-gemma-god/memory/`. Currently saved: project notes for the helpdesk goal, AWS stop-don't-terminate preference, full SFT v1 results breakdown.
