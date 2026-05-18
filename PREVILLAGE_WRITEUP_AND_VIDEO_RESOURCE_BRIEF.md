# PreVillage writeup and video resource brief

Snapshot: 2026-05-17.

Deadline: 2026-05-19 05:44 NPT.

This is the working evidence map for the Gemma for Good writeup and the
three-minute video. It consolidates what exists, where it lives, what can be
claimed safely, and what still needs clean footage.

## One-line thesis

I used privilege to find the path. PreVillage exists so the next person does not
need privilege to use their own government.

PreVillage is a public-service navigator for Nepal: voice, WhatsApp, kiosk, and
web access over official sources, practical office knowledge, contacts,
uncertainty, and human handoff.

## The story we should tell

Start with the public pain, not the stack.

The origin story is the company registration and PAN experience: three weeks,
four offices, four versions of the same form, and about NPR 8k paid to
middlemen, not because the law was private, but because the actual route was
tacit. The real problem was not "forms are hard." The real problem was that the
flowchart lived in people's heads.

Then turn the lens inward:

- I had the time, technical skill, GPU access, family support, and stubbornness
  to keep pushing.
- I could scrape government websites, train ASR/TTS models, rent serious
  compute, and travel 180 km to Jiri to ask officers how things really work.
- Most citizens do not get that many attempts. They get sent to the next room,
  the next office, or the next middleman.

That is the moral center of the video: use privilege to lay infrastructure.
The "Previ lays" visual can work as a short playful beat, but the serious
framing should be "pre-village": public-service knowledge before privilege.

## Product identity

Do not describe this as a generic RAG chatbot.

The product rule from `SERVICE_NAVIGATOR_MODUS_OPERANDI.md` is stronger:
PreVillage is a government-service navigator. It should do intake first, resolve
service/action/location/case type, ask compact follow-ups when needed, use chat
memory, route sources based on the question, include contacts and uncertainty,
and use named human practical sources when available.

Important product line for writeup/video:

> A normal chatbot tries to answer. PreVillage first tries to understand the
> case.

## Safe technical claims

These claims are supported by local docs or implementation.

### RAG and service navigator

Sources:

- `SERVICE_NAVIGATOR_MODUS_OPERANDI.md`
- `RAG_HARDENING_STATUS.md`
- `HACKATHON_DEMO_RUNBOOK.md`
- `server/navigator.py`
- `server/main.py`
- `scripts/service_navigator_pipeline_audit.py`
- `eval/reports/service_navigator_pipeline_k2_20260516_185517.jsonl`
- `eval/reports/rag_query_audit_k2_planner_20260516_185800.jsonl`

Safe claims:

- Full government directory crawl was documented at 899/899 sources in the
  May 10 demo runbook.
- The May 10 runbook documents 270,509 searchable chunks and 14/14 API smoke
  pass.
- Later hardening moved the deployed path to a deterministic planner-first
  pipeline using `google/gemma-4-E2B-it` with no adapter.
- The May 16 k2 planner audit passed 8/8, navigator smoke passed 7/7, and RAG
  query audit passed 15/15 with no bad citations, loops, or slow generation.
- The system returns planner metadata from `/retrieve`, `/query`, and
  `/query/stream`.
- The product handles ambiguity by asking follow-up questions instead of
  dumping a generic checklist.

Avoid claiming:

- Do not claim the failed v5 SFT adapter is deployed.
- Do not claim every government workflow is solved.
- Do not claim every office source is fresh or complete.
- Do not claim the model memorizes facts. Exact facts should come from source
  retrieval or deterministic extraction.

### WhatsApp and voice bridge

Sources:

- `HACKATHON_DEMO_RUNBOOK.md`
- `whatsapp/src/server.mjs`
- `frontend/src/routes/WhatsAppDemo.tsx`
- `frontend/src/lib/api.ts`
- `server/main.py`

Safe claims:

- A real Baileys bridge exists and is proxied through FastAPI.
- Inbound WhatsApp text works.
- Inbound WhatsApp audio is downloaded, sent to ASR, sent to `/query`, and can
  return text plus a compact TTS voice reply.
- Audio replies separate full text/sources from the compact spoken answer so
  TTS does not read URLs.
- The bridge deduplicates inbound message IDs and keeps group replies disabled.
- `/whatsapp` is operator-protected and should not expose QR, private phone
  details, or auth state in the video.

Avoid claiming:

- Do not imply the WhatsApp bridge is production-hardened. The runbook still
  lists supervisor, observability, and ASR confirmation-loop gaps.
- Do not show real pairing QR, auth directories, tokens, or private numbers.

### Live kiosk / web voice mode

Sources:

- `frontend/src/routes/LiveKiosk.tsx`
- `frontend/src/App.tsx`
- `frontend/src/lib/api.ts`
- `server/main.py`

Safe claims:

- `/kiosk` exists as a live web interface.
- It uses browser microphone capture, VAD, ASR transcription, streamed RAG
  answer, latency display, and optional TTS playback.
- It can point to a same-origin backend or an onsite backend URL.
- This is the clearest visual for "each office can run a capable-enough
  helpdesk onsite."

Video note:

- The previous production inventory said the kiosk was still missing. That is
  now outdated. The next task is clean capture and hardening, not basic concept
  design.

### ASR

Sources:

- Remote: `/mnt/transcend4tb/asr_work/g2p_asr_tools/ASR/README.md`
- Remote: `/mnt/transcend4tb/asr_work/g2p_asr_tools/ASR/docs/fastconformer-training-base-2026-05-11.md`
- Remote: `/mnt/transcend4tb/asr_work/g2p_asr_tools/ASR/docs/local-corpus-inventory.md`
- Local/remote ASR scripts and configs.

Safe claims:

- The ASR workstream targets Nepali FastConformer rather than a generic
  Whisper-only demo.
- Accepted training-base total is documented as 509.54 hours.
- The first training ladder is akshara CTC, BPE CTC, then BPE hybrid CTC-RNNT.
- Quality gates include transcript agreement, CER/WER, akshara/phone error,
  duration, Devanagari ratio, and acoustic checks.
- Open-data reality is documented: the work does not pretend 509 hours is
  universal SOTA for every dialect, microphone, code-mix, or noisy condition.

Best video visuals:

- The 509.54-hour table.
- The FastConformer config list.
- A live or recorded ASR query in `/kiosk` or `/whatsapp`.

### TTS, G2P, and evaluation

Sources:

- Remote training log:
  `/mnt/transcend4tb/g2p_aws_saves/g2p_aws_minimal_20260503T164025Z/training/multi_speaker_v4_train.log`
- Remote NepTTS-Bench:
  `/home/cdjk/gt/neptts_bench/README.md`
- Public portals:
  `https://ampixa.com`, `https://tts.ampixa.com`,
  `https://tts.ampixa.com/speak`, `https://tts.ampixa.com/voices`,
  `https://tts.ampixa.com/rating`, `https://tts.ampixa.com/g2p`

Safe claims:

- Piper/VITS-style TTS training logs exist and show hundreds of epochs.
- The log reaches epoch 675 and logs audio samples to WandB during training.
- NepTTS-Bench documents 164+ native Nepali speakers and 5,760+ ratings.
- The benchmark includes human MOS and ASR round-trip evaluation, not only
  subjective demo listening.
- The public Ampixa portals support recording, rating, voice progress, and G2P
  review workflows.

Best video visuals:

- Terminal replay or clean crop of the epoch log.
- `tts.ampixa.com/speak`, `/voices`, `/rating`, `/g2p`.
- Sister voice-recording footage as the human part of the voice stack.
- MOS table or rating dashboard as evidence that evaluation exists.

### Human practical source layer

Sources:

- Existing Jiri trip footage.
- `frontend/src/routes/Interview.tsx`
- `frontend/src/routes/Admin.tsx`
- `scripts/process_interview.py`
- Existing screenshots: `interview-ne-final.png`, `admin-expanded.png`.

Safe claims:

- The system has a pipeline concept and UI for collecting office interviews,
  reviewing submissions, and turning approved interviews into practical claims.
- The Jiri footage shows fieldwork, office presentation, and office interview
  context.
- Human source records should be treated as named, dated, confidence-labelled
  practical evidence after approval, not as anonymous rumors.

Need caution:

- Confirm consent before showing faces, names, or interview audio.
- Do not publish raw practical notes unless approved for public use.

## Existing footage map

Raw copied footage on the 4 TB SSD:

```text
/mnt/transcend4tb/video-creation/previllage-gemma-for-good-2026/footage/raw/PreVillageSpeaks2
```

Manifest:

```text
/mnt/transcend4tb/video-creation/previllage-gemma-for-good-2026/footage/raw/PreVillageSpeaks2_manifest.tsv
```

Current inventory:

- 19 videos and 1 photo.
- About 28 GB on SSD.
- About 86 minutes of source video.
- Source Mac duplicate folder only has the same copied footage.
- Downloads `govspeak` folder contains duplicate phone-shot screen clips already
  included in the copied raw folder.

Footage groups:

- Journey/remoteness: road POV, hills, mountains, public building arrival.
- Public office pitch: long GoPro meeting/presentation files and one closer
  presentation shot.
- Office interview/desk demo: practical source layer.
- Phone-shot UI/speech clips: useful texture, but not enough for clean tech
  proof.

Best use:

- 0:00-0:25: road and origin cards.
- 0:35-0:55: road/travel as the privilege confession.
- 1:45-2:10: Jiri pitch and office interview.
- 2:55-3:00: return to road/mountain or clean kiosk shot.

## Existing still/screenshots

Local screenshot assets:

- `landing-en-final.png`
- `landing-ne-full.png`
- `chat-after-click.png`
- `chat-empty.png`
- `interview-ne-final.png`
- `admin-expanded.png`
- `whatsapp-demo-local.png`
- `speakgov_v2_english.png`

Use these for draft boards or as backup stills. For final video, prefer fresh
screen recordings so the product feels alive.

## Writeup outline

1. Problem: the hidden map of government services.
2. Origin: company registration and PAN story; people pay for information, not
   just service.
3. Privilege: why one person could keep pushing when most citizens cannot.
4. Insight from Jiri: official websites miss practical route knowledge.
5. Solution: PreVillage as a service navigator, not a generic chatbot.
6. Architecture:
   - crawler/source registry;
   - resolver/intake planner;
   - source-routed RAG;
   - human practical source review;
   - ASR/TTS/G2P stack;
   - WhatsApp, kiosk, and web surfaces.
7. What was built:
   - documented crawl/audit numbers;
   - live chat;
   - WhatsApp bridge;
   - kiosk voice mode;
   - interview/admin flow;
   - ASR/TTS/evaluation groundwork.
8. Why onsite matters: each office can run a low-cost capable-enough helpdesk
   over its own sources and practical knowledge.
9. Limitations and next steps:
   - SFT adapter failed and is not deployed;
   - ASR entity confirmation still needed;
   - supervisor/observability needed;
   - more office interviews and source freshness checks.
10. Closing: public-service knowledge before privilege.

## Three-minute video source stack

### 0:00-0:20 - The hidden route

Show:

- Recreated Reddit/title card.
- Text cards: 3 weeks, 4 offices, 4 forms, about NPR 8k to middlemen.
- Fast flashes of forms, office corridors, maps, road footage.

Say:

- The law was public. The route was privileged.

### 0:20-0:45 - Privilege confession

Show:

- Road to Jiri.
- AWS/L40/training log or terminal.
- Late-night laptop clip.

Say:

- I had the privilege to keep pushing: compute, skill, time, travel, family
  support.

### 0:45-1:10 - What privilege should lay

Show:

- Very short "Previ lays" egg/infrastructure animation.
- Cut quickly to real product and source registry.

Say:

- Not a private shortcut. Public infrastructure.

### 1:10-1:40 - Navigator, not chatbot

Show:

- `/chat` asking a known Jiri/contact question.
- `/query`/planner metadata or code/doc.
- Source cards and uncertainty.

Say:

- PreVillage asks first, answers second, and refuses when the source is missing.

### 1:40-2:05 - Human practical knowledge

Show:

- Jiri meeting/pitch.
- Office interview/desk demo.
- Interview/admin review UI.

Say:

- Websites miss the room numbers, local routing, busy times, and documents
  people forget. Those become reviewed practical sources.

### 2:05-2:35 - Voice, WhatsApp, kiosk

Show:

- `/kiosk` live voice flow: mic, ASR transcript, answer, TTS playback, latency.
- `/whatsapp` status/demo with private details hidden.
- Sister voice footage and TTS epoch log.

Say:

- Nepal was never voice-poor. The internet UX was not built for us.

### 2:35-3:00 - Onsite office deployment

Show:

- Raspberry Pi or low-cost computer running `/kiosk`.
- Office counter/desk visual.
- End on road or product title.

Say:

- Each office can run a capable-enough helpdesk onsite, grounded in its own
  sources and practical knowledge.

## Footage still needed

Must capture before edit:

- Clean screen recording of `https://helpdesk.ampixa.com/chat`.
- Clean screen recording of `/kiosk` completing one voice question.
- Clean screen recording of `/whatsapp` status/demo with QR and private number
  hidden.
- Clean screen recording of interview and admin review.
- Clean browser capture of `ampixa.com` and `tts.ampixa.com` portals.
- Clean terminal capture of TTS epoch log.
- Clean ASR doc capture of the 509.54-hour training-base table.
- Raspberry Pi or low-cost office computer running kiosk mode.
- Origin-story cards from the Reddit post.

Nice to capture:

- A close shot of hands using the kiosk.
- Before/after ASR transcript correction, if the fixer is visible.
- A contact-officer outreach simulation for missing room/counter info.
- A short MOS/rating visual from NepTTS-Bench.
- A consent-safe subtitle from the Jiri interview.

## Security and privacy rules for filming

Do not show:

- `.env` files.
- API keys, tokens, private keys, cookies, deployment passwords.
- WhatsApp pairing QR for a real number.
- Full private WhatsApp JID or private phone numbers unless deliberately
  approved.
- Raw interview identities/audio without consent.
- Admin password or Basic Auth prompt contents.

Blur or crop:

- Browser address bars if they include secrets.
- WhatsApp contacts and message IDs.
- Officer faces if consent is uncertain.

## Biggest narrative risk

The project has too many impressive pieces. The video will fail if it becomes a
subsystem tour.

The edit should only prove three things:

1. The gap is real: people pay for tacit government routing.
2. The work is real: RAG, planner, ASR, TTS, WhatsApp, kiosk, field interviews,
   and evaluation exist.
3. The deployment is practical: a low-cost onsite office helpdesk can make
   public-service knowledge available before privilege is needed.

Everything else is supporting evidence.
