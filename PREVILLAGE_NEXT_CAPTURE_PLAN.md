# PreVillage next capture plan

Snapshot: 2026-05-17.

This is the next footage to capture after the training/tmux material.

## Priority order

1. Kiosk user testing with 3-4 people.
2. Raspberry Pi / local Gemma E2B edge demo.
3. Clean product screen recordings.
4. Short founder explanation lines for why Gemma mattered.
5. Safety/caveat inserts so the claims stay honest.

## Kiosk user testing

Goal: show that the voice interface can be used by normal people, not just by
the builder.

Setting:

- Outside setting is useful for energy and public proof.
- Also capture one office-like setup: table, laptop/Pi, small monitor, chair,
  counter-like framing.
- The final story should say "tested with people" outside, but "deployed inside
  offices" for the core product.

People:

- 3-4 people is enough.
- Capture consent before recording usable faces/voices.
- Get one line from each person after trying it.

Shot list per person:

1. Wide shot: person approaches kiosk/table.
2. Over-shoulder: mic/listening state.
3. Close shot: person asks the question.
4. Screen shot: ASR transcript appears.
5. Screen shot: PreVillage asks follow-up or answers with sources.
6. Reaction line: 3-6 seconds.

Suggested questions:

- "Nagarikta banauna k garnu parcha?"
- "Passport renew garna kaha jane?"
- "Company PAN banauna kun office jane?"
- "Janma darta ko certificate copy kasari line?"
- "Jiri municipality ko helpdesk number ke ho?"

Direct people away from private details:

- No real citizenship number.
- No real phone number.
- No family dispute.
- No active legal/financial complaint with names.

Good reaction prompts:

- "Would this save one office visit?"
- "Was speaking easier than searching a website?"
- "Would your parents use this?"
- "What was missing?"

Audio:

- Use a lav mic or phone close to the speaker if possible.
- Capture room tone/street tone for 20 seconds.
- Record system audio separately if TTS playback matters.

## Raspberry Pi / local Gemma E2B footage

Goal: prove that a low-cost local machine can run the small Gemma reasoning
lane onsite. This supports the privacy/offline story.

Do not claim the Pi is serving the full current RAG corpus unless that is wired
locally. The honest claim is:

> Gemma E2B can run locally as an edge/intake/composer fallback. The full
> helpdesk can be deployed onsite on an office computer with local sources.

Physical shots:

- Pi on desk with keyboard, monitor, ethernet/wifi visible.
- Power cable, SD/SSD, small fan/heatsink if visible.
- Pi beside the kiosk screen.
- A hand plugging it in or starting the local server.

Terminal shots:

```bash
cat /proc/device-tree/model
free -h
ls -lh ~/speakgov-pi/models/*.gguf
bash ~/gemma-god-pi/scripts/pi_llamacpp_start.sh
BASE_URL=http://127.0.0.1:8081 bash ~/gemma-god-pi/scripts/pi_llamacpp_office_demo.sh
```

If filming from another computer:

```bash
BASE_URL=http://<pi-ip>:8081 ./scripts/pi_llamacpp_office_demo.sh
```

On-screen caption:

```text
Gemma E2B local edge mode on a low-cost office machine
```

Voiceover idea:

> A government office does not need an L40S to help a visitor at the counter.
> Gemma gives us a small open model that can run locally for intake, rewriting,
> and fallback answers. The heavier crawl and evaluation work can prepare the
> knowledge, but the office can keep the interaction onsite.

## Clean product screen recordings

Record these after the human tests:

- `/kiosk`: one clean full successful voice flow.
- `/chat`: one source-backed answer and one follow-up question.
- `/whatsapp`: status/demo with private identifiers hidden.
- `/interview`: recording/practical-source collection flow.
- `/admin`: review/approve one practical-source submission.
- `tts.ampixa.com/speak`, `/voices`, `/rating`, `/g2p`.
- ASR 509.54-hour doc and TTS epoch log already have terminal footage; use them
  only as short inserts now.

## Why Gemma was pivotal

The writeup/video should make Gemma central without pretending it is magic.

Use these points:

- Gemma is open-weight, so the service navigator can run where the service
  happens: office, kiosk, Pi, or local server.
- Gemma is small enough for edge/on-prem deployment, but capable enough for
  intent resolution, transcript repair, planner/composer behavior, and grounded
  answer writing.
- Gemma let us separate the system into inspectable parts: deterministic
  resolver/source routing plus a model that composes only from provided context.
- Gemma made privacy plausible: sensitive questions do not have to start by
  leaving the office.
- The failed SFT run was useful too: it proved we should not train the model to
  memorize government facts; we should train it to plan, ask, cite, and refuse.

One clean line:

> Gemma was pivotal because it made the helpdesk local: not just a cloud demo,
> but a model small enough to sit inside the office and honest enough to ask
> before it answers.

## Tight shot-to-script mapping

0:00-0:25:

- Reddit origin card.
- Office/path confusion text.
- Road/queue/form shots.

0:25-0:45:

- Training/tmux footage.
- Jiri travel.
- Founder line about privilege.

0:45-1:10:

- Gemma + source registry + planner.
- Caption: "open model + official sources + practical knowledge".

1:10-1:40:

- `/chat` and `/kiosk` showing intake.
- Ambiguous question -> follow-up.

1:40-2:05:

- Jiri meeting/interview.
- Admin practical-source review.

2:05-2:35:

- 3-4 people using kiosk.
- TTS/ASR snippets.
- WhatsApp snippet.

2:35-2:55:

- Pi local Gemma E2B.
- Office computer/kiosk setup.

2:55-3:00:

- End line: "public-service knowledge before privilege."

## Capture checklist

- 3-4 kiosk users outside.
- 1 office-like kiosk setup.
- Physical Pi + local terminal demo.
- Clean `/kiosk` voice capture.
- Clean `/chat` source capture.
- Clean `/whatsapp` capture with private info hidden.
- Founder line: "Gemma was pivotal because..."
- Founder line: "I used privilege to find the path..."
- Consent notes for faces/voices.
