# PreVillage Gemma 4 Good submission plan

Snapshot: 2026-05-18.

Goal: make the submission match the Gemma 4 Good judging shape: a strong
three-minute story, backed by a 1,500-word proof-of-work writeup, public code,
live demo, and public artifacts.

Architecture source of truth:

- `PREVILLAGE_PUBLIC_ARCHITECTURE.md`

## Judging Target

Gemma 4 Good scoring:

- Impact & Vision: 40
- Video Pitch & Storytelling: 30
- Technical Depth & Execution: 30

Implication:

- The video carries the emotional arc.
- The writeup proves the technology is real.
- The repo/demo prove the writeup is not staged.

## Core Positioning

PreVillage is not a generic government chatbot.

It is a government-service navigator for Nepal:

- intake before answer;
- compact follow-up when location/case/service is ambiguous;
- source routing by question type;
- official sources plus reviewed named practical sources;
- contacts and uncertainty;
- voice, WhatsApp, kiosk, and web access;
- local Gemma deployment path for offices.

One-line thesis:

> I used privilege to find the path. PreVillage exists so the next person does
> not need privilege to use their own government.

## Final Writeup Word Budget

Target: 1,350-1,450 words, never above 1,500.

| Section | Words | Job |
|---|---:|---|
| Problem: hidden route | 150 | Hook and moral center |
| What PreVillage does | 170 | Make product legible fast |
| Why Gemma 4 | 180 | Local model, planner/composer, edge |
| Architecture | 260 | Resolver/RAG/human/voice pipeline |
| Engineering arc | 330 | CPT/SFT failures, RAG hardening, evals |
| What is real today | 250 | Code, demo, metrics, public artifacts |
| Limits and next steps | 110 | Honest close |

## Video Beats

Three-minute target:

| Time | Beat | Proof Shot |
|---|---|---|
| 0:00-0:25 | Three weeks, four offices, Rs. 8k, hidden route | Forms, offices, road/queue |
| 0:25-0:45 | Privilege confession | GPU/terminal/Jiri travel |
| 0:45-1:10 | What PreVillage is | Web/chat asking follow-up |
| 1:10-1:40 | RAG and source layer | Source registry, crawler, citations, contacts |
| 1:40-2:05 | Training arc | SFT/CPT logs, rejected checkpoints, eval gates |
| 2:05-2:35 | Voice/WhatsApp/kiosk | ASR transcript, Gemma repair, TTS reply, WhatsApp |
| 2:35-2:50 | Local deployment | Pi llama.cpp / office computer |
| 2:50-3:00 | Closing line | "Public-service knowledge before privilege" |

## ASR/TTS Inclusion Decision

Include ASR and TTS, but keep them as the access layer for PreVillage, not as a
second hackathon project.

Decision update, 2026-05-18: the ASR artifact is intended to be public for the
submission. If the existing `voidash/nepali-asr-staging` repo cannot be made
public safely because it contains staging/private data, create a cleaned public
release repo for the checkpoint and model card, then point the Space at that
public artifact.

Correct framing:

- Nepal's public-service UX is spoken in practice: people ask clerks, neighbors,
  officers, and WhatsApp contacts.
- Voice makes the service navigator usable at a counter, kiosk, and phone.
- ASR converts messy speech to text; Gemma repairs transcript noise and performs
  service intake; RAG finds the source; TTS speaks back a compact answer.
- The voice work proves this is not only a web form.

Do not overdo:

- Do not spend more than one writeup paragraph on ASR/TTS.
- Do not imply the voice models are final SOTA.
- Do not imply the Raspberry Pi runs the full national RAG plus ASR/TTS plus
  WhatsApp concurrently.

## Voice Evidence

Local repo:

- `~/github/llm/g2p`
- `~/github/llm/g2p/ASR`
- `~/github/llm/proper-voices`

Remote benchmark repo:

- Host: `cdjk@<private-storage-tailnet-ip>`
- Path: `~/gt/neptts_bench`

Public TTS artifacts verified:

- `https://huggingface.co/ampixa/real-nepali-v0.2-kala`
  - public
  - Piper/VITS
  - Nepali
  - six-speaker checkpoint
- `https://huggingface.co/ampixa/real-nepali-v0.4`
  - public
  - punctuation-aware continuation
  - 5,808 rows / 11.60 h in model card
- `https://huggingface.co/spaces/ampixa/real-nepali-tts`
  - public Gradio Space
  - currently runs v0.2 on CPU basic
- `https://huggingface.co/datasets/ampixa/neptts-bench`
  - public benchmark dataset

NepTTS-Bench safe public claim:

- First comprehensive Nepali TTS benchmark.
- Public README currently says 164+ native Nepali speakers and 5,760+ ratings.
- Remote paper draft says 207 speakers and 7,003 ratings, but do not use those
  higher numbers publicly unless the public dataset card/writeup is updated.
- Benchmark includes human MOS, SCOREQ, ASR round-trip metrics, rating app, and
  `neptts-eval`.

ASR artifacts:

- Public demo Space:
  `https://huggingface.co/spaces/voidash/nepali-fastconformer-demo`
- It currently references `voidash/nepali-asr-staging`.
- Target state for submission: public ASR checkpoint/model artifact with a clean
  model card, no private corpus shards, no tokens, and a Space that runs from
  the public artifact.
- Until the public artifact is live, use provisional wording in drafts. Once it
  is live, update the writeup with the final HF URL.

Pi voice benchmark:

- `PREVILLAGE_PI_VOICE_BENCHMARK_2026_05_17.md`
- Safe claim:
  - Gemma E2B Q4 on Pi 5: roughly 6-8 generated tok/s.
  - TTS warm response on Pi: about 1.1-1.4 s server-side.
  - ASR warm transcription on Pi: about 2.9-3.0 s for a short Nepali WAV.
- Caveat:
  - ASR transcript still had spacing/WER artifacts, which is exactly why Gemma
    fixer/intake belongs in the pipeline.

## Public Artifact Checklist

Must be public or safely accessible:

- GitHub repo with clear README and no secrets.
- Live demo URL.
- YouTube video.
- Kaggle writeup.
- HF links for Gemma SFT adapter if used.
- HF links for TTS models/Space and NepTTS-Bench.

Need decide before final submission:

- Whether to include the SFT adapter as a main artifact or a research artifact.
- Whether to update the NepTTS-Bench public README to the newer paper numbers.

## Highest-Impact Proof Shots

1. One service query with ambiguity and a compact follow-up.
2. One Jiri/local government query that returns real contact/source info.
3. One Nepali or Roman-Nepali voice query:
   - raw ASR transcript;
   - Gemma repair/intake;
   - grounded answer;
   - TTS audio reply.
4. One WhatsApp text/audio interaction.
5. One source/crawler/audit pane.
6. One Pi/edge pane showing Gemma E2B local inference.
7. One NepTTS-Bench or HF artifact screenshot.

## Risk Controls

- No officer auto-messaging in the public demo unless operator-reviewed.
- No QR codes, tokens, private phone numbers, or passwords in footage.
- No "full coverage of all Nepal government services" claim.
- No "SFT solved the helpdesk" claim.
- No naked factual Gemma claim: facts come from sources.
- No Hindi leakage in the captured demo. If it happens, restart the shot and
  fix the prompt/language routing before filming.

## Next Work Order

1. Publish or clean-release the ASR checkpoint artifact.
2. Update the ASR Space to consume the public artifact.
3. Decide whether to update NepTTS-Bench public dataset card to newer numbers.
4. Cut the 1,500-word writeup from `PREVILLAGE_WRITEUP_WORKING_DRAFT.md`.
5. Update public repo README around PreVillage only.
6. Prepare screenshots/short captures for the proof shots above.
7. Confirm live demo endpoints and remove auth/password exposure.
8. Final video script and shot list.
