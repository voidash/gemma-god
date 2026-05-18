# PreVillage Docs

This repository keeps the product source at the root and puts the engineering
trail under `docs/`.

## Judge Path

If you are reviewing the project, read in this order:

1. [Root README](../README.md) - problem, product, architecture, eval headline.
2. [Links](LINKS.md) - public demo/model/data links and release status.
3. [Datasets](../datasets/README.md) - public dataset artifacts and release boundary.
4. [Benchmarks](../benchmarks/README.md) - public eval data and smoke gates.
5. [Fine-tuning trail](finetuning/README.md) - how Gemma was trained and judged.
6. [Raspberry Pi edge runbook](raspberrypi.md) - Gemma E2B via `llama.cpp`.
7. [Public architecture](architecture/PREVILLAGE_PUBLIC_ARCHITECTURE.md) -
   resolver-first RAG, voice, WhatsApp, human loop.
8. [Service navigator contract](architecture/SERVICE_NAVIGATOR_MODUS_OPERANDI.md)
   - the product behavior that drives implementation.
9. [Corpus release plan](CORPUS_RELEASE_PLAN.md) - what should be published as
   a dataset and what should stay private/redacted.

License: project-authored public artifacts use
[CC-BY-4.0](../LICENSE). Third-party components keep their upstream licenses;
see [NOTICE.md](../NOTICE.md).

## Code Layout

| Path | Purpose |
| --- | --- |
| `server/` | FastAPI service: resolver, retrieval, composer, voice, admin, WhatsApp bridge integration. |
| `frontend/` | React/Vite web app: chat, kiosk, interview intake, WhatsApp QR/status UI. |
| `whatsapp/` | Real Baileys bridge for WhatsApp text and voice messages. |
| `scripts/` | Training, eval, crawl, RAG audit, Pi, ASR/TTS, deployment utilities. |
| `src/` | Original Rust PDF/corpus pipeline: font conversion, OCR hooks, crawler/index tools. |
| `recipes/` | Per-domain crawler/source recipes. |
| `datasets/` | Reviewer-facing public dataset artifacts and dataset release notes. |
| `benchmarks/` | Reviewer-facing benchmark/eval data and smoke-gate notes. |
| `corpora/` | Only small public registries are committed. Large corpora/SFT data are ignored. |
| `assets/` | Curated screenshots/diagrams used by README/submission docs. |
| `docs/raspberrypi.md` | Short runnable Pi/`llama.cpp` runbook for the edge Gemma claim. |
| `docs/architecture/` | Product/RAG/crawler architecture and hardening notes. |
| `docs/finetuning/` | SFT/CPT research, results, recipes, eval history. |
| `docs/runbooks/` | Demo, Pi, WhatsApp, and deployment runbooks. |
| `docs/archive/` | Historical plans and logs kept for provenance. |

## What Is Not In Git

The repo intentionally excludes model weights, checkpoints, generated SFT
corpora, full crawl outputs, raw videos, temporary renders, auth state, local
databases, and tokens. Those belong in Hugging Face/Kaggle datasets or private
operator storage, not in source control.
