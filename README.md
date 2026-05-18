# PreVillage / SpeakGov

## Public Links

| Artifact | Link | Notes |
| --- | --- | --- |
| Live web helpdesk | <https://helpdesk.ampixa.com> | Same backend as the kiosk and WhatsApp bridge. |
| Kiosk voice mode | <https://helpdesk.ampixa.com/kiosk> | ASR -> resolver -> RAG -> TTS loop. |
| Nepali ASR demo | <https://huggingface.co/spaces/voidash/nepali-fastconformer-demo> | FastConformer experiment for Nepali speech. |
| Nepali TTS demo | <https://huggingface.co/spaces/ampixa/real-nepali-tts> | Piper/real-Nepali TTS demo. |
| TTS model | <https://huggingface.co/ampixa/real-nepali-v0.2-kala> | Public Kala voice model. |
| Source repository | <https://github.com/voidash/previllage> | This repo. |

The Gemma SFT adapters and GGUF builds are staged on Hugging Face. They should
be made public for a submission or external review before relying on the links
from a public writeup.

## Start Here For Reviewers

- Project map and code layout: [docs/README.md](docs/README.md)
- Links to share publicly: [docs/LINKS.md](docs/LINKS.md)
- Fine-tuning and eval trail: [docs/finetuning/README.md](docs/finetuning/README.md)
- Product/RAG contract: [docs/architecture/SERVICE_NAVIGATOR_MODUS_OPERANDI.md](docs/architecture/SERVICE_NAVIGATOR_MODUS_OPERANDI.md)
- Corpus release plan: [docs/CORPUS_RELEASE_PLAN.md](docs/CORPUS_RELEASE_PLAN.md)

## What It Does

SpeakGov(previllage) turns a raw citizen question into a service frame before trying to
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


## Repository Layout

```text
docs/                           Project docs, runbooks, submission notes
  README.md                     Judge-readable map of the repo
  LINKS.md                      Public links and release-status checklist
  finetuning/README.md          Fine-tuning path, evals, scripts, artifacts
server/                         FastAPI RAG, resolver, voice, admin endpoints
frontend/                       React/Vite web, chat, interview, WhatsApp, kiosk UI
whatsapp/                       Baileys bridge for real WhatsApp text/audio
scripts/                        Crawling, eval, SFT, voice, deployment utilities
src/                            Older Rust PDF/corpus pipeline
recipes/                        Crawl/source recipes for government sites
assets/                         Curated public screenshots and diagrams
corpora/                        Small public source registry files only
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

