# PreVillage public architecture

Snapshot: 2026-05-18.

Purpose: architecture blueprint for the Gemma 4 Good public submission. This is
the document to read before changing the public demo, writeup, artifact release,
or video proof shots.

## Product Contract

PreVillage is a Nepal government-service navigator, not a generic RAG chatbot.

The system must:

- perform resolver/intake before answering;
- remember case details already given in the chat/session;
- ask compact follow-up questions when the case is ambiguous;
- route retrieval by question type, not one fixed source ranking;
- answer from official sources and reviewed named practical sources;
- include contacts and uncertainty where useful;
- log gaps instead of hallucinating;
- support text, WhatsApp, kiosk, and voice access.

Core rule:

```text
Facts live in sources.
Gemma fixes noisy input, plans the case, asks follow-ups, composes grounded
answers, and explains uncertainty.
```

## Public Artifact Decision Log

### ASR

Decision, 2026-05-18: the Nepali ASR artifact will be public for the
submission.

Current public surface:

- `https://huggingface.co/spaces/voidash/nepali-fastconformer-demo`

Current staging reference:

- `voidash/nepali-asr-staging`

Target state:

- publish a clean public ASR checkpoint/model artifact;
- no private corpus shards;
- no tokens/secrets;
- model card states training data tiers and limitations;
- Space runs from the public artifact, not a private token-only staging repo.

If `voidash/nepali-asr-staging` cannot be made public safely, create a new
clean public release repo and point the Space there.

### TTS

Public artifacts already verified:

- `https://huggingface.co/ampixa/real-nepali-v0.2-kala`
- `https://huggingface.co/ampixa/real-nepali-v0.4`
- `https://huggingface.co/spaces/ampixa/real-nepali-tts`
- `https://huggingface.co/datasets/ampixa/neptts-bench`

Use public NepTTS-Bench README numbers unless the public dataset card is updated
before submission:

- 164+ native Nepali speakers;
- 5,760+ ratings.

Remote working copy:

```text
cdjk@<private-storage-tailnet-ip>:~/gt/neptts_bench
```

Remote paper draft currently has newer numbers, but do not cite those publicly
until the public dataset card is synchronized.

### Gemma

Public-facing model story:

- Gemma 4 E2B is the local/edge target.
- Gemma 4 E4B/SFT work is engineering evidence and a stronger candidate lane,
  but do not imply a rejected adapter powers the demo.
- Deployed reliability comes from resolver, source routing, retrieval,
  deterministic high-confidence extraction, and grounded composition.

## System Architecture

```text
Citizen / visitor
  -> web chat | kiosk | WhatsApp | voice
  -> session memory
  -> ASR if audio
  -> Gemma transcript fixer
  -> service resolver / dialogue planner
  -> source router
  -> retrieval
       official gov corpus
       reviewed human practical corpus
       contacts directory
  -> Gemma grounded composer
  -> answer + contacts + citations + follow-up + gaps
  -> TTS if voice reply
  -> gap logger / human review loop
```

## Runtime Components

| Layer | Component | Responsibility | Public Proof |
|---|---|---|---|
| Interface | Web chat | Plain chat with sources and memory | Live demo |
| Interface | Kiosk | Mic input, ASR transcript, answer stream, TTS playback | Video shot |
| Interface | WhatsApp | Real Baileys bridge for text/audio | Video shot, code |
| Speech input | Nepali ASR | Transcribe Nepali speech into text | Public HF ASR artifact + Space |
| Transcript repair | Gemma fixer | Repair WER/script noise without changing intent | Kiosk raw vs fixed shot |
| Planning | Resolver/planner | Service, action, location, case type, missing slots | `/retrieve` metadata |
| Retrieval | Source router | Choose source classes by question | Planner metadata |
| Retrieval | Gov corpus | Official .gov.np pages/PDF chunks | Source/chunk counts |
| Retrieval | Human practical corpus | Named reviewed officer/staff/citizen notes | Admin/interview shot |
| Composition | Gemma composer | Source-grounded answer and uncertainty | Query response |
| Speech output | Nepali TTS | Speak compact answer, not raw URLs | HF TTS artifacts |
| Operations | Corpus health | Detect zero chunks, stale polls, duplicates | Audit report |
| Operations | Gap logger | Missing source/contact/interview/alias tasks | JSONL/admin shot |

## Query-Time Contract

Every query should produce or internally use this frame:

```json
{
  "service": "citizenship | passport | vital_registration | ...",
  "action": "apply | renew | replace | correct | contact | complaint | ...",
  "case_type": "first_time | lost | correction | unknown",
  "location": {
    "district": "Sankhuwasabha",
    "municipality": null,
    "ward": null
  },
  "known_from_memory": [],
  "missing_slots": ["municipality", "ward", "case_type"],
  "source_classes": ["dao", "municipality", "citizen_charter", "contact"],
  "expected_domains": ["daosankhuwasabha.moha.gov.np"],
  "retrieval_query": "citizenship Sankhuwasabha DAO required documents contact",
  "gaps": []
}
```

The response can answer partially while asking follow-up:

```text
I can guide you, but citizenship depends on your exact case. Tell me your
municipality/ward and whether this is first-time, lost/duplicate, or correction.

Meanwhile, the district-level office is DAO Sankhuwasabha. I found the DAO
source, but not your ward-level checklist yet.
```

## Voice Flow

Voice is part of the access layer:

```text
audio
  -> Nepali ASR
  -> raw transcript
  -> Gemma transcript fixer
  -> fixed question / preserved uncertainty
  -> service planner
  -> RAG
  -> visible answer with sources
  -> TTS preprocessor
  -> short spoken answer
```

Rules:

- Raw transcript must stay visible in kiosk/debug mode.
- Fixed question must not invent missing slots.
- Spoken answer must omit URLs and citation markers.
- Visible answer must keep citations/source cards.
- If ASR is uncertain, ask confirmation instead of over-normalizing.

## Deployment Modes

### Public cloud/demo

Use for judges and remote reviewers.

- Public web URL.
- Public code repo.
- Public HF model/data links.
- No private tokens in frontend or repo.
- Demo should degrade gracefully if GPU/Space is cold.

### Office computer

Use for real local pilot framing.

- Runs backend, RAG index, kiosk, WhatsApp bridge, ASR/TTS workers.
- Keeps office/user data local where needed.
- Can use stronger hardware than Pi for full RAG and voice concurrency.

### Raspberry Pi / edge lane

Use as low-cost proof, not full-stack claim.

- Gemma E2B Q4 local inference through llama.cpp.
- TTS warm response around 1.1-1.4s in the measured Pi benchmark.
- ASR warm response around 2.9-3.0s for a short WAV in the measured Pi
  benchmark.
- Gemma E2B generation around 6-8 tok/s in the measured smoke.

Correct claim:

```text
The Pi proves a low-cost local edge lane. The full office helpdesk can run on an
office computer with local RAG, voice, WhatsApp, and admin review.
```

## Public Release Checklist

### Code

- Remove secrets, passwords, private phone numbers, auth directories, and
  local-only tokens.
- Make setup path obvious:
  - backend;
  - frontend;
  - WhatsApp bridge optional;
  - voice workers optional;
  - RAG data/bootstrap path.
- Add a small public demo dataset or documented remote demo URL.
- Mark experimental parts honestly.

### Hugging Face

- TTS v0.2/v0.4 links already public.
- NepTTS-Bench public card should be synchronized if using newer paper numbers.
- ASR release needs a clean public repo or public staging conversion.
- ASR model card should include:
  - architecture;
  - checkpoint path;
  - training data tiers at a high level;
  - best validation WER if defensible;
  - limitations: dialects, noisy audio, code-mix, private staging history.

### Demo

- `/chat` or equivalent: text service navigation.
- `/kiosk`: voice in, raw/fixed transcript, answer, TTS playback.
- `/whatsapp`: real Baileys bridge connected, but no officer auto-message.
- `/admin` or screenshot: source counts, tacit/review loop, health evidence.

### Video

Must capture:

- one ambiguous query that asks follow-up instead of over-answering;
- one local contact/source query that works;
- one voice query showing raw ASR -> fixed question -> answer -> TTS;
- one WhatsApp interaction;
- one RAG/source/health proof shot;
- one ASR/TTS/HF/NepTTS-Bench proof shot;
- one Pi/edge proof shot.

## Immediate Work Order

1. Publish or clean-release the ASR checkpoint artifact.
2. Update the ASR Space to consume the public artifact.
3. Synchronize NepTTS-Bench public README if using the newer 207/7,003 numbers.
4. Cut the Kaggle writeup to 1,500 words using this architecture.
5. Prepare public repo README and demo instructions.
6. Capture proof shots in the video order.
7. Run final smoke tests:
   - English local contact;
   - Nepali local contact;
   - Roman-Nepali service query;
   - ambiguous citizenship;
   - WhatsApp text;
   - WhatsApp audio;
   - kiosk voice;
   - streaming answer/source rendering.

## Do Not Overclaim

- Do not say every Nepal government service is covered.
- Do not say SFT alone made the helpdesk reliable.
- Do not say Pi runs the full national RAG and all voice services concurrently.
- Do not say human practical notes are official law.
- Do not auto-message officers from public failure cases.
- Do not hide failures like ASR noise; show that Gemma repair/intake exists
  because noisy transcripts are real.
