# PreVillage / SpeakGov

PreVillage started from a simple failure mode: the law is public, the form is
public, and the office exists. What is not public is the route through the
office.

Nepal is moving hard toward e-governance, but much of the UX still stops at
"there is a form online." Citizens still visit an office only to learn that the
form was wrong, the counter was different, the document needed a ward
recommendation first, or the phone number on the website no longer works. The
route is held by middlemen, officers, and people who already failed once.

PreVillage, also deployed as SpeakGov, is a government-service navigator for
Nepal. It is not a generic RAG Q&A bot. It does intake first, asks compact
follow-up questions when a case is ambiguous, routes retrieval by the user's
actual need, cites sources, includes contacts when available, and says when the
evidence is missing.

![A hidden route through four offices](assets/previllage-writeup-gallery/submission/hidden_route_four_offices.png)

## Public Links

| Artifact | Link | Notes |
| --- | --- | --- |
| Live web helpdesk | <https://helpdesk.ampixa.com> | Same backend as the kiosk and WhatsApp bridge. |
| Kiosk voice mode | <https://helpdesk.ampixa.com/kiosk> | ASR -> resolver -> RAG -> TTS loop. |
| Nepali ASR demo | <https://huggingface.co/spaces/voidash/nepali-fastconformer-demo> | FastConformer experiment for Nepali speech. |
| Nepali TTS demo | <https://huggingface.co/spaces/ampixa/real-nepali-tts> | Piper/real-Nepali TTS demo. |
| TTS model | <https://huggingface.co/ampixa/real-nepali-v0.2-kala> | Public Kala voice model. |
| Source repository | <https://github.com/voidash/gemma-god> | This repo. |

The Gemma SFT adapters and GGUF builds are staged on Hugging Face. They should
be made public for a submission or external review before relying on the links
from a public writeup.

## What It Does

SpeakGov turns a raw citizen question into a service frame before trying to
answer. The frame includes intent, service, office or jurisdiction, document,
situation, language, missing slots, and the source type that should be trusted
for that question.

That matters because "how do I get citizenship in Sankhuwasabha?" should not
produce a generic AI checklist. The assistant should ask which municipality or
case type if that changes the route, prefer the District Administration Office
and ward-level sources when relevant, include contact paths, and avoid invented
facts.

The same pipeline is used by:

- Web chat for source-backed typed answers.
- Live kiosk mode for local voice intake.
- A real Baileys WhatsApp bridge for text and audio messages.
- Admin/interview tooling for collecting practical office knowledge.

![WhatsApp follow-up flow](assets/previllage-writeup-gallery/submission/whatsapp_annotated_followup_flow.jpg)

## Architecture

![SpeakGov architecture](assets/graphics/speakgov_architecture_tldraw_board_2560x1440.png)

The core pattern is resolver-first RAG:

1. Input arrives from chat, WhatsApp, or kiosk voice.
2. ASR output and Roman-Nepali text are normalized enough for retrieval.
3. The planner resolves the service frame and decides whether to ask a
   follow-up, retrieve, or use a deterministic source extractor.
4. The source router chooses the right authority lane. Contact questions prefer
   office contact pages and staff directories. Fee/date/form questions prefer
   dated official pages. "Where do I go?" questions prefer local office routing
   and practical counter notes.
5. Retrieval builds a source pack from official government pages and reviewed
   tacit sources.
6. Gemma composes from the source pack, preserving language and citing source
   IDs instead of inventing URLs.

## Corpus

The corpus is treated as infrastructure, not a folder of scraped text. The
initial seed came from the Digobikas government website directory:
<http://digobikas.gov.np/2019-08-21-05-14-56>.

The latest hardening snapshot used for the hackathon pass had:

- 1,071 source records.
- 46,051 live documents.
- 272,718 searchable chunks.

The hard parts were not the happy path. They were broken government sites,
legacy Nepali PDF encodings, scanned notices, pages that fetched but produced
no chunks, duplicated PDFs that looked like coverage, and source ranking that
had to distinguish a legal fact from a practical counter note.

The older Rust pipeline in `src/` still handles classification, legacy-font
conversion, OCR hooks, crawling, chunking, and BM25 indexing for Nepali
government PDFs. The current demo stack adds the Python/FastAPI navigator,
SQLite/FTS5 retrieval, voice workers, and frontend.

## Evidence-Path Repair

Self-healing in this project means evidence-path repair. If the system finds a
missing, stale, weak, or not-searchable source, that is turned into crawl,
parse, review, or interview work. Official pages provide legal facts. Named and
reviewed officers, staff, and citizens who completed a process provide
practical facts such as rooms, timing, common rejections, and working contacts.

| Evidence repair | WhatsApp evidence loop |
| --- | --- |
| ![Evidence repair board](assets/graphics/self_healing_evidence_repair_board_2560x1440.png) | ![WhatsApp self-heal flow](assets/previllage-writeup-gallery/submission/whatsapp_self_heal_flow.png) |

The WhatsApp outreach demo is now disabled by default for real officers. The
bridge remains available for citizen chat and voice, but automatic officer
messaging is a demo-only mode.

## Why Gemma

Government facts should not be memorized into model weights. Contacts, fees,
office holders, forms, and URLs change. Those facts belong in retrieval,
structured source packs, or deterministic extraction.

Gemma is useful here because it can run openly and locally for the parts that do
need a language model:

- Repair noisy Nepali, Roman-Nepali, and ASR text.
- Plan the service case before retrieval.
- Ask the next compact follow-up question.
- Preserve the user's language.
- Compose answers from evidence without turning every office into a GPU cloud
  customer.

## Fine-Tuning Path

The first continuous pre-training experiment taught the wrong lesson. More
Nepali tokens did not automatically produce a public-service navigator, and CPT
on an instruction model damaged chat behavior.

The SFT path then moved through several product failures:

- `v2`: 11,896 supervised records from Reddit, Hello Sarkar-style questions,
  government snippets, and synthetic supervision. Roman-Nepali improved, but
  refusal and routing were brittle.
- `v3a`: 13,763 records. More rows did not fix the task design and general
  capability regressed.
- `v5`: Gemma 4 E4B looked good on loss but failed product checks. It invented
  a phone number, answered ambiguous citizenship questions generically,
  misrouted manpower complaints, and missed direct contact questions.
- `v6`: the useful direction. Train planner/composer behavior over provided
  source packs instead of asking the model to be a naked factual chatbot.

`v6.4` split the task into planner JSON, answerability JSON, and final
composition. On the `quick48` source-backed eval it reached:

- URL recall: `0.94`.
- Wrong refusals: `2/48`.
- Source-ID citations: `45/48`.
- Roman-Nepali degeneration, loops, or mojibake: `0/10`.

That made it the first serious RAG-backed composer candidate. It is not meant
to answer from memory. It is meant to sit behind resolver, retrieval, and source
routing.

![SFT iteration reality](assets/previllage-writeup-gallery/submission/sft_iteration_reality.png)

![v6 progression metrics](assets/previllage-writeup-gallery/submission/v6_progression_metrics.png)

## Evals

Evals became the product spec. A pass was not "the answer sounds fluent." A
pass meant the system did the job:

- Ask for municipality or office details when location changes the route.
- Avoid Hindi drift for Nepali users.
- Cite source IDs from the provided source pack.
- Route manpower-agency fraud to labor/foreign-employment authorities.
- Answer contact questions from contact pages or staff directories.
- Refuse only when retrieved evidence truly does not support the answer.

Live pipeline smoke gates used during the final pass:

- Service pipeline audit: `8/8`.
- Navigator smoke audit: `7/7`.
- RAG query audit: `15/15`, with one expected refusal.
- Bad citations: `0`.
- Generation loops: `0`.
- Slow-generation failures in the smoke set: `0`.

![RAG eval gates](assets/previllage-writeup-gallery/submission/rag_service_eval_gates.png)

## Voice, WhatsApp, And Kiosk

Voice is part of the UX, not an add-on. Many users should be able to speak a
messy question, have ASR produce imperfect text, let Gemma repair and plan it,
retrieve sources, and hear a short answer back.

The ASR work uses OpenSLR54 plus additional collected data for a roughly
509.54-hour Nepali training base and a FastConformer finetuning ladder. The TTS
work uses Piper Plus and a real Nepali Kala voice model, including a 3,000+
utterance collection from a consented speaker plus OpenSLR43.

![Kiosk voice mode](assets/previllage-writeup-gallery/submission/kiosk_voice_mode.png)

## Edge Gemma

Quantized Gemma E2B through `llama.cpp` ran on a Raspberry Pi 5. A short-prompt
smoke measured around 7.5 tokens/sec. That does not mean the Pi should run the
full national RAG, ASR, and TTS stack. It means a local office can keep a small
open model nearby for intake and composition while heavier crawl, training, and
index-building work happens centrally.

![Gemma on Raspberry Pi](assets/previllage-writeup-gallery/submission/pi_gemma_llamacpp_smoke.png)

## Repository Layout

```text
server/                         FastAPI RAG, resolver, voice, admin endpoints
frontend/                       React/Vite web, chat, interview, WhatsApp, kiosk UI
whatsapp/                       Baileys bridge for real WhatsApp text/audio
scripts/                        Crawling, eval, SFT, voice, deployment utilities
src/                            Older Rust PDF/corpus pipeline
recipes/                        Crawl/source recipes for government sites
assets/                         Curated public screenshots and diagrams
SERVICE_NAVIGATOR_MODUS_OPERANDI.md
RAG_HARDENING_STATUS.md
SFT_V6_PLANNER_COMPOSER.md
PI_E2B_LLAMA_CPP_RUNBOOK.md
```

Raw videos, temporary renders, local auth state, databases, checkpoints, and
model weights are intentionally not committed.

## Local Development

Backend:

```bash
python -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn pydantic httpx

export DB_PATH=/path/to/corpus/index.db
export MODEL_ID=mlx-community/gemma-4-e4b-it-bf16
export ADAPTER_PATH=voidash/gemma-helpdesk-v6-4-e4b-g6e-qlora-seed42
python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
```

Frontend:

```bash
cd frontend
pnpm install
pnpm dev
```

WhatsApp bridge:

```bash
cd whatsapp
npm install
HELP_DESK_BASE_URL=http://127.0.0.1:8000 npm start
```

Rust corpus tools:

```bash
cargo build --release
cargo test
```

## Verification Commands

```bash
python scripts/service_navigator_pipeline_audit.py
python scripts/navigator_smoke_audit.py
python scripts/rag_query_audit.py
python scripts/rag_retrieval_audit.py
python scripts/corpus_health_audit.py
```

Pi/`llama.cpp` smoke:

```bash
scripts/pi_llamacpp_smoke.sh /path/to/model.gguf
```

## Cost Reality

For May 2026 month-to-date, project-attributable AWS GPU-ish EC2 compute was
about `$363.63`. Training EBS volumes added roughly `$38.48`. The product
design is not that every office buys an L40S. Heavy crawl, training, and eval
work can be centralized; office-facing intake can run on smaller open models
plus retrieved source packs.

## Limits

SpeakGov is not a legal authority. It is an evidence-backed navigator. Users
should verify action-taking details such as fees, forms, deadlines, eligibility,
and office contacts with the relevant government office before acting.

The system should refuse or ask a follow-up when the source path is weak. A
mostly-right government chatbot can still send someone to the wrong line.

## License

GPL-3.0-or-later. See `LICENSE`.

This project vendors `third_party/npttf2utf/`, a GPL-3.0 legacy-font mapping
table. Because the Rust converter compiles that table into the binary through
`include_str!`, the combined work is released under GPL-3.0-or-later.
