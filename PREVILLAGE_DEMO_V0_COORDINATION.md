# PreVillage demo v0 coordination

Purpose: align the web/kiosk voice demo and the WhatsApp demo around one
pipeline and one story before the 2026-05-19 05:44 NPT deadline.

## Ownership split

This agent owns:

- three-minute video script and shot plan;
- web/kiosk speaking-listening v0 plan;
- API contract for the voice pipeline;
- product truthfulness: no hallucinated claims about unfinished WhatsApp/ASR/TTS
  integration.

Other WhatsApp agent owns:

- Baileys/WhatsApp demo surface;
- sending citizen message/audio into the same backend contract;
- showing contact-officer outreach when the system lacks room/practical info;
- returning answer text and, if available, TTS audio.

Shared contract:

- both demos should call the same service-navigator query path after
  transcript fixing;
- both demos should show the same missing-source behavior: log gap, ask a
  human/contact officer, do not hallucinate.

## Demo pipeline

```text
User voice/audio/text
  -> ASR if audio
  -> Gemma transcript fixer
  -> service resolver/planner
  -> RAG retrieve official + tacit sources
  -> composer answer with citations/contact/uncertainty
  -> TTS answer preprocessor
  -> Nepali TTS audio
  -> UI reply
  -> if gap: WhatsApp contact-officer outreach task
```

## Web/kiosk v0 UX

Route proposal: `/office` or `/kiosk`.

Screen shape:

- large "Hold to speak" / "Tap to speak" mic button;
- live recording state;
- raw transcript panel;
- "fixed question" panel;
- answer panel with source cards;
- replay spoken answer button;
- small gap/outreach panel if missing info is detected;
- no complex settings in the demo screen.

Voice interaction target:

1. User speaks a Nepali or Roman-Nepali government-service question.
2. UI records audio and sends it to backend.
3. Backend returns:
   - raw transcript;
   - fixed question;
   - planner summary;
   - answer;
   - sources;
   - TTS audio URL or base64;
   - optional outreach task.
4. UI plays TTS and shows the same answer text.

## API contract proposal

### `POST /voice/query`

Multipart form:

```text
audio_file: webm/wav/m4a/etc. optional if text is supplied
text: optional direct text fallback
language_hint: optional, e.g. ne, roman-ne, en, mixed
session_id: optional
mode: "kiosk" | "whatsapp" | "web"
```

Response:

```json
{
  "raw_transcript": "mero nagarikta sankhuwasabha ma banauna cha",
  "fixed_question": "मेरो नागरिकता संखुवासभामा बनाउनुछ।",
  "planner": {
    "service": "citizenship",
    "action": "apply",
    "location": {"district": "Sankhuwasabha"},
    "missing_slots": ["municipality", "ward", "case_type"],
    "follow_up_questions": [
      "Which municipality/rural municipality and ward?",
      "Is this first-time, duplicate/lost, or correction?"
    ],
    "coverage_gaps": []
  },
  "answer": "...",
  "sources": [],
  "citations": [],
  "tts_text": "...speakable answer...",
  "tts_audio_url": "/voice/audio/<id>.wav",
  "outreach_task": null
}
```

If source is missing:

```json
{
  "answer": "I do not have a reliable source for the exact room number yet...",
  "outreach_task": {
    "status": "queued_for_demo",
    "reason": "missing_room_number",
    "office": "Jiri Municipality",
    "contact_source": "jirimun.gov.np contact page",
    "suggested_message": "Namaste, PreVillage is checking..."
  }
}
```

## Transcript fixer behavior

Goal: repair ASR word errors, spelling, and script noise without changing the
user's intent.

Inputs:

- raw transcript;
- optional language hint;
- recent chat memory;
- known service aliases;
- Nepal geography/service aliases.

Output:

- fixed question text;
- confidence;
- changed spans if useful for debugging;
- if uncertain, preserve raw phrase instead of over-normalizing.

Rules:

- Do not invent missing location/case slots.
- Do not turn a broad query into a specific service.
- Preserve Roman-Nepali if the UI mode wants Roman output.
- Prefer government-service aliases: CDO/DAO/jilla prashasan, nagarikta,
  sifaris, ward, passport, PAN, shram swikriti, manpower, etc.

## TTS answer preprocessor

Goal: convert answer text into speakable Nepali without destroying citations in
the visible answer.

Inputs:

- visible answer;
- citations/source cards;
- language/script choice.

Output:

- short spoken answer;
- removes raw URLs and `[S#]` citation markers from speech;
- keeps uncertainty and follow-up questions;
- expands numbers/phones carefully if the TTS frontend needs it.

Example:

Visible:

```text
Jiri Municipality lists Contact No. +977 071 5555556 [S1].
```

Spoken:

```text
जिरी नगरपालिकाको सम्पर्क नम्बर शून्य सात एक, पाँच पाँच पाँच पाँच पाँच पाँच छ हो।
```

## WhatsApp agent handoff

The WhatsApp agent should implement two demo flows.

### Flow A: citizen asks known question

Input:

```text
जिरी नगरपालिकाको हेल्पडेस्क नम्बर?
```

Expected:

- query backend;
- return answer with short citation label;
- optionally return TTS audio.

### Flow B: system lacks practical room/counter info

Input:

```text
जिरीमा जन्मदर्ता गर्न पहिले कुन कोठामा जाने?
```

Expected if room source is absent:

- answer honestly: official source found / practical room source missing;
- queue or show outgoing WhatsApp message to relevant contact officer;
- show message text and target contact, not fake answer.

Suggested contact-officer message:

```text
Namaste. PreVillage is helping citizens find Jiri Municipality service
information. We have the official birth-registration source, but we do not have
verified practical room/counter routing. For a first-time birth-registration
visitor, which room/counter should they visit first, and what documents are most
commonly missed?
```

## Video demo questions

Known-source demo:

- `जिरी नगरपालिकाको हेल्पडेस्क नम्बर के हो?`
- `जिरीको नगर प्रमुख को हुनुहुन्छ?`
- `How do I replace a lost citizenship certificate?`

Ambiguous-intake demo:

- `Sankhuwasabha ma nagarikta banauna paryo`

Voice/kiosk demo:

- `जिरीमा जन्मदर्ता गर्न के चाहिन्छ?`

Missing-practical-source demo:

- `जिरीमा जन्मदर्ता गर्न पहिले कुन कोठामा जाने?`

## Immediate build order

1. Create `/office` kiosk route with recording UI and answer playback shell.
2. Add backend `/voice/query` with text fallback first, so UI can be tested
   before ASR/TTS are wired.
3. Wire audio upload to current ASR path or local ASR artifact once path is
   known.
4. Add transcript fixer prompt/path.
5. Call existing `/query` pipeline with fixed question and history.
6. Add TTS preprocessor and return `tts_text`; wire audio when local TTS command
   or server is available.
7. Coordinate WhatsApp agent to call the same `/voice/query` or `/query` path.

## Required answers from Ashish

Blocking for real ASR/TTS integration:

1. Exact ASR artifact path/model repo and how to run inference.
2. Exact TTS inference command/server for the chosen voice.
3. Whether the kiosk output should speak in Nepali script, Roman Nepali, or
   match user input.

Blocking for video:

1. Which Jiri footage has public consent.
2. Which live demo question you want to ask on camera.
3. Whether to say Rs. 7,000 or Rs. 8,000.
