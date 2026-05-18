# PreVillage Writeup Review Audit - 2026-05-18

Purpose: review the Kaggle/Gemma 4 Good writeup against the codebase,
evidence docs, remote video pipeline, and available image assets.

## Verdict

Use `PREVILLAGE_KAGGLE_WRITEUP_HUMAN_PASS.md` as the prose base.

It is the strongest voice: direct, human, and honest about failed RAG/SFT
attempts. The longer `PREVILLAGE_KAGGLE_WRITEUP_DRAFT.md` is useful as a
technical source, but it is already 1,524 words and reads more like a system
overview than a public writeup.

The current writeup has the right thesis:

> PreVillage is not "ask AI about government." It is public-service navigation
> before privilege is needed.

What is missing is not another paragraph. What is missing is packaging:

- media gallery images with captions;
- final public links;
- claim-to-proof anchors;
- a short limitations section;
- a clearer engineering arc around `v1 -> v6` SFT/RAG iteration;
- evidence that self-healing is an ops loop, not model magic;
- evidence that voice is trained/evaluated work, not demo garnish.

## Codebase Audit

Implemented surfaces found in this repo:

| Claim | Evidence |
|---|---|
| Resolver-first service navigator | `server/navigator.py`, `SERVICE_NAVIGATOR_MODUS_OPERANDI.md` |
| Query/retrieve/stream API | `server/main.py` exposes `/retrieve`, `/query`, `/query/stream` |
| Admin stats and reindexing | `server/main.py` exposes `/admin/info`, `/admin/reindex` |
| Voice API | `server/main.py` exposes `/voice/transcribe`, `/voice/synthesize`, `/voice/providers` |
| Local ASR/TTS workers | `scripts/voice_asr_worker.py`, `scripts/voice_tts_worker.py` |
| Real WhatsApp bridge | `whatsapp/src/server.mjs` uses Baileys and supports text/audio replies |
| WhatsApp admin surface | `frontend/src/routes/WhatsAppDemo.tsx`, `/whatsapp/*` backend routes |
| Kiosk voice UI | `frontend/src/routes/LiveKiosk.tsx` |
| Chat UI | `frontend/src/routes/Chat.tsx` |
| Interview collection UI | `frontend/src/routes/Interview.tsx`, `/interview/submit` |
| Admin review/reload loop | `frontend/src/routes/Admin.tsx`, `/admin/submissions`, `/admin/submission/{sid}/approve`, `/admin/tacit/reload` |
| Source registry | `corpora/sources_tiered.jsonl`, `corpora/tier_overrides.jsonl` |
| Crawler / extraction stack | Rust crawler in `src/crawler_v2/*`; batch scripts in `scripts/run_crawl_batch.py` |
| Corpus health/self-healing audit | `scripts/corpus_health_audit.py`, `PREVILLAGE_RAG_ARCHITECTURE_FOR_VIDEO.md` |
| Source discovery | `scripts/seed_moha_office_sources.py`, `scripts/seed_dao_sources.py` |
| Eval discipline | `scripts/service_navigator_pipeline_audit.py`, `eval/reports/*`, `SFT_V6_PLANNER_COMPOSER.md` |
| Pi edge lane | `PI.md`, `PI_E2B_LLAMA_CPP_RUNBOOK.md`, `PREVILLAGE_PI_VOICE_BENCHMARK_2026_05_17.md` |
| Video capture scaffolding | `video_rag_recording/`, `video_pi_recording/`, `video_training_replay/` |

Important: the codebase supports the "real system" claim. It also shows that
the public story must be precise: the deployed reliability comes from the
planner/RAG/source routing/control layer, not from a magic SFT adapter.

## Writeup Gaps

### 1. Final Links Are Still Missing

The final submission still needs:

- public GitHub repo link;
- live demo link;
- YouTube/video link;
- public ASR artifact/model link;
- public HF TTS links;
- NepTTS-Bench link;
- optional Kaggle notebook or setup notebook link if available.

### 2. Images Are Not Integrated Yet

The docs mention media, but the writeup does not yet have a gallery manifest or
captions. This is a major missed opportunity. The story is unusually visual:
road to Jiri, office interviews, source registry, RAG audits, WhatsApp, kiosk,
Pi, ASR/TTS training.

Add a media gallery with captions. Let images carry the engineering density so
the prose can stay human.

### 3. Engineering Arc Needs A Tighter Proof Sequence

The human pass says "training failed usefully", which is good. It should be
paired with one visible artifact:

- `assets/previllage-writeup-gallery/evolution_v1_v6.png`

Caption idea:

> Six SFT/RAG passes taught us the wrong lesson to avoid: do not make a small
> model memorize government facts. Put Gemma inside a resolver, retrieval, and
> review loop.

### 4. Self-Healing Needs A Concrete Shot

The writeup correctly says self-healing is evidence-path repair. It should show
one of:

- source registry rows;
- crawl batch logs;
- corpus health audit;
- gap logging;
- admin review/tacit reload.

Without a screenshot, "self-healing RAG" sounds vague. With a shot, it becomes
credible engineering.

### 5. Voice Needs More Than "ASR + TTS"

The ASR/TTS section is strong, but it should cite the real pain:

- ASR scratch FastConformer collapse into dominant-token predictions;
- overfit diagnostic succeeded, proving the pipeline could learn;
- accepted ASR training-base total: 509.54 hours;
- TTS review found punctuation/prosody/pronunciation failures;
- NepTTS-Bench has 164+ native speakers and 5,760+ ratings.

Use these as captions or a short evidence table, not a long prose detour.

### 6. The Writeup Needs One Honest Limitations Block

Current limitation text exists, but make it more concrete:

- coverage is uneven across offices;
- some municipality sites have contacts but not service checklists;
- ASR still needs confirmation for damaged entities;
- SFT is not the public hero yet;
- WhatsApp bridge is real but not production-supervised;
- officer auto-messaging should not be shown as public behavior.

### 7. Avoid Overclaiming The Pi

Correct public claim:

> Pi proves a low-cost local edge lane with Gemma E2B Q4. The full office
> helpdesk belongs on an office computer or local server with RAG, ASR/TTS, and
> admin review.

Do not say the Pi runs the full national RAG + voice + WhatsApp stack.

### 8. Do Not Publicly Feature Officer Auto-Messaging

The remote video workspace has a `helpdesk_whatsapp_officer_outreach` contact
sheet. Keep it as internal review unless it is heavily reframed and redacted.
Current product direction is not to auto-message officers from public demos.

## Image Gallery Candidates

I copied concrete candidates into:

```text
assets/previllage-writeup-gallery/
```

Recommended public gallery:

| File | Use | Caption angle |
|---|---|---|
| `middlemen_news_contact_sheet-0.jpg` | Problem proof | Public-service middlemen are a known civic issue, not only one personal story. |
| `gov_homepage_contact_sheet.jpg` | Source breadth | PreVillage starts from official government websites, including broken/fragile ones. |
| `fieldwork_contact_sheet.jpg` | Human story | Fieldwork to Jiri: the route lived in offices and people, not only PDFs. |
| `helpdesk_chat_sources_sheet.jpg` | Product proof | The chat asks first and answers with sources instead of guessing. |
| `architecture.png` | System proof | Resolver-first RAG with official sources, reviewed practical knowledge, voice, WhatsApp, and gap loop. |
| `evolution_v1_v6.png` | Engineering arc | SFT/RAG iterations: the win was the planner/composer split around evidence. |
| `interview_form_ne.png` | Human-source intake | Practical knowledge is collected in Nepali through a structured form. |
| `admin_interview_review_sheet.jpg` | Human review | Practical claims are reviewed before retrieval. |
| `admin_review_local.png` | Admin proof | Review UI exists, not just a diagram. |
| `whatsapp_bridge_local.png` | Channel proof | Real WhatsApp bridge management surface. Redact any private details. |
| `01_rating_registration.png` / `02_dashboard.png` / `03_voices.png` | TTS benchmark proof | NepTTS-Bench and voice evaluation are real artifacts. |
| `07_huggingface.png` | Public artifact proof | TTS/benchmark release on Hugging Face. |

Internal-only unless redacted/reframed:

| File | Reason |
|---|---|
| `whatsapp_officer_outreach_sheet_INTERNAL_REVIEW.jpg` | Shows officer-outreach demo behavior; current public direction is not to show automatic officer messaging. |

Remote video workspace checked:

```text
cdjk@<video-workstation-tailnet-ip>:/Volumes/TRANSCEND/video-creation/previllage-gemma-for-good-2026
```

Useful remote files:

- `analysis/gemini/govspeak-2/clip_index.md`
- `spec/rough_spec_v3_timeline.md`
- `spec/visual_assets_plan_20260518.md`
- `analysis/helpdesk_product_captures/contact_sheets/`
- `analysis/gov_homepage_montage/screenshots/`
- `footage/selects/govspeak-2/`
- `footage/selects/story_clips/`

## Gallery Order

Use 8-10 images, in this order:

1. Cover/composite: PreVillage title + office/road/product.
2. Origin/middlemen evidence.
3. Government source breadth / fragile websites.
4. Architecture diagram.
5. Chat ask-first/source-backed answer.
6. Human practical source intake/review.
7. Voice/kiosk or TTS/ASR benchmark image.
8. Pi/local Gemma image or evolution card.
9. WhatsApp bridge, redacted.
10. Closing fieldwork still.

## What To Add To The Writeup

Add a compact "Evidence" block near the end:

```text
Built proof:
- FastAPI resolver/RAG backend with `/retrieve`, `/query`, and streaming.
- Real Baileys WhatsApp bridge for text and audio.
- Kiosk voice path with raw ASR, fixed question, source-backed answer, and TTS.
- Source registry, crawler, corpus health audit, and gap loop.
- Interview/admin review path for practical office knowledge.
- Pi Gemma E2B local inference smoke.
- Nepali ASR/TTS work with public artifacts and human TTS evaluation.
```

Add a compact "Limits" block:

```text
PreVillage is not complete coverage of Nepal's government. Office coverage is
uneven, ASR can still damage entities, some local service checklists are absent,
and the SFT adapter is not the deployed source of truth. The production promise
is the loop: ask, retrieve, cite, expose uncertainty, collect missing practical
knowledge, and improve the source base.
```

## Final Recommendation

Do not make the writeup longer. Make it denser through evidence:

- keep the human-pass prose;
- add final links;
- attach the media gallery;
- include one architecture image;
- include one SFT/RAG evolution image;
- include one human-loop image;
- include one voice/TTS benchmark image;
- include one fieldwork image;
- include one product/WhatsApp/kiosk image.

The core narrative should stay:

> I used privilege to find the path. PreVillage exists so the next person does
> not need privilege to use their own government.
