# PreVillage Gemma 4 Good writeup research

Snapshot: 2026-05-18.

Purpose: turn prior Gemma hackathon winner writeups and the current Gemma 4
Good rules into concrete guidance for the PreVillage Kaggle writeup and video.

## Current competition constraints

Primary source:

- Gemma 4 Good Kaggle page:
  <https://www.kaggle.com/competitions/gemma-4-good-hackathon/overview>

Important constraints:

- The submission needs a Kaggle writeup, public video, public code repository,
  live demo, and media gallery.
- The writeup is the proof-of-work report. It must explain the app
  architecture, how Gemma 4 is used, challenges overcome, and why the technical
  choices are right.
- The writeup should not exceed 1,500 words.
- The video is judged as the star of the submission.
- Scoring is:
  - Impact & Vision: 40 points
  - Video Pitch & Storytelling: 30 points
  - Technical Depth & Execution: 30 points
- The prompt explicitly asks for post-training, domain adaptation, and agentic
  retrieval when they improve grounded outputs.
- Relevant impact categories for PreVillage:
  - Digital Equity & Inclusivity: strongest fit.
  - Safety & Trust: secondary fit because groundedness, citation, source
    routing, and uncertainty are central.
- Relevant special technology prizes:
  - llama.cpp, if the Pi/edge run is shown cleanly.
  - Unsloth, only if the fine-tuned Gemma 4 SFT artifact is public and the
    writeup proves it was useful.
  - Ollama, only if the deployed local demo visibly uses Ollama. Do not dilute
    the story chasing every prize.

## Prior winner patterns

Primary source:

- Official Google winner announcement:
  <https://blog.google/technology/developers/developers-changing-lives-with-gemma-3n/>

The official announcement frames the winning projects around mobile-first,
on-device, multimodal Gemma systems that address real human needs. That is the
standard to match: not "we used an LLM," but "this model shape made this
deployment possible."

### Gemma Vision

Writeup:

- <https://www.kaggle.com/competitions/google-gemma-3n-hackathon/writeups/gemma-vision>

What made it strong:

- It has a concrete human tester: the builder's blind brother.
- It does not hide implementation pain. The writeup explains model download,
  Google AI Edge, camera position, controller integration, TalkBack/VoiceOver,
  text recognition, and latency.
- It gives a specific performance story: camera preview caused a major
  slowdown, so the flow was changed to capture then close the camera before
  inference.
- It uses streaming plus audio feedback because the user cannot visually tell
  whether generation is still running.
- It admits Gemma was not the best tool for OCR alone and adds ML Kit as a
  deterministic on-device tool.

Lesson for PreVillage:

- Show the office/citizen workflow details, not just the model. The equivalent
  hard details are Jiri fieldwork, Nepali/Roman-Nepali failures, source routing,
  chat memory, WhatsApp voice, kiosk latency, and why deterministic extraction
  exists only for narrow high-confidence cases.

### Vite Vere Offline

Writeup:

- <https://www.kaggle.com/competitions/google-gemma-3n-hackathon/writeups/vite-vere-offline>

What made it strong:

- It is easy to scan: what it does, key features, architecture, how Gemma is
  used, challenges, why choices were right.
- It stays product-specific: people with cognitive disabilities, offline task
  support, simplified instructions, local TTS.
- It clearly names constraints: offline execution, limited memory, cognitive
  accessibility, offline speech, lightweight image interpretation.

Lesson for PreVillage:

- Our writeup needs a "What it does" section before the engineering arc. Judges
  should understand the product in 20 seconds: intake, follow-up, RAG, contacts,
  kiosk, WhatsApp, voice, local deployment.

### 3VA

Writeup:

- <https://www.kaggle.com/competitions/google-gemma-3n-hackathon/writeups/3va>

What made it strong:

- It centers one named person and makes the harm obvious.
- It explains the data: 809 examples co-written with the user.
- It has a "Validation / What's Real" section.
- It includes a replication path: collect examples, train, deploy.
- It frames local processing as privacy, dignity, and ownership, not just cost.

Lesson for PreVillage:

- Add a "What is real today" section. Be explicit: source registry, crawler,
  RAG backend, planner, audits, Jiri field interviews, Baileys WhatsApp bridge,
  ASR/TTS workers, kiosk, Pi llama.cpp run. Do not make judges infer reality
  from prose.

### Sixth Sense for Security Guards

Writeup:

- <https://www.kaggle.com/competitions/google-gemma-3n-hackathon/writeups/sixth-sense-for-security-guards-powered-by-googles>

What made it strong:

- It publishes the actual prompt/contract shape.
- It has experiments with known outcomes and raw model outputs.
- It gives a concrete system pipeline, hardware list, performance notes, and
  caveats.
- It explains why prefiltering is necessary instead of pretending Gemma should
  process everything directly.

Lesson for PreVillage:

- Include a compact planner contract and eval table. The direct analog is:
  resolver -> source router -> retrieval -> grounded composer -> citations and
  contacts. Show smoke cases and failure modes fixed: wrong Jiri contacts,
  Hindi leakage, loops, stale sources, generic answers, unsupported claims.

### LENTERA

Writeup:

- <https://www.kaggle.com/competitions/google-gemma-3n-hackathon/writeups/lentera-offline-ai-microserver-for-remote-and-rura>

What made it strong:

- It has a last-mile infrastructure thesis, not just an app.
- It shows offline AI plus a content library.
- It is honest about latency and hardware cost.
- It uses caching for common queries and slower generation for novel queries.
- It positions local deployment as the difference between static content and
  interactive help.

Lesson for PreVillage:

- This is the closest precedent. Our version is not "offline education"; it is
  "office-local government-service navigation." The Pi and office-computer
  story should be framed as a local helpdesk appliance: the heavy crawl builds
  the knowledge, the office runs the helpdesk.

## What this means for our writeup

The current working draft is useful background, but it is too broad for Kaggle.
The final writeup should be under 1,500 words and should not try to list every
experiment. It should prove four things:

1. The problem is real and morally sharp.
2. The product works as a service navigator, not a generic chatbot.
3. Gemma 4 is load-bearing: planner/composer behavior, local deployment,
   edge/Pi path, SFT research, and voice/intake repair.
4. The engineering was not faked: source registry, crawler, RAG, audits,
   rejected checkpoints, live WhatsApp/kiosk/voice paths, and measured edge
   behavior.

Recommended 1,500-word structure:

1. Title and subtitle.
2. Problem: the hidden public-service route, 150-200 words.
3. What PreVillage does, 150 words.
4. Why Gemma 4, 150-200 words.
5. Architecture, 250-300 words.
6. Engineering arc/challenges, 300-350 words.
7. What is real today/evidence, 200-250 words.
8. Limitations and next steps, 100-150 words.

## Claims to emphasize

- "A normal chatbot answers. PreVillage does intake."
- "The facts live in sources. The model plans, asks, composes, and explains
  uncertainty."
- "SFT failures were product research: they showed what should not be
  memorized."
- "Human practical knowledge is part of the corpus, but named and reviewed."
- "Office-local deployment matters because government help should work where
  the citizen is: counter, kiosk, WhatsApp, voice."
- "The Pi run proves the low-cost edge lane; the full office helpdesk can run
  on stronger local hardware."

## Claims to avoid

- Do not imply every Nepali government procedure is solved.
- Do not imply SFT alone made the helpdesk reliable.
- Do not imply the model memorizes government facts.
- Do not overstate the Pi as running the full national RAG stack.
- Do not present automatic WhatsApp officer messaging as production behavior.
  The correct framing is operator-reviewed human handoff/gap escalation.

## What to change in the current writeup draft

- Add a "What is real today" section modeled after 3VA.
- Add a compact architecture diagram/table modeled after Sixth Sense.
- Add a hardware/latency paragraph modeled after LENTERA.
- Add a "wrong turns" paragraph: CPT regression, weak SFT, v5 rejection, v6
  planner/composer, RAG hardening.
- Cut the long internal history unless it directly proves judgment.
- Use the video for emotion; use the writeup for verification.

## Source links

- Gemma 4 Good overview:
  <https://www.kaggle.com/competitions/gemma-4-good-hackathon/overview>
- Google Gemma 3n winners announcement:
  <https://blog.google/technology/developers/developers-changing-lives-with-gemma-3n/>
- Gemma Vision:
  <https://www.kaggle.com/competitions/google-gemma-3n-hackathon/writeups/gemma-vision>
- Vite Vere Offline:
  <https://www.kaggle.com/competitions/google-gemma-3n-hackathon/writeups/vite-vere-offline>
- 3VA:
  <https://www.kaggle.com/competitions/google-gemma-3n-hackathon/writeups/3va>
- Sixth Sense:
  <https://www.kaggle.com/competitions/google-gemma-3n-hackathon/writeups/sixth-sense-for-security-guards-powered-by-googles>
- LENTERA:
  <https://www.kaggle.com/competitions/google-gemma-3n-hackathon/writeups/lentera-offline-ai-microserver-for-remote-and-rura>
- Gemma 4 E2B model card:
  <https://huggingface.co/google/gemma-4-E2B-it>
