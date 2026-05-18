# v3-fix.md — what v2 deploy on k2 exposed, in priority order for v3 training

This is a punch-list for the agent training v3. v1 (E4B base, 9.5% IT data, 0/91
refusal, 22.09 chrF) and v2 (E2B base, 11% refusal slice, 12/91 refusal, 13.42
chrF, more verbose) are both live on HF. v2 was deployed to k2 (Mac Studio, MPS,
transformers+peft) on 2026-04-29 and walked through the demo path end-to-end via
the web client. Most of the bugs surfaced are NOT model bugs — they are corpus,
retrieval, and prompt-construction bugs that v3 training cannot fix. Treat them
as upstream blockers and fix in the right place.

The rest of this document is what to fix and where.

---

## P0 — what v2 deploy actually broke at the demo

### 1. Cross-language retrieval is asymmetric. English/Roman-NE queries miss

The corpus is 877 .gov.np sources, mostly Nepali. FTS5 token-OR search ranks well
for Devanagari technical queries because the keywords are lexically specific.
For English queries the same words ("citizenship", "certificate", "lost",
"Nepal") match thousands of chunks, and BM25 surfaces NHRC speech books and
Raute community reports instead of the MOHA citizenship-replacement directive.

Verified live, 2026-04-29:

| Query | Top gov.np chunk retrieved | Right answer? |
|---|---|---|
| `नागरिकता प्रमाणपत्र हराएमा के गर्ने?` | `nia.gov.np/.../660fedd08d720_1712319952.pdf` (the actual MOHA directive) | ✅ |
| `How do I replace a lost citizenship certificate in Nepal?` | NHRC chairperson speech book on CEDAW + foreigners + 4M Nepalis in India | ❌ |

The English query retrieved 3 gov chunks, NONE of which discussed replacement
procedure. The model then template-completed from the only useful source (a
tacit claim) and looped.

**Three fix paths, ranked by effort:**
- **(quickest, demo-grade)** Bilingual keyword expansion in `Retriever.search`.
  Build a small bilingual map for ~50 gov-domain anchor terms (citizenship →
  नागरिकता, license → लाइसेन्स, passport → राहदानी, …). When the query language
  detector says English/Roman-NE, OR-append the Devanagari translations to the
  FTS query before BM25.
- **(proper)** Multilingual sentence-transformer retrieval. The Phase 29.2
  embedder + LanceDB store is on the roadmap but unbuilt. v3 should ship it —
  paraphrase-multilingual-mpnet-base-v2 or LaBSE both handle ne/en cleanly.
- **(orthogonal)** Translate the query at the server before retrieval. Use
  IndicTrans2 or the model itself in a 1-shot translate-then-retrieve pre-step.
  Adds latency. Worse than the embedding path.

Whichever path is taken, **v3 training data construction must use the same
retrieval pipeline** as inference. Today the SFT teacher (Sonnet/Kimi) gets
chunks from `scripts/format_sft_v2.py` that are Devanagari-keyworded. At
inference English queries get different chunks. That's how the train/serve mismatch
silently grew. Fix retrieval first, then re-distill.

### 2. PDF mojibake is in the chunks, not in the model

Many gov.np PDFs were Preeti/Kantipur/Sagarmatha-encoded and the chunker only
half-decoded them. Live evidence from one chunk shipped to the v2 model on
2026-04-29:

```
ficate and क्ष् could नभत mथ copy only if क्ष् signed an बााष्मबखष्त saying
क्ष् had not obtained mथ citizenship certificate before
```

The Latin chars are real ASCII, the Devanagari chars are real Unicode, but
they're co-mingled because the PDF used a Preeti font for some glyphs and ASCII
for others. `src/legacy_fonts.rs` handles full Preeti→Unicode but it doesn't
fire on this hybrid pattern.

**Audit (run on k2 prod DB 2026-04-30, 101,022 chunks, strict heuristic =
Latin alpha adjacent to Devanagari char in same token):**

- 13,738 chunks affected (**13.6% of corpus**)
- Top 4 sources hold ~75% of the mojibake:

| Source | Mojibake chunks | Share within source |
|---|---:|---:|
| nhrcnepal.org | 5,206 | 15.5% |
| nrb.org.np | 3,043 | 21.2% |
| nia.gov.np | 1,154 | 10.3% |
| ag.gov.np | 1,128 | 13.1% |
| jirimun.gov.np | 416 | 25.4% |
| dmgnepal.gov.np | 174 | 29.0% |

(Audit script at `scripts/probe_bm25.py` was a one-off; the audit was a 30-line
ad-hoc script — re-create from the heuristic above when needed for v3.)

**Fix in this order:**
- For the 4 high-volume sources above (nhrc/nrb/nia/ag), re-extract from the
  source PDF with `pdftotext -layout` (Poppler) plus a stricter Preeti→Unicode
  pass. Bin is at `/Volumes/T9/gemma-god/bin/pdftotext` on k2. Each is a
  whole-source rebuild, not a chunk-by-chunk patch.
- For PDFs where the source font is identifiable but the chunker missed it,
  add the font name to `legacy_fonts.rs::detect_legacy`.
- For PDFs where text extraction is unreliable (rasterized scans), schedule
  Tesseract OCR via `src/ocr.rs` (currently unused since Phase 29).

This is corpus hygiene work. v3 cannot work around mojibake chunks at training
time and inference time both — the evidence the model is given has to be clean.

### 3. Tacit corpus URLs are bare domains. The model can't distinguish claims

Every tacit claim in `corpora/tacit/processed/jirimun/...jsonl` carries
`office.domain = "jirimun.gov.np"`. The server constructs the citation marker
as `f"https://{office.domain}"` → all 40 tacit claims end up tagged
`[https://jirimun.gov.np]`. When 3 tacit claims appear in the prompt and the
model is told to cite, it correctly notes that the only bracketed URL pattern
is `[https://jirimun.gov.np]` and uses it for everything — including claims it
cobbled together by template-completion that don't match any tacit claim.

**Fix:** per-claim citation marker. Two options:

- **Pseudo-ID form** like `[tacit:jirimun:nagarikta:agent_001:001]`. The web
  client doesn't auto-link these (which is fine — they're not URLs), but the
  source card below the bubble shows the deep-link URL of the underlying claim
  source. The marker becomes a true 1-to-1 with the chunk.
- **Per-service deep-link** like `https://jirimun.gov.np/services/nagarikta`
  (synthetic but meaningful). Easier UI integration but encodes the office
  taxonomy in URL paths that don't match real gov.np page structures.

Pseudo-ID form is cleaner. v3 SFT teacher distillation should produce answers
that cite tacit claims with the pseudo-ID and gov chunks with the real URL.

### 4. Server-side relevance gate. No threshold on BM25 today

`Retriever.search` returns top-K regardless of score. `TacitRetriever` returns
top-K regardless of token-overlap. The composer accepts whatever it gets. So
the OOD probe (`बेन्जामिन फ्रैंकलिन को थिए?`) returned 3 NHRC chunks (low
relevance) and the model confabulated a biography with a suicide year that
never happened. v2's 12/91 refusal slice did NOT save us at inference because
the slice never trained the model to interpret "low BM25 score" as a refusal
signal — it trained on the absence of a relevant chunk.

**Fix:** server-side gate before composition. If `max(bm25_score)` is below a
threshold (FTS5 bm25 returns negative; closer-to-0 = better; needs calibration
on a held-out set), refuse with the canned response in the appropriate language
and skip generation entirely. Latency win plus safety win.

Calibrate the threshold on the v3 groundedness eval set (task #32 in CLAUDE.md
— still unbuilt). Don't ship a guessed number.

---

## P1 — v3 SFT mix changes (the actually-training-related items)

### 5. Refusal slice was undersized at 11%. Bump to 25–30%

v2 trained 1100 refusal examples against 6553 grounded examples (11% refusal
share). Loss went from 5.69 → 0.43 — the format was learned. But at inference
the 6553 "always answer" prior dominates and refusal fires 13/91 instead of
intended ~90/91. The mechanism transfers; the proportion is wrong.

For v3 target 25–30% refusal share. That's ~2k refusal items against ~6k
grounded items. Categories to cover (more than v2's empty/partial/off_domain):

- **OOD entirely** (history of Benjamin Franklin, recipe for daal bhat,
  geopolitics) — current
- **OOD-but-plausible-citation** (someone asks about a Nepal gov topic that
  isn't in the corpus, retrieval surfaces tangentially-related chunks). This
  is what failed at the demo.
- **Wrong-language-source** (Roman-NE question, only Devanagari chunks
  retrieved that don't answer it). This needs to cooperate with the bilingual
  retrieval fix from §1, otherwise v3 won't see realistic train/serve parity.
- **Mojibake-only-source** (chunk is Preeti remnants and not interpretable —
  refuse rather than confabulate). Do this only AFTER §2 fixes the corpus, so
  the fraction is small.

### 6. Anti-template-completion slice. New for v3

Today's failure mode (verified live): when only one tacit claim is on-topic,
v2 paraphrases that claim, then auto-extends to neighboring claims by
substitution. From the demo:

```
[from prompt]   "For a lost citizenship certificate, ... municipality, ...
                 recommendation for a duplicate"
[v2 output]     "For a lost citizenship certificate, ... municipality, ...
                 recommendation for a duplicate [https://jirimun.gov.np].
                 For a lost passport, ... municipality, ... recommendation
                 for a duplicate [https://jirimun.gov.np]."
```

The "lost passport" sentence is fabricated by analogy. Lost passports go to
the Department of Passports, not the municipality. There is no source for this
in the prompt. The model invented it AND cited the unrelated tacit URL.

v3 needs ~300 negative items: prompt has 3 sources covering topic A, question
asks about both A and B, teacher answer covers A and refuses on B with
`[unverified]` or refusal phrasing. Today this slice is zero.

### 7. Anti-verbosity slice. v2 is 70% more verbose than v1

Same query, v1 produced 425 chars, v2 produced 724 chars. eval-time chrF
22.09 → 13.42. The mc and brief_qa slices in v2 didn't fully cancel the
grounded slice's verbose-output regression. v3 should:

- Add ~200 "be terse" items: same gold answer, 30% shorter; teacher prompted
  for "minimum-words" output
- At eval time, drop default `max_new_tokens` from 800 → 500 (already noted in
  v2-results memory)
- Optionally add a length-penalty in generation kwargs (-0.1 on Gemma's logit
  bias, after testing on MPS — the 4 GB NDArray cap from §10 may apply)

### 8. Drop the step-1000 mini-gen gate. Same bug fired in v2

v1 hit it. v2 hit it. The `prompt_msgs_text` reconstruction is broken in a way
that's not worth chasing. Best checkpoint was step-600 in both runs anyway.
Just remove the gate for v3.

---

## P2 — corpus / pipeline / infra hygiene

### 9. The crawler daemon isn't loaded into launchctl on k2

`ops/install_daemon.sh` is built but not run in production. Currently the only
poll cycle in the prod DB is the manual Jiri ad-hoc poll. Either:

- Run `install_daemon.sh` on k2 before v3 training data refresh starts (so
  fresher chunks are available)
- Or accept that the corpus is frozen at the 2026-04-28 snapshot and ship v3
  on that snapshot

If freezing: snapshot `index.db` to `index.db.v3-baseline.bak` first.

### 10. MPS NDArray > 4 GB cap blocks several HF generation processors

Empirical from 2026-04-29: on Gemma 4 (vocab 256K) bf16 on MPS,
`repetition_penalty=1.2 + no_repeat_ngram_size=5` triggers
`MPSCore/Types/MPSNDArray.mm: total bytes of NDArray > 2**32`. Both processors
together (and `repetition_penalty` alone at 1.3) hit it. `do_sample=True,
T=0.3, top_p=0.9` is the only generation config that ran cleanly to completion
without crashing.

If v3 inference also targets MPS (Mac Studio), use sampling. If v3 targets
Pi 5 GGUF (llama.cpp), this MPS bug is irrelevant — llama.cpp has its own
generation kernels and doesn't use HF logits processors.

### 11. v2 GGUF exists. Pi 5 deploy is unblocked

`voidash/gemma-helpdesk-v2-e2b-seed42/gguf/` has both Q4_K_M (3.26 GB) and
bf16 (8.84 GB). Pi 5 8GB target is Q4_K_M. The `pi@<pi-tailnet-ip>` Tailscale
node lost its SSH password during 2026-04-29 demo prep — recovery is the
`init=/bin/sh` trick on the SD card's `cmdline.txt`. If v3 ships a GGUF, the
Pi deploy is one llama-server invocation.

### 12. Sentence-level dedup post-processor is in `server/main.py`

Function: `_dedup_sentences` at server/main.py:435 (after the latest edit).
Splits on `[।.!?]\s+`, lowercase-strips trailing `[URL]` markers, drops
duplicates, cuts the answer at 2 consecutive duplicates (loop detection).

This is a band-aid that should NOT be present in v3 inference if v3's training
fixes the underlying repetition. Remove the call from `Composer._generate`'s
last line and confirm v3 doesn't loop. If it does, the SFT mix didn't solve
the repetition problem and the band-aid stays.

---

## What I'd actually do, top-to-bottom

1. **Before any v3 training**: fix §1 (bilingual retrieval) and §2 (mojibake
   chunks). Without these, v3's distilled training data will have the same
   train/serve mismatch v2 had.
2. **Then build the groundedness eval set** (task #32 in CLAUDE.md, still
   unbuilt). 100 items, half Devanagari half Roman-NE/English, half in-corpus
   half OOD, golden URLs marked.
3. **Run §4 (relevance gate) calibration on that eval set** — pick the BM25
   threshold from data, not a guess.
4. **Fix §3 (per-claim tacit URLs)** — touch the JSONL records and the
   `TacitRetriever._build_index` method.
5. **Then v3 SFT**: §5 (refusal 25–30%), §6 (anti-template, ~300 items), §7
   (anti-verbosity, ~200 items). LoRA r=64 rsLoRA on E2B base. ~$10–15
   distillation cost.
6. **Eval after every checkpoint**. The fast_eval harness exists. The
   groundedness eval from step 2 is the new addition.
7. **Once v3 is stable**: remove §12 (sentence dedup band-aid), remove §10's
   sampling-only constraint if HF MPS bug is fixed in transformers ≥4.45.

Cost estimate: ~$35 distillation + eval, no GPU rental needed (MPS or H100
spot). About 1 week of agent-time if §1 and §2 are tractable on the existing
corpus.

---

## What landed 2026-04-30 — Track A server-side fixes (no training touched)

These are demo-grade band-aids that ship the v2 adapter on k2 cleanly. They do
NOT solve the underlying training-side issues (§5–§8) and SHOULD be revisited
once v3 is trained. Locations are all in `server/main.py` unless noted.

| Item | Location | Status |
|---|---|---|
| `BILINGUAL_ANCHORS` map (63 terms) for FTS expansion | `server/main.py:60–140` | shipped |
| `Retriever.search` query-token expansion using anchors | `server/main.py:215–245` | shipped |
| Bracketed gov.np URLs in prompt (symmetry with tacit) | `build_user_prompt` | shipped |
| Per-claim tacit markers `[<url>#tacit-N]` | `build_user_prompt` (tacit loop) | shipped |
| Sentence dedup post-processor (exact + Jaccard ≥ 0.80 near-dup) | `_dedup_sentences` | shipped |
| Sampling generation config (T=0.3, top_p=0.9) | `Composer._generate` | shipped |
| Anti-extrapolation rule #7 in system prompt | `SYSTEM_GROUNDED` | shipped, partial fix |
| `LOG_PROMPT=1` env flag for prompt+raw-output logging | `Composer._generate` | shipped |

**Verified live (2026-04-30):**
- Devanagari in-scope `नागरिकता प्रमाणपत्र हराएमा के गर्ने?` → 5 distinct sentences
  citing `nia.gov.np/.../660fedd08d720_1712319952.pdf` (correct MOHA directive). Demo-grade.
- Roman-NE in-scope `Mero nagarikta haraayo, ke garne?` → 5 distinct Roman-NE sentences,
  citations diverse across `tacit-1/tacit-2`. Demo-grade.
- English in-scope `How do I replace a lost citizenship certificate in Nepal?` →
  4 useful sentences with correct per-claim citations, but 5th sentence still
  template-extrapolates to "lost passport" with fabricated alphabetical document
  list. The template-completion bias from §6 needs SFT, not prompt fix.
- OOD `Who was Benjamin Franklin?` → still no refusal, fabricates "American
  polymath" with NRB citation. Better than v1+v2's "suicide year 1948"
  fabrication, but unsolved. Needs §5 (refusal slice 25-30%).

**What this does NOT fix and why:**
- **Bilingual map is a 63-term hack**, not multilingual semantic retrieval.
  Queries that don't contain any anchor term still fall through to raw FTS.
  Must be replaced by Phase 29.2 embeddings before v3 distillation
  (`scripts/generate_sft_grounded.py` selects chunks directly, but the
  inference path uses the retriever — train/serve split widens otherwise).
- **Per-claim tacit markers** put fragments on a bare-domain URL. The v3
  pseudo-ID form (`[tacit:office:service:claim_id]`) from §3 is cleaner and
  doesn't pretend the URL deep-links to anything.
- **Sentence dedup** is post-hoc cleanup. Real fix is anti-template SFT
  (§6) and anti-verbosity SFT (§7).
- **Anti-extrapolation rule** in the system prompt fires when the model
  notices it. v2 only sometimes notices. v3 needs ~300 anti-template SFT
  items to actually internalize this.
- **No relevance gate** because the BM25 score distribution doesn't cleanly
  separate OOD English (`-16.658`) from in-scope English (`-22 to -38`) —
  the latter is "more negative = better-ranked," but English in-scope often
  has more rare-token bonus than Devanagari in-scope (`-17`). Calibration
  needs the v3 groundedness eval set to set a per-language threshold.

**Files changed today, summary diff against pre-2026-04-30 master:**
- `server/main.py` — bilingual map, search expansion, per-claim markers,
  bracketed gov URLs, dedup, sampling, anti-extrapolation rule, prompt logging
- `v3-fix.md` — this file (audit numbers + landed-fixes section)

---

## Where to look for evidence in the repo

- Live demo trace + raw model output: server.log on k2 with `LOG_PROMPT=1`
- Retrieval mismatch on English query: this document, §1 table
- Mojibake chunk example: this document, §2 quote
- Tacit URL collapse: prompt dump in §3, also `corpora/tacit/processed/jirimun/.../agent_001.jsonl` line 1 `office.domain`
- v2 looping: snapshot at `web/speakgov/.playwright-mcp/page-2026-04-29T12-17-05-952Z.yml` (12× repeat of "national ID card")
- MPS NDArray cap crash: server.log on k2, search for `MPSNDArray.mm:788`
- v2 eval headline numbers: `SFT_V2_RESULTS.md` and the project-memory
  `project_sft_v2_results.md`
- v1 eval headline numbers: `SFT_V1_RESULTS.md` and `project_sft_v1_results.md`
