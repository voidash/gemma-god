# PreVillage Gemma for Good - Source-of-Truth Sequence Spec v1

Deadline: 2026-05-19 05:44 NPT.

Target runtime: 3:00.

This is now the edit source of truth. Treat `rough_spec_v3_timeline.md` as
scratch notes and rationale; edit from this file.

All paths are relative to:

```text
/Volumes/TRANSCEND/video-creation/previllage-gemma-for-good-2026
```

## Locked Story

PreVillage is a voice-first government-service navigator. It turns privileged
government know-how into public infrastructure by asking first, checking
official and practical sources, reaching officers when sources are missing, and
running close to the office on small local hardware.

Final title-card definition:

```text
PreVillage is a voice-first government-service navigator.
It asks first, checks official and practical sources,
reaches officers when sources are missing,
and can run inside the office.
```

Final line:

```text
PreVillage exists because it is still a privilege
to navigate government services.
```

## Locked Audio

Use:

```text
audio/narration/previllage_narration_20260518_113426_16k_mono.wav
```

Timing helper:

```text
analysis/transcripts/chirp2/narration_20260518_113426/chirp2_word_beats.tsv
analysis/transcripts/chirp2/narration_20260518_113426/chirp2_subtitle_en.srt
```

Chirp2 mishears several terms. Correct them in captions:

```text
VZERA -> v0
JMA / P portal -> Gemma was pivotal
SR / ESR -> ASR
TS / TDS -> TTS
root -> route
privilege when used as product name -> PreVillage
dataset knowledge -> tacit knowledge
```

Recorded VO starts at about `0:01.04` and ends at about `2:42.84`. Use
`2:43-3:00` for the definition/title close and optional music tail.

## Edit Rules

- The viewer must understand what happens at every point in time.
- Every scene must prove one part of the argument.
- Do not add decorative footage unless it supports the beat.
- Keep overlays short; the VO carries the detail.
- Use original location/interview audio only when it is stronger than narration,
  and duck narration under it.
- If a referenced clip is too weak, replace it with another clip that proves the
  same scene purpose. Do not change the purpose without updating this spec.

## Whole Video Timeline

### S01 - Cold Open

Time: `0:00-0:02`

Purpose: Establish that this is a lived public-service problem, not a generic
AI demo.

VO cue:

```text
Nepal has a problem.
```

Visual stack:

- Start on recreated Reddit-origin card.
- Add kinetic text over it.
- Keep the frame still enough to read the problem.

Assets:

```text
assets/graphics/reddit_origin_card_1920x1080.png
assets/graphics/reddit_origin_card_1920x1080.svg
```

Overlay:

```text
Nepal has a problem.
```

Status: ready.

### S02 - Hidden Knowledge Has A Price

Time: `0:02-0:07`

Purpose: Make the origin story concrete: time, offices, repeated forms, and
money paid because the route was hidden.

VO cue:

```text
Three weeks. Four offices. Four versions of the same form.
Almost eight thousand rupees paid to middlemen.
```

Visual stack:

- Cut from Reddit card into the four-office route graphic.
- Animate the cards in this order: OCR/CAMIS, IRD Tripureshwor, IRD Kalimati,
  IRD Kalanki.
- Stamp or duplicate one form at each redirect.

Assets:

```text
assets/graphics/four_office_route_map_1920x1080.png
assets/graphics/four_office_route_map_1920x1080.svg
assets/sources/forms/mock_government_form_document.pdf
assets/sources/four_office_route/capture_manifest.tsv
```

Overlay:

```text
3 weeks / 4 offices / 4 forms / Rs 8k
```

Status: ready.

### S03 - Not A One-Off

Time: `0:07-0:15`

Purpose: Prove the Reddit story is part of a broader middlemen/routing problem.

VO cue:

```text
People are leveraging lack of proper pipeline and well documentation.
I wanted to solve this.
```

Visual stack:

- Rapid newspaper-style montage of middlemen headlines.
- Cut between article screenshots and real office/form footage.
- End on the line that the issue is structural.

Assets:

```text
assets/sources/middlemen_news/SELECTS.tsv
assets/sources/middlemen_news/screenshots/01b_myrepublica_amp_good_governance_on_hold.png
assets/sources/middlemen_news/screenshots/02_rising_nepal_ending_sway_middlemen.png
assets/sources/middlemen_news/screenshots/03_ekantipur_middlemen_prohibited_land_revenue.png
assets/sources/middlemen_news/screenshots/04_ratopati_land_revenue_middlemen_crackdown.png
assets/sources/middlemen_news/screenshots/05_nepalnews_brokers_hijack_services.png
assets/sources/middlemen_news/screenshots/06_arthasarokar_sarlahi_middlemen.png
footage/selects/story_clips/fieldwork_jiri_office_form_laptop.mp4
```

Overlay:

```text
People pay for information,
not the service.
```

Status: ready.

### S04 - E-Governance Gap

Time: `0:15-0:23`

Purpose: Diagnose the problem as UX plus documented and undocumented tacit
knowledge.

VO cue:

```text
It's the gap every country transitioning into modern e-governance faces.
Nepal has internet forms, but you still have to visit offices.
```

Visual stack:

- Use form/process reference clip as background.
- Overlay the process graphic: online form -> print/check -> office visit ->
  redirect -> repeat.
- Separate documented knowledge from tacit knowledge.

Assets:

```text
footage/selects/story_clips/forms_process_reference_20260518_122823.mp4
assets/graphics/form_process_overlay_1920x1080.png
assets/graphics/form_process_overlay_1920x1080.svg
assets/references/process_animation_reference_image_1.png
```

Overlay:

```text
documented knowledge: forms, PDFs, notices
tacit knowledge: room, counter, timing, officer
```

Status: ready.

### S05 - Privilege Flex

Time: `0:23-0:30`

Purpose: Introduce privilege honestly: the founder could keep pushing because
of compute, technical knowledge, help, and obsession.

VO cue:

```text
I had privilege: GPU access, technical knowledge, people who helped me,
and obsession to keep debugging.
```

Visual stack:

- Start with sister/voice-collection footage full screen.
- Split into AWS/GPU footage.
- Split again into training/tmux footage.
- Let this feel like work, not vanity.

Assets:

```text
footage/selects/story_clips/voice_collection_sister.mp4
footage/selects/story_clips/aws_ec2_gpu_access.mp4
footage/selects/story_clips/training_tmux_status.mp4
```

Overlay:

```text
GPU access
technical knowledge
people who helped
obsession to debug
```

Status: ready.

### S06 - v0 Was Web-First

Time: `0:30-0:36`

Purpose: Show that the first solution worked, but still assumed web literacy.

VO cue:

```text
With which v0 was born. It was a web interface where people could type questions.
But that was a Kathmandu solution.
```

Visual stack:

- Show web chat and source-backed answer.
- Show SFT/eval screen briefly as proof of iteration.
- Make the interface look useful but insufficient.

Assets:

```text
footage/selects/story_clips/web_question_box_or_chat.mp4
footage/selects/story_clips/sft_eval_dashboard.mp4
```

Overlay:

```text
v0: type a question
useful, but still web-first
```

Status: ready.

### S07 - Leaving Kathmandu

Time: `0:36-0:42`

Purpose: Move the story from desk/laptop privilege into field reality.

VO cue:

```text
Kathmandu itself is a privilege.
So I travelled 180 kilometers to Jiri...
```

Visual stack:

- On the word "privilege", use a large text mask that opens into mountains.
- Cut to road/motorcycle footage.
- End with arrival or office exterior.

Assets:

```text
footage/selects/story_clips/jiri_mountain_wide.mp4
footage/selects/story_clips/road_to_jiri_motorcycle.mp4
footage/selects/story_clips/arrival_office_compound.mp4
```

Overlay:

```text
180 km to Jiri
Kathmandu is also privilege
```

Status: ready.

### S08 - Fieldwork Changed Product

Time: `0:42-0:50`

Purpose: Show that the Jiri trip changed product assumptions.

VO cue:

```text
That trip changed the product.
The problem was not only lack of information, but also a UX problem.
```

Visual stack:

- Start with Jiri meeting context.
- Use the Android/TikTok/Facebook/call quote as the evidence.
- Keep subtitles readable; optionally duck narration under the quote.

Assets:

```text
footage/selects/story_clips/jiri_meeting_phone_ux_context.mp4
footage/selects/story_clips/jiri_android_tiktok_facebook_call_quote.mp4
footage/selects/story_clips/public_pitch_gemma_screen.mp4
```

Subtitle:

```text
Android phone त TikTok हेर्ने, Facebook हेर्ने,
अनि फोन गर्नेभन्दा अरू जान्दै जान्दैनन्।
```

Overlay:

```text
fieldwork changed the product
```

Status: ready; subtitle timing still needs final cut.

### S09 - To Not Lay / To Lay

Time: `0:50-1:05`

Purpose: Land the "PreVillage / privi lays" idea: lay infrastructure on already
learned UX instead of forcing people through portals.

VO cue:

```text
The internet of Nepal wasn't built for PDFs, HTML forms, and buttons...
People already know how to speak, call, and use WhatsApp.
I thought maybe we should start there.
```

Visual stack:

- Left side: portals, PDFs, forms, buttons, popups.
- Right side: WhatsApp, kiosk, voice.
- On "privi lays", cut in the hen clip for a short visual joke.
- Return immediately to product proof so the joke does not dominate.

Assets:

```text
footage/selects/story_clips/gov_homepage_montage_20sites.mp4
footage/selects/story_clips/whatsapp_company_darta_user.mp4
footage/selects/story_clips/whatsapp_bihe_darta_user.mp4
footage/selects/story_clips/kiosk_voice_asr_pi.mp4
footage/selects/story_clips/privi_lays_hen_06s_08s.mp4
```

Overlay:

```text
TO NOT LAY: PDFs / forms / buttons
TO LAY: voice / call / WhatsApp / kiosk
```

Status: ready.

### S10 - Human Sentence Becomes Route

Time: `1:05-1:13`

Purpose: Explain the resolver job in human language.

VO cue:

```text
A citizen does not begin with a portal URL.
They ask naturally: Dharmadevi Nagarpalika, marriage registration,
how do I do it?
That is the job: turn a human sentence into a route.
```

Visual stack:

- Use marriage-registration WhatsApp clip.
- Extract three labels from the sentence.
- If the phone text says a different municipality, keep the phone less readable
  and make the overlay match the VO.

Assets:

```text
footage/selects/story_clips/bihe_darta_question_tight.mp4
footage/selects/story_clips/bihe_darta_compact_workflow.mp4
footage/selects/story_clips/whatsapp_bihe_darta_user.mp4
```

Overlay:

```text
WHERE   -> Dharmadevi Nagarpalika
SERVICE -> marriage registration
INTENT  -> how do I do it?
```

Status: ready.

### S11 - Why Gemma

Time: `1:13-1:20`

Purpose: Make Gemma pivotal: open, small enough for local deployment, capable
enough for messy service navigation.

VO cue:

```text
Gemma was pivotal because it is small enough for local deployment...
```

Visual stack:

- Lead with Raspberry Pi physical shot.
- Cut to local inference terminal.
- Use benchmark text sparingly.

Assets:

```text
footage/selects/story_clips/pi_gemma_local_inference_smoke_test.mp4
```

Overlay:

```text
Gemma on Raspberry Pi
local enough for offices
```

Optional data card:

```text
Gemma E2B Q4 via llama.cpp
~6-8 generated tokens/sec on short service-navigation answers
```

Status: ready.

### S12 - Ask First, Answer Second

Time: `1:20-1:26`

Purpose: Show that this is a navigator, not a generic answering machine.

VO cue:

```text
It can reason through messy ASR text, ask the next question,
and compose from sources. The first job is not to answer,
but to understand the case.
```

Visual stack:

- Show vague prompt.
- Show compact follow-up.
- Then show source-backed answer.

Assets:

```text
footage/selects/story_clips/chat_ask_first_sources.mp4
footage/selects/story_clips/kiosk_voice_asr_pi.mp4
```

Overlay:

```text
understand first
answer second
```

Status: ready.

### S13 - RAG Is Necessary But Not Enough

Time: `1:26-1:38`

Purpose: Introduce official source layer, crawler, health checks, and self-healing
source maintenance.

VO cue:

```text
RAG alone is weak when truth is scattered across old websites,
PDFs, office habits, and the memory of one contact officer.
So I built a registry of 800+ government sources, crawlers,
health checks, and a self-healing pipeline.
```

Visual stack:

- Flash many government sites.
- Cut to source registry / DigoBikas scraping tmux.
- Push into architecture diagram on "self-healing pipeline."

Assets:

```text
footage/selects/story_clips/gov_homepage_montage_20sites.mp4
footage/selects/story_clips/digobikas_scraping_tmux.mp4
assets/graphics/previllage_system_architecture_1920x1080.png
assets/graphics/previllage_system_architecture_1920x1080.svg
```

Overlay:

```text
800+ government sources
crawl / health check / repair
```

Status: ready.

### S14 - Field Interviews Capture Practical Truth

Time: `1:38-1:50`

Purpose: Show how tacit office knowledge enters the system.

VO cue:

```text
With this I also created a pipeline to capture tacit knowledge.
Government officials can answer simple questions that never go documented.
```

Visual stack:

- Use Jiri officer interview.
- Show interview questions visually, not as dense paragraphs.
- Prefer the human face over screen UI here.

Assets:

```text
footage/selects/story_clips/jiri_officer_interview_full.mp4
```

Best interview targets:

```text
0:45-1:00   inquiry counter / citizens routed to departments
1:00-1:35   commonly forgotten documents
1:55-2:20   why citizens are sent back
2:25-2:35   check if office is open
```

Overlay:

```text
Which counter first?
Which room?
What time is easiest?
Which document do people forget?
Why are they sent back?
```

Status: ready; final subclip selection still needed.

### S15 - Review Turns Interview Into Source

Time: `1:50-2:05`

Purpose: Prove the human knowledge is reviewed and citeable, not dumped straight
into answers.

VO cue:

```text
Those answers go through review, become practical sources,
and can be cited later beside official government sources.
Tacit knowledge is only unfair when it stays trapped in one office corridor.
```

Visual stack:

- Interview footage transitions into admin review UI.
- Show approve/transcribe/reject controls.
- Cut to answer with source list.

Assets:

```text
footage/selects/story_clips/admin_interview_review_transcribe.mp4
footage/selects/story_clips/chat_ask_first_sources.mp4
footage/selects/story_clips/source_reference_pitch.mp4
```

Overlay:

```text
interview -> review -> practical source -> cited answer
```

Status: ready.

### S16 - Human Loop When Source Is Missing

Time: `2:05-2:24`

Purpose: Show the anti-hallucination behavior and officer outreach loop.

VO cue:

```text
When PreVillage does not know, it should not hallucinate.
It says what is missing, shows what sources it checked,
and turns the citizen's question into an officer outreach message
through the WhatsApp bridge.
The answer is not invented. It is asked, reviewed,
and folded back into the system for the next person.
```

Visual stack:

- Show "no authoritative source" moment.
- Show checked sources.
- Show WhatsApp/officer outreach message.
- Show loop arrow back to practical source/admin review.

Assets:

```text
footage/selects/story_clips/whatsapp_officer_outreach.mp4
footage/selects/story_clips/admin_interview_review_transcribe.mp4
assets/graphics/previllage_system_architecture_1920x1080.png
```

Overlay:

```text
no source?
do not hallucinate
ask officer
review reply
fold back
```

Status: ready.

### S17 - Custom Voice Stack

Time: `2:24-2:36`

Purpose: Show the ASR/TTS grunt work and why voice matters in Nepal.

VO cue:

```text
The internet UX of forms and buttons was not made with Nepali people in mind.
Nepal is voice and language rich. So I trained our own TTS and ASR too.
```

Visual stack:

- Sister voice collection.
- ASR/TTS/G2P UI.
- Training/eval glimpses.
- Keep it fast but explicit: this is not just a chatbot.

Assets:

```text
footage/selects/story_clips/voice_collection_sister.mp4
footage/selects/story_clips/tts_huggingface_kala.mp4
footage/selects/story_clips/tts_epoch_g2p_comparison.mp4
footage/selects/story_clips/g2p_newari_dialect_review.mp4
footage/selects/story_clips/training_tmux_status.mp4
```

Overlay:

```text
custom Nepali ASR
custom Nepali TTS
G2P review
voice data collection
```

Status: ready.

### S18 - Voice Pipeline In Action

Time: `2:36-2:45`

Purpose: Connect ASR, Gemma, RAG, and TTS into one understandable pipeline.

VO cue:

```text
A citizen speaks. Our Nepali ASR transcribes.
Gemma fixes the rough text and plans the intent.
Retrieval finds official and practical sources.
Our Nepali TTS speaks back.
```

Visual stack:

- Kiosk voice clip as the proof.
- Overlay simple pipeline text.
- Cut to architecture diagram only if needed.

Assets:

```text
footage/selects/story_clips/kiosk_voice_asr_pi.mp4
assets/graphics/previllage_system_architecture_1920x1080.png
```

Overlay:

```text
speak -> ASR -> Gemma fix -> intent -> retrieve -> TTS
```

Status: ready.

### S19 - Office Deployment

Time: `2:45-2:52`

Purpose: Show that the office does not need an L40 GPU; the heavy work builds
knowledge, the local device runs the helpdesk.

VO cue:

```text
On WhatsApp and kiosks in the office, help starts where people already ask for help.
PreVillage is small enough to run on Raspberry Pi for compute and centralized enough
to share and capture tacit knowledge.
```

Visual stack:

- Pi shot.
- Kiosk/WhatsApp shot.
- Architecture diagram focused on local office + shared knowledge.

Assets:

```text
footage/selects/story_clips/pi_gemma_local_inference_smoke_test.mp4
footage/selects/story_clips/kiosk_voice_asr_pi.mp4
footage/selects/story_clips/whatsapp_bihe_darta_user.mp4
assets/graphics/previllage_system_architecture_1920x1080.png
```

Overlay:

```text
heavy work builds the knowledge
small local model runs the helpdesk onsite
```

Status: ready.

### S20 - Definition And Close

Time: `2:52-3:00`

Purpose: Make the conclusion say what PreVillage is, then end on the privilege
line.

VO cue:

```text
Use title-card close. Recorded narration ends before the final definition is fully clear.
```

Visual stack:

- Start on architecture diagram.
- Simplify into title card.
- Optional mountain/road texture behind final wordmark.

Assets:

```text
assets/graphics/previllage_system_architecture_1920x1080.png
footage/selects/story_clips/jiri_mountain_wide.mp4
footage/selects/story_clips/road_to_jiri_motorcycle.mp4
```

Overlay:

```text
PreVillage is a voice-first government-service navigator.

It asks first.
It checks official and practical sources.
It reaches officers when sources are missing.
It can run inside the office.

PreVillage
public-service knowledge before privilege

PreVillage exists because it is still a privilege
to navigate government services.
```

Status: ready.

## Required Captions / Subtitle Fixes

Use clean captions, not raw Chirp2 captions, for the major misheard terms:

```text
PreVillage
Gemma
ASR
TTS
RAG
Raspberry Pi
tacit knowledge
government-service navigator
```

For the Jiri phone quote, use Nepali subtitle:

```text
Android phone त TikTok हेर्ने, Facebook हेर्ने,
अनि फोन गर्नेभन्दा अरू जान्दै जान्दैनन्।
```

## Asset Registry For This Spec

Primary graphics:

```text
assets/graphics/reddit_origin_card_1920x1080.png
assets/graphics/four_office_route_map_1920x1080.png
assets/graphics/form_process_overlay_1920x1080.png
assets/graphics/previllage_system_architecture_1920x1080.png
```

Primary evidence/source folders:

```text
assets/sources/middlemen_news/
assets/sources/four_office_route/
assets/sources/forms/mock_government_form_document.pdf
```

Primary clips:

```text
footage/selects/story_clips/voice_collection_sister.mp4
footage/selects/story_clips/aws_ec2_gpu_access.mp4
footage/selects/story_clips/training_tmux_status.mp4
footage/selects/story_clips/web_question_box_or_chat.mp4
footage/selects/story_clips/sft_eval_dashboard.mp4
footage/selects/story_clips/jiri_mountain_wide.mp4
footage/selects/story_clips/road_to_jiri_motorcycle.mp4
footage/selects/story_clips/arrival_office_compound.mp4
footage/selects/story_clips/jiri_android_tiktok_facebook_call_quote.mp4
footage/selects/story_clips/whatsapp_bihe_darta_user.mp4
footage/selects/story_clips/kiosk_voice_asr_pi.mp4
footage/selects/story_clips/pi_gemma_local_inference_smoke_test.mp4
footage/selects/story_clips/chat_ask_first_sources.mp4
footage/selects/story_clips/digobikas_scraping_tmux.mp4
footage/selects/story_clips/jiri_officer_interview_full.mp4
footage/selects/story_clips/admin_interview_review_transcribe.mp4
footage/selects/story_clips/whatsapp_officer_outreach.mp4
footage/selects/story_clips/tts_huggingface_kala.mp4
footage/selects/story_clips/tts_epoch_g2p_comparison.mp4
footage/selects/story_clips/g2p_newari_dialect_review.mp4
```

## Still Needs Human Edit Decisions

These are edit choices, not blockers:

- Pick the exact 8-10 seconds inside `jiri_android_tiktok_facebook_call_quote.mp4`.
- Pick the exact interview snippets from `jiri_officer_interview_full.mp4`.
- Decide whether the hen/privi-lays clip is a 0.5-second flash or a 2-second beat.
- Decide whether the final close uses mountain footage or a clean graphic-only card.

## Validation Checklist

- The first 15 seconds make the problem understandable without explanation.
- By 0:50, the viewer understands why the product changed after fieldwork.
- By 1:26, the viewer understands "navigator, not chatbot."
- By 1:59, the viewer understands practical human sources.
- By 2:24, the viewer understands the human loop when sources are missing.
- By 2:45, the viewer understands custom ASR/TTS plus Gemma pipeline.
- By 3:00, the viewer can answer: "What is PreVillage?"
