# PreVillage production inventory and footage plan

Deadline: 2026-05-19 05:44.

This document turns the scattered project work into a production map for the
three-minute Gemma for Good video and the v0 demo. It is intentionally practical:
what exists, where it lives, what can be filmed, what still needs to be generated,
and what claims are safe.

## North Star

PreVillage is not a generic chatbot. It is a local government-service navigator:
intake first, source routing, compact follow-ups, practical office knowledge,
contacts, uncertainty, and human handoff when the source is missing.

The story is privilege turned into infrastructure:

> I used privilege to find the path. PreVillage exists so the next person does
> not need privilege to use their own government.

The Reddit origin remains the human hook: company registration plus PAN took
weeks, repeated forms, office-to-office routing, and middleman fees because the
real process was tacit instead of written.

## Current Truth We Can Show

### Helpdesk and RAG

Local repo: `/Users/cdjk/github/llm/gemma-god`

Useful files:

- `SERVICE_NAVIGATOR_MODUS_OPERANDI.md` - canonical behavior.
- `HACKATHON_DEMO_RUNBOOK.md` - documented demo-ready state.
- `RAG_HARDENING_STATUS.md` - Jiri and contact-ranking history.
- `SFT_V5_POSTMORTEM_AND_NEXT_PASS.md` - rigorous failure story; v5 is not safe.
- `PREVILLAGE_DEMO_V0_COORDINATION.md` - voice/WhatsApp/kiosk pipeline.
- `frontend/src/routes/WhatsAppDemo.tsx` - current PreVillage WhatsApp-style demo UI.
- `whatsapp/src/server.mjs` - Baileys bridge with text, voice ingest, TTS fallback.
- `server/main.py` - RAG API, interview/admin, ASR/TTS hooks.

Safe claims from docs:

- Full government directory crawl documented at 899/899 sources.
- FTS documented at 270,509 searchable chunks.
- Demo audit documented as 14/14 pass on 2026-05-10.
- Jiri-specific hardening exists for phone/contact/person/service questions.
- v5 adapter trained but failed smoke testing; do not claim it is deployed.

What to film:

- `HACKATHON_DEMO_RUNBOOK.md` with the 899 sources / 270,509 chunks / 14 pass lines.
- `server/main.py` prompt rules around cited-source-only answers and uncertainty.
- `SERVICE_NAVIGATOR_MODUS_OPERANDI.md` showing resolver/intake before RAG.
- local screenshots already in repo: `chat-after-click.png`, `admin-expanded.png`,
  `interview-ne-final.png`, `whatsapp-demo-local.png`.
- the frontend routes list to show this is a real product surface, not slides.

### Frontend and UX State

Existing surfaces:

- `/chat` - citizen helpdesk with source cards.
- `/interview` - office/practical knowledge recording path.
- `/admin` - review/approve/transcribe practical claims.
- WhatsApp demo route in the React frontend.
- Static older HTML surfaces under `web/`.

Current gap:

- We still need the dedicated kiosk/live voice interface. It can be a web app
  mode for now, with text fallback first and real audio as soon as ASR/TTS are
  wired.

What to film:

- Current chat answer with sources.
- Interview recording flow.
- Admin review expanding one submission.
- WhatsApp demo showing text, voice icon, source cards, and contact-officer
  outreach message.

### G2P and TTS

Local repo: `/Users/cdjk/github/llm/g2p`

Important docs and surfaces:

- `README.md`
- `docs/current-state.md`
- `docs/frontend-preparation-roadmap.md`
- `docs/linguist-review-invitation.md`
- `reports/neptts_bench_scorecard.md`
- `reports/cross_system_scorecard.md`
- `hf_model_real_nepali_v02_kala/README.md`
- `hf_model_real_nepali_v04/README.md`
- `hf_space_real_nepali_tts/README.md`
- `ASR/README.md`

Local samples and review assets:

- `/Users/cdjk/samples/punctuation_review_v02_vs_v04.html`
- `/Users/cdjk/samples/real_nepali_v04_punct_bs96/`
- `/Users/cdjk/samples/dashboard.html`
- `/Users/cdjk/samples/tts_review/`

Remote logs and samples:

- `/mnt/transcend4tb/g2p_aws_saves/g2p_aws_minimal_20260503T164025Z/training/multi_speaker_v4_train.log`
- `/mnt/transcend4tb/g2p_aws_saves/g2p_aws_minimal_20260503T164025Z/training_samples/`

Useful visual facts:

- Piper/VITS training logs include hundreds of epochs and checkpoint/audio sample
  logging.
- Public Ampixa pages are live:
  - `https://ampixa.com`
  - `https://tts.ampixa.com`
  - `https://tts.ampixa.com/speak`
  - `https://tts.ampixa.com/voices`
  - `https://tts.ampixa.com/rating`
  - `https://tts.ampixa.com/g2p`
- The `/voices` portal currently shows progress per speaker.
- The `/g2p` portal shows open review batches and native/linguist workflow.

What to film:

- Terminal tail/replay of `multi_speaker_v4_train.log` showing epoch progress.
- Browser walkthrough of `tts.ampixa.com/speak`, `/voices`, `/rating`, `/g2p`.
- Sample WAV comparison page for punctuation/prosody.
- Sister voice footage, which already exists, as the human part of TTS.
- Hugging Face pages for Ampixa models/datasets if time permits.

### ASR

Local ASR path: `/Users/cdjk/github/llm/g2p/ASR`

Remote ASR paths:

- `/mnt/transcend4tb/asr_work/g2p_asr_tools/ASR/`
- `/mnt/transcend4tb/asr_work/asr_audit/`
- `/mnt/transcend4tb/asr_work/validation_dashboards_20260511/`
- `/home/cdjk/asr_mfa_training_20260516/`

Important docs:

- `ASR/README.md`
- `ASR/docs/fastconformer-training-base-2026-05-11.md`
- `ASR/docs/local-corpus-inventory.md`
- `ASR/docs/paper-style-quality-gates.md`
- `ASR/docs/youtube-training-extraction-guide.md`

Safe claims from docs already found:

- Current accepted FastConformer training base is documented as 509.54 hours.
- Chirp2 weak-label inventory is documented as 248.44 hours raw by transcript
  metadata.
- Sushant podcast/interview corpus is documented as 132 long WAVs and 258.96 raw
  hours.
- Quality gates include transcript agreement, CER/WER, akshara/phone error,
  duration, Devanagari ratio, and acoustic checks.

What to film:

- ASR README sections: goal, quality gates, data scale.
- Training-base doc with the 509.54h table.
- `validation_dashboards_20260511/*/data.json` or generated dashboard if easy.
- MFA logs under `/home/cdjk/asr_mfa_training_20260516/*/logs/train.log`.
- A voice query going through ASR once the kiosk route exists.

### NepTTS-Bench

Remote path: `/home/cdjk/gt/neptts_bench`

Important assets:

- `README.md`
- `screenshots/01_rating_registration.png`
- `screenshots/02_dashboard.png`
- `screenshots/03_voices.png`
- `screenshots/04_pairs.png`
- `screenshots/05_pair_test.png`
- `screenshots/06_github.png`
- `screenshots/07_huggingface.png`
- `screenshots/08_agentshakti.png`
- `benchmark/results/*.json`

Useful visual facts:

- 164+ native Nepali speakers and 5,760+ ratings are documented in the README.
- Human MOS table exists and can be turned into a clean visual.
- Existing screenshots are ready-made B-roll for “we built evaluation, not just
  a voice demo.”

What to film:

- Rating registration.
- Dashboard.
- Voice list.
- Pair test.
- Human MOS table as motion graphic.

### Deployment and Infra

Remote deploy doc: `/home/cdjk/deploy.md` on `cdjk@<private-storage-tailnet-ip>`

Hetzner server from doc:

- `hetzner-1`
- CAX21 ARM, 4 vCPU, 8 GB RAM, 80 GB
- Traefik on ports 80/443

Running containers observed on Hetzner:

- `ampixa-web`
- `tts-portal-web`
- `g2p-api`
- `neptts-rating-app`
- `neptts-recording`
- `proper-voices-recording`
- `jirisewa-web`
- `jirisewa-auth`
- `jirisewa-db`
- `ring_ai-*`
- `traefik`

Routed public surfaces observed from compose files:

- `ampixa.com`
- `tts.ampixa.com`
- `tts.ampixa.com/speak`
- `tts.ampixa.com/voices`
- `tts.ampixa.com/g2p/api`
- `khetbata.xyz`
- `agentshakti.xyz`

What to film:

- `docker ps` table on Hetzner.
- Traefik routing labels with secrets excluded.
- Browser tabs showing the public portals.
- A cheap-office deployment visual: small computer/Raspberry Pi + browser kiosk,
  not “random street demo.”

Security rule:

- Never film `.env`, tokens, private keys, full deploy secrets, WhatsApp pairing
  QR for a real number, or raw personal interview/audio without consent.

### Past Claude/Codex Conversations

Relevant local history locations:

- `/Users/cdjk/.claude/projects/-Users-cdjk-github-llm-gemma-god/`
- `/Users/cdjk/.claude/projects/-Users-cdjk-github-llm-g2p/`
- `/Users/cdjk/.claude/projects/-Users-cdjk-github-llm-g2p-ASR/`
- `/Users/cdjk/.claude/projects/-Volumes-TRANSCEND-video-creation-new-government/`
- `/Users/cdjk/.codex/sessions/2026/`

Use these as production memory, not as on-screen content. If filmed, show only
high-level search/index output or blurred timeline shots. Do not expose raw
private prompts, credentials, or unrelated conversations.

What to extract next:

- A one-page “grind montage” index: dates, topic, artifact produced.
- Specific lines only when they are already reflected in repo docs.

## Footage We Need To Generate

See `PREVILLAGE_EXISTING_FOOTAGE_MAP.md` for the footage already found under
`/Users/cdjk/video/PreVillageSpeaks 2` on `cdjk@<video-workstation-tailnet-ip>`. That folder
already covers the Jiri journey, mountain establishing shots, public-office
presentation, and office/interview desk footage. The remaining capture work
should focus on product/tech proof.

### Must-Have Tech Shots

1. Epoch/training progress
   - Use TTS `multi_speaker_v4_train.log`.
   - If no live run exists, replay/tail the log in terminal and crop tightly.

2. ASR data/quality pipeline
   - Show 509.54h accepted training-base doc.
   - Show quality gates.
   - Show MFA/ASR logs as process evidence.

3. G2P review infrastructure
   - Show `tts.ampixa.com/g2p`.
   - Start a batch and show word, phones, IPA, decision buttons.

4. TTS evaluation infrastructure
   - Show `tts.ampixa.com/rating`.
   - Show NepTTS-Bench dashboard screenshots.
   - Show MOS/ratings table.

5. Voice corpus collection
   - Show `tts.ampixa.com/speak`.
   - Show `/voices` progress list.
   - Cut with sister voice footage.

6. Helpdesk product
   - Show chat answering with citations.
   - Show resolver/follow-up behavior.
   - Show interview capture and admin approval.

7. WhatsApp and contact officer loop
   - Show PreVillage WhatsApp demo UI.
   - Show known-question answer.
   - Show missing-practical-info question routing to a contact officer message.

8. Kiosk/live voice mode
   - Needs implementation.
   - Minimum acceptable v0: browser records audio, shows transcript, Gemma fixes
     transcript, answers with sources, plays TTS or shows TTS-ready text.

9. Onsite low-cost deployment
   - Film Raspberry Pi or office computer running the web app locally or on a
     LAN.
   - Message: each office invests as little as possible for a capable onsite
     navigator, not every citizen needing privilege.

10. Previ lays animation
   - Simple, short, not childish: privilege egg cracks into crawler, RAG, ASR,
     TTS, WhatsApp, kiosk, human loop.
   - Use as a 1-2 second visual bridge only.

### Nice-To-Have Shots

- HF pages for Ampixa models/datasets.
- `docker ps` on Hetzner.
- Traefik diagram or compose labels.
- `rg` over source registry / crawler recipes.
- Before/after transcript fixer example.
- Model smoke/eval report showing v5 failed and why truthfulness matters.
- `ArchitectureSvg.tsx` or a cleaner motion version of the pipeline.

## Capture Order

1. Record story A-roll/voiceover only after narration text is locked.
2. Capture tech B-roll first because it can be done now:
   - portals;
   - logs;
   - docs;
   - screenshots;
   - Docker/infra;
   - existing helpdesk frontend.
3. Implement or fake-proof kiosk v0:
   - text fallback first;
   - audio record second;
   - ASR/TTS hooks third.
4. Coordinate with the WhatsApp agent:
   - exact route/port;
   - QR safety;
   - known question;
   - missing-info outreach question.
5. Build rough video spec from actual captured clips.

## Three-Minute Story Allocation

0:00-0:20 - The invisible route

- Reddit origin, office-to-office movement, repeated forms, middleman cost.

0:20-0:45 - Privilege confession

- L40/AWS access, technical skill, family voice help, Jiri travel, hunger.

0:45-1:15 - Diagnosis

- Nepal does not lack will or phones; it lacks reliable public-service memory.

1:15-1:45 - Infrastructure

- crawler, old-font/OCR, registry, RAG, resolver, evals, source routing.

1:45-2:10 - Human loop

- Jiri pitch/interviews; practical facts become first-class sources.

2:10-2:35 - Voice and WhatsApp

- ASR, Gemma transcript fixer, RAG answer, TTS, WhatsApp contact officer.

2:35-3:00 - Deployment vision

- one cheap onsite office box/kiosk; every office lays its own public service
  memory.

## Claims To Avoid

- Do not imply the failed v5 adapter is deployed.
- Do not say WhatsApp contact-officer automation is complete until the other
  agent has a working demo.
- Do not claim ASR/TTS quality as “best” without showing the benchmark basis.
- Do not imply government endorsement from Jiri footage unless consent/wording
  is explicit.
- Do not frame this as replacing officers. The story is reducing repeated,
  low-level information burden and preserving practical knowledge.

## Immediate Next Build Tasks

1. Build `/office` or `/kiosk` route in the frontend.
2. Add backend `/voice/query` text fallback first.
3. Wire transcript fixer as a deterministic prompt over ASR text.
4. Return planner/source/answer/TTS fields using the contract in
   `PREVILLAGE_DEMO_V0_COORDINATION.md`.
5. Add TTS text preprocessing and audio playback when the chosen TTS command is
   confirmed.
6. Capture the tech B-roll listed above while the WhatsApp agent finishes their
   bridge.
7. Convert this document into `spec/rough_spec_v1.md` after the narration text
   is locked.
