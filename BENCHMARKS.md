# BENCHMARKS.md — what we evaluate, why, and the numbers we have

Reference doc for the eval harness used by the Nepal-gov-helpdesk Gemma
project. Whenever we train a checkpoint (CPT, SFT, distillation), we run
this suite and write a report.

The harness lives in two scripts:

| Script | Use when |
|---|---|
| `scripts/nepali_baseline.py` | full-baseline run (Belebele n=200, FLORES n=100). Slow (~2 h). One-time per base model. |
| `scripts/fast_eval.py` | iteration eval (Belebele n=50, FLORES n=30). ~10 min. Run after every checkpoint. |

Outputs land under `/Volumes/T9/gemma-god/eval/`. JSON for machines, `.md`
report for humans.

---

## 1. Benchmark inventory

| # | Benchmark | What it measures | Source | n (full / fast) | Random baseline | Score |
|---|---|---|---|---|---|---|
| 1 | Belebele Nepali | general Nepali reading comprehension | `facebook/belebele` (`npi_Deva` split) | 200 / 50 | 25% (4-choice MC) | accuracy |
| 2 | FLORES-200 en→ne | translation quality, English to Nepali | `openlanguagedata/flores_plus` (dev) | 100 / 30 | n/a | chrF++ + BLEU |
| 3 | FLORES-200 ne→en | translation quality, Nepali to English | same | 100 / 30 | n/a | chrF++ + BLEU |
| 4 | Roman-Nepali qualitative | gov-procedure handling in Roman-NE | hand-written prompts | 10 / 10 | n/a | manual + degen-loop count |

**None of these benchmarks measure the actual deployed task** (RAG-grounded
answer composition over Nepal-gov chunks). See [§4 Known gaps](#4-known-gaps).

---

## 2. Per-benchmark detail

### 2.1 Belebele Nepali

**Format**: passage (Nepali), question (Nepali), four answer choices, model
must reply with a single letter `A`/`B`/`C`/`D`.

**Prompt template** (`scripts/fast_eval.py:80-87`):

```
Read the passage in Nepali and answer the question by choosing the
single best option (A, B, C, or D). Reply with only the letter.

Passage: <flores_passage>

Question: <question>

A) <mc_answer1>
B) <mc_answer2>
C) <mc_answer3>
D) <mc_answer4>

Answer:
```

**Real sample**:

> **PASSAGE** (on accordion playing — generic encyclopedic content):
> सबै नोटहरू राम्ररी पल्टाउँदा - आफ्ना औँलाहरूले धेरै अनावश्यक गति नबनाउने प्रयास गर्दै तपाईंको हात सम्भव भएसम्म शान्त छ भनि सुनिश्चित गर्नुहोस्। ... अकोर्डियनमा, अतिरिक्त आवाज प्राप्त गर्न, तपाईं थप दवाब वा वेगका साथ बेलोजको प्रयोग गर्नुहुन्छ।
>
> **QUESTION**: अनुच्छेदनुसार, कुन सुझावलाई राम्रोसँग अकोर्डियोन बजाउने सही सुझाव मानिँदैन?
>
> A) थप भोल्यूमका लागि, कुञ्जीहरू थिचे जत्तिकै बल बढाउनुहोस्
> B) आफ्नो सहनशक्ति बचाउनका लागि धेरै अनावश्यक गतिविधि नगर्नुहोस्
> C) हातलाई सहज राखेर सावधानीका साथ धुन निकाल्नुहोस्
> D) थप भोल्यूम बढाउनका लागि तपाईंले बेल्लोहरू सञ्चालन गरे जत्तिकै गति बढाउनुहोस्
>
> **GOLD**: A

**What it actually measures**: can the model read a paragraph of encyclopedic
Nepali and pick the best answer to a comprehension question. **Topics are
generic** (accordion, ancient history, geology, etc.) — _not_ Nepal-specific,
_not_ gov-specific. A high score means the model reads Nepali; it tells us
nothing about whether it can answer gov-helpdesk questions.

### 2.2 FLORES-200 en→ne

**Format**: one English sentence in, one Nepali translation out. Score is
chrF++ (character-n-gram F-score) at corpus level.

**Prompt template** (`scripts/fast_eval.py:117`):

```
Translate the following English sentence into Nepali (Devanagari).
Reply with only the translation.

English: <src>

Nepali:
```

**Real sample**:

> **EN src**: Crime, and ill-will toward foreigners in general, is virtually unknown in Greenland. Even in the towns, there are no "rough areas."
>
> **NE ref**: अपराध र सामान्यतया विदेशीहरूप्रति खराब इच्छा, ग्रीनल्याण्डमा लगभग अज्ञात छ। शहरहरूमा पनि, त्यहाँ कुनै "असभ्य क्षेत्रहरू" छैनन्।
>
> **NE hyp** (Gemma 3 4B IT baseline): ग्रीनलैंडमा अपराध, र विदेशीहरूमा सामान्यतया दुर्व्यवहार लगभग अज्ञात छ। यहाँसम्म पनि, शहरहरूमा पनि "कठोर क्षेत्र" छैनन्।

**What it measures**: en→ne translation fluency. **Source domain is general
news / encyclopedic content from FLORES** — not Nepal-domain content.

### 2.3 FLORES-200 ne→en

Same dataset, reverse direction. Strictly easier for the model (Nepali
input → English output is closer to the model's training distribution).

**Real sample**:

> **NE src**: (the Nepali sentence above)
>
> **EN ref**: (the English source above)
>
> **EN hyp**: Crime and generally ill will towards foreigners are almost unknown in Greenland. Even in cities, there are no "uncivilized areas."

### 2.4 Roman-Nepali qualitative

**Format**: 10 hand-written prompts in Roman-NE about Nepal-gov procedures.
No reference answer. Eval is **manual inspection + automated
degeneration-loop detection** (a response that repeats the same opening
≥3× counts as `degen`).

**The full prompt set** (`scripts/fast_eval.py:134-145`):

```
1.  mero nagarikta banauna ko lagi kun office janu parcha?
    (which office should I go to to get my citizenship made?)
2.  passport renew garna kaha janu parcha?
    (where should I go to renew passport?)
3.  company registration kasari garne?
    (how to do company registration?)
4.  PAN number kasari banaune?
5.  driving license ko lagi k k chaine?
6.  VAT ra PAN ma k farak cha?
7.  nagarikta certificate hareyo, kaha janu parcha?
    (citizenship certificate is lost, where to go?)
8.  jagga ko malpot kaha tirne?
    (where to pay land tax?)
9.  bachhako janmadarta kasari garne?
    (how to register a child's birth?)
10. online tax file kasari garne?
```

**This is the only benchmark whose domain matches the demo.** It's also the
smallest and least structured.

---

## 3. Score history

### 3.1 Baseline — Gemma 3 4B IT (no fine-tuning)

Source: `eval/gemma3_nepali_baseline.md` (full run, 2026-04-18).

| Benchmark | n | Metric | Score |
|---|---|---|---|
| Belebele Nepali | 200 | accuracy | **63.0%** |
| FLORES-200 en→ne | 100 | chrF++ | **38.15** |
| FLORES-200 en→ne | 100 | BLEU | **6.94** |
| FLORES-200 ne→en | 100 | chrF++ | **55.88** |
| FLORES-200 ne→en | 100 | BLEU | **28.79** |
| Roman-NE qualitative | 10 | degen-loop count | _not measured at baseline; qualitatively coherent_ |

A 4B model at 63% on Belebele is **not bad** — random is 25%, and the
benchmark is non-trivial. The translation numbers are the floor.

### 3.2 CPT v1 (LoRA, step 10 000) — REGRESSED

Source: `eval/fast_eval_cpt_v1_step10000.json`.

| Benchmark | Baseline | CPT v1 | Δ |
|---|---|---|---|
| Belebele Nepali | 63.0% (n=200) | 52.0% (n=50) | **−11 pts** |
| FLORES en→ne chrF++ | 38.15 | 33.46 | −4.7 |
| FLORES ne→en chrF++ | 55.88 | 55.09 | ≈ flat |
| Roman-NE degen-loop | (coherent) | **3 / 10 outright degenerate**; rest mostly echo the prompt | catastrophic |

**Roman-NE failure example** (CPT v1 response to "passport renew garna kaha janu parcha?"):

```
Passport renew garna kaha janu parcha?
Passport renew garna kaha janu parcha?
Passport renew garna kaha janu parcha?
... (~20 times)
```

**Diagnosis** (per `STORY.md`): catastrophic forgetting of instruction-format
behavior. Of the CPT training data, only **9.5% had instruction format**;
the other 90.5% was raw Nepali prose. The raw-text training swamped the
chat signal and the model unlearned how to answer questions. This is a
known textbook failure mode of CPT-on-IT (a late-2024 paper reported the
same effect: continued-pretraining Llama 3 on Nepali dropped MMLU 61%→35%).

**Plan B (documented, not yet run)**: CPT from `gemma-3-4b-pt-bf16` (the
**pretrained**, not instruction-tuned variant) — no chat behavior to forget.
Then SFT with Alpaca-NE + chat data on top, as a separate stage. Total
~11 h on k2.

---

## 4. Known gaps

The current suite measures **general Nepali fluency**, not the **actual
deployed task**. The task is: given a Nepali question + retrieved chunks
from the gov corpus, produce a grounded cited answer. None of the four
benchmarks above test this.

| What we should measure | Status |
|---|---|
| Grounded answer over retrieved chunks | **MISSING** — no eval set exists. Spec'd as task #32 ("100-item human-reviewed eval set"). |
| Hallucination / refusal when chunks don't cover a claim | **MISSING** |
| Code-mixed input (Roman-NE + Devanagari + English in one query) | **MISSING** |
| Citation correctness (does the model cite real URLs from the chunks?) | **MISSING** |
| Domain-specific Nepali (gov / legal / bureaucratic register) | **MISSING** — Belebele is generic, FLORES is news |

**Implication for SFT**: until we have a groundedness eval set, an SFT run
can only be evaluated against Belebele/FLORES/Roman-NE. Those will tell us
whether the SFT broke fluency (regression check) but not whether it _improved
the demo task_. Building the groundedness eval set is the prerequisite for
measurable SFT iteration.

---

## 5. How to run

### Full baseline (slow, run once per base model)

```sh
python scripts/nepali_baseline.py \
    --out /Volumes/T9/gemma-god/eval/<model_label> \
    --n-belebele 200 \
    --n-flores 100
```

### Fast eval (after every checkpoint)

```sh
python scripts/fast_eval.py \
    --base mlx-community/gemma-3-4b-it-bf16 \
    --adapter /Volumes/T9/gemma-god/checkpoints/<run>/<step>_adapters.safetensors \
    --label <run_label>
```

Both scripts:
- expect `HF_TOKEN` env var for gated FLORES download
- write JSON results to `eval/<label>.json`
- write a `.md` summary alongside (full baseline only)

### Reading results

```sh
# Belebele score over time:
jq '.label, .belebele_nepali.accuracy' /Volumes/T9/gemma-god/eval/fast_eval_*.json

# Roman-NE degen count:
jq '.label, .roman_nepali.degen_count' /Volumes/T9/gemma-god/eval/fast_eval_*.json
```

---

## 6. What to add before serious SFT iteration

1. **Groundedness eval set** (task #32) — 100 hand-reviewed
   `(question, retrieved_chunks, expected_answer_with_citation)` tuples.
2. **Refusal eval** — 20 questions whose answers don't appear in the
   corpus; correct response is "I don't have a source for this." Measure
   refusal rate.
3. **Code-mixed input set** — 30 prompts mixing Roman-NE / Devanagari /
   English in realistic ways (filtered from r/Nepal).
4. **Citation-correctness check** — automated scoring of whether cited
   URLs in the answer actually appear in the retrieved chunks.

Once those exist, an SFT run produces a single comparison table that says
either "ship this" or "regressed, don't ship."
