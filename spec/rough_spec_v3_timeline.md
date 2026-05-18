# PreVillage Gemma for Good - Timeline-First Edit Spec v3

Deadline: 2026-05-19 05:44 NPT.

Target runtime: 3:00.

Superseded for editing by:

```text
spec/sequence_spec_v1.md
```

Keep this file as scratch notes and rationale. Use `sequence_spec_v1.md` as the
source-of-truth edit spec.

## Core Argument

PreVillage turns privileged government-service know-how into a public, voice-first
navigator: it asks first, checks official and practical sources, reaches a human
officer when knowledge is missing, and can run inside a local office.

This argument serves one job in the edit: every shot must prove one part of that
sentence.

## Core Line

Use this as the final title-card line if it is not fully present in the recorded
voiceover:

```text
PreVillage exists because it is still a privilege to navigate government services.
```

Supporting title:

```text
public-service knowledge before privilege
```

## Audio Source

Recorded narration:

```text
audio/narration/previllage_narration_20260518_113426_16k_mono.wav
```

Chirp2 timing:

```text
analysis/transcripts/chirp2/narration_20260518_113426/chirp2_word_beats.tsv
analysis/transcripts/chirp2/narration_20260518_113426/chirp2_subtitle_en.srt
```

Recorded VO starts around `0:01.04` and ends around `2:42.84`. Use the last
17 seconds for architecture/title/close.

Chirp2 is only for timing. It mishears project words like PreVillage, Gemma,
ASR, TTS, and RAG.

## Readable Clip Folder

Use these readable aliases while editing:

```text
footage/selects/story_clips/
```

The original file mapping is preserved here:

```text
footage/selects/story_clips/ALIASES.tsv
```

These are symlinks on the SSD, so the original footage was not renamed or
destroyed. The spec below uses the readable alias filenames.

## Timeline

### 0:00-0:02 - Cold Open

VO cue:

```text
Nepal has a problem.
```

Screen:

- Show the kinetic typography that shows "Nepal has a problem"
- The background is our created reddit interface
- Hold just long enough for the viewer to understand this came from lived pain.

Clip / asset:

```text
GRAPHIC: reddit_origin_card
source: assets/graphics/reddit_origin_card_1920x1080.png
editable: assets/graphics/reddit_origin_card_1920x1080.svg
what happens: recreated r/Nepal-style post card shows the origin story and the core numbers.
```

Overlay:

```text
Nepal has a problem.
```

### 0:02-0:07 - Cost Of Hidden Knowledge

VO cue:

```text
Three weeks, four offices, four versions of the same form...
```

Screen:

- Show the four-office route graphic as the first clean explanation of the
  pain:
  - OCR / CAMIS;
  - IRD Tripureshwor;
  - IRD Kalimati;
  - IRD Kalanki.
- Animate one copy of the same form being stamped again and again as the route
  moves office to office.
- Keep the Reddit-origin backdrop or text texture underneath if the frame needs
  more lived-context weight.

Assets:

```text
four_office_route_map
source: assets/graphics/four_office_route_map_1920x1080.svg
rendered: assets/graphics/four_office_route_map_1920x1080.png
what happens: 3 weeks / 4 offices / 4 forms / Rs 8k are connected to a concrete route.

mock_form_document
source: assets/sources/forms/mock_government_form_document.pdf
what happens: form texture for the repeated-form animation.

four_office_sources
source: assets/sources/four_office_route/capture_manifest.tsv
what happens: official OCR/CAMIS and IRD office pages used as evidence for the route labels.
```

### 0:07-0:15 - Forms Exist, Route Is Missing

VO cue:

```text
People are leveraging lack of proper pipeline and documentation...
```

Screen:
- Cycle the middlemen/news screenshots rapidly in a newspaper-style edit.
- Use these as proof that the Reddit story is not a one-off.
- Cut in office/forms/laptop/papers so the problem is not abstract websites.

Clips:

```text
middlemen_news_montage
source: assets/sources/middlemen_news/SELECTS.tsv
what happens: six usable article screenshots show middlemen/broker/governance headlines.

gov_homepage_montage_20sites
source: footage/selects/story_clips/gov_homepage_montage_20sites.mp4
what happens: 20 government sites flash by; some load, some fail, some have popups.

fieldwork_jiri_office_form_laptop
source: footage/selects/story_clips/fieldwork_jiri_office_form_laptop.mp4
what happens: Jiri office desk, laptop form, papers, officials around the process.
```

Overlay:

```text
internet forms exist
but the path is still hidden
```

### 0:15-0:23 - UX + Tacit Knowledge

VO cue:

```text
Nepal has internet forms, but you still have to visit offices...
problem of UX, documented and undocumented tacit knowledge.
```

you can use this : `footage/selects/story_clips/forms_process_reference_20260518_122823.mp4`
But at a same time create a svg animation on the front where people fill forms first

Here is the reference style i am targetting for the animation that runs in front while the forms are shown in the back:
`assets/references/process_animation_reference_image_1.png`
the animation should show hassle of going through multiple processes first fill form online and go offline stuff

Created overlay asset:

```text
form_process_overlay
source: assets/graphics/form_process_overlay_1920x1080.png
editable: assets/graphics/form_process_overlay_1920x1080.svg
what happens: online form -> print/check -> visit office -> redirect -> repeat loop,
with documented knowledge and tacit knowledge separated at the bottom.
```

Screen:

- Government sites/PDF surfaces.
- Office counter or laptop form.
- Quick labels for two kinds of knowledge.

Clips:

```text
gov_sites_fragile_surface
source: footage/selects/story_clips/gov_homepage_montage_20sites.mp4
what happens: websites and errors show why source maintenance matters.

office_form_context
source: footage/selects/story_clips/fieldwork_jiri_office_form_laptop.mp4
what happens: real office workflow around papers and a digital form.
```

Overlay:

```text
documented knowledge: buried in PDFs
undocumented knowledge: rooms, counters, timing
```

Add more footage here if it shows forms, PDF, office rooms, or people being
redirected.

### 0:23-0:30 - Privilege Flex

VO cue:

```text
I have privilege. GPU access, technical knowledge, people who help me...
```

Screen:

- Three-part flex montage.
- First clip full screen, second splits to half, third splits to thirds.

Clips:

```text
voice_collection_sister
source: footage/selects/story_clips/voice_collection_sister.mp4
what happens: sister/voice contributor speaks into mic while looking at laptop.

aws_ec2_gpu_access
source: footage/selects/story_clips/aws_ec2_gpu_access.mp4
what happens: AWS EC2 dashboard and cost/resource view.

training_tmux_status
source: footage/selects/story_clips/training_tmux_status.mp4
what happens: terminal panes show training logs, ASR/TTS workers, RAG audit/demo status.
```

Overlay:

```text
GPU access
technical knowledge
people who helped
obsession to keep debugging
```

### 0:30-0:36 - v0 Was A Kathmandu Solution

VO cue:

```text
with which v0 was born. It was a web interface where people could type questions,
but that was a Kathmandu solution.
```

show ampixa website you can click images showing how we had nailed references and chat helpdesk.ampixa.com

Screen:

- Show web/chat UI or SFT/dashboard.
- It should feel useful but incomplete.

Clips:

```text
web_question_box_or_chat
source: footage/selects/story_clips/web_question_box_or_chat.mp4
what happens: PreVillage chat UI receives a Nepali query and shows sourced response.

sft_eval_dashboard
source: footage/selects/story_clips/sft_eval_dashboard.mp4
what happens: SFT evaluation dashboard with Nepali question/answer and human review controls.
```

Overlay:

```text
v0: type a question
useful, but still web-first
```

### 0:36-0:42 - 180 Km To Jiri

VO cue:

when i say privilege i want a text mask that matches when i say privilege and it comes when i say privilege
```text
Kathmandu itself is a privilege. So I travelled 180 km to Jiri...
```

Screen:

- Privilege text mask clears into mountain/road footage.
- Make this feel like leaving the web interface behind.

Clips:

```text
jiri_mountain_wide
source: footage/selects/story_clips/jiri_mountain_wide.mp4
what happens: wide mountain landscape, valley, distant peaks.

road_to_jiri_motorcycle
source: footage/selects/story_clips/road_to_jiri_motorcycle.mp4
what happens: motorcycle POV on winding mountain road.

arrival_office_compound
source: footage/selects/story_clips/arrival_office_compound.mp4
what happens: motorcycle enters a compound, likely the office arrival.
```

Overlay:

```text
180 km to Jiri
Kathmandu is also privilege
```

### 0:42-0:50 - Trip Changed Product

VO cue:

```text
That trip changed the product.
```

There is a 14 sec video . where they are saying people use android phones i want it used here.

Screen:

- Jiri meeting room.
- The viewer should understand: product direction changed because of fieldwork.

Clips:

```text
jiri_meeting_phone_ux_context
source: footage/selects/story_clips/jiri_meeting_phone_ux_context.mp4
what happens: meeting room discussion about how people use Android phones.

public_pitch_gemma_screen
source: footage/selects/story_clips/public_pitch_gemma_screen.mp4
what happens: presenter stands near screen discussing Gemma.
```

Overlay:

```text
fieldwork changed the product
```

### 0:50-1:00 - To Not Lay: Bad Fit UX

VO cue:

```text
The internet of Nepal wasn't built for PDFs, HTML forms, and buttons...
```

Screen:

- Use the Jiri phone quote here.
- Let the subtitle carry the point even if you keep narration underneath.
- If using original quote audio, duck VO briefly.

Clips:

```text
jiri_android_tiktok_facebook_call_quote
source: footage/selects/story_clips/jiri_android_tiktok_facebook_call_quote.mp4
what happens: Jiri official says people mostly use Android for TikTok, Facebook, and calls.

gov_sites_forms_buttons
source: footage/selects/story_clips/gov_homepage_montage_20sites.mp4
what happens: portals/forms/errors/popups show the web-first surface.
```

Subtitle:

```text
Android phone त TikTok हेर्ने, Facebook हेर्ने,
अनि फोन गर्नेभन्दा अरू जान्दै जान्दैनन्।
```

Overlay:

```text
TO NOT LAY
PDFs / forms / buttons / portals
```

### 1:00-1:05 - To Lay: Already Learned UX

VO cue:

```text
People already know how to speak, call and use WhatsApp.
```

Screen:

- Cut from portal/forms into phone/WhatsApp/kiosk.

Clips:

```text
whatsapp_company_darta_user
source: footage/selects/story_clips/whatsapp_company_darta_user.mp4
what happens: woman asks how to register a company and scrolls chat response.

whatsapp_bihe_darta_user
source: footage/selects/story_clips/whatsapp_bihe_darta_user.mp4
what happens: woman asks about marriage registration in Nepali through WhatsApp-like flow.

kiosk_voice_asr_pi
source: footage/selects/story_clips/kiosk_voice_asr_pi.mp4
what happens: tablet listens/transcribes Nepali speech with Raspberry Pi visible.
```

Overlay:

```text
TO LAY
voice / call / WhatsApp / kiosk
```

there should be where i have said "privi lays" i want hen footage
`footage/selects/story_clips/privi_lays_hen_06s_08s.mp4` where it says privi lays.
Full source is staged at `footage/selects/story_clips/privi_lays_hen_source.mp4`.


### 1:05-1:13 - Human Sentence To Route

VO cue:

```text
A citizen doesn't begin with a portal URL.
They ask naturally: Dharmadevi Nagarpalika, marriage registration, how do I do it?
```

Screen:

- Use the bihe darta clip.
- Overlay phrase extraction: where, service, intent.

Clips:

```text
bihe_darta_question_tight
source: footage/selects/story_clips/bihe_darta_question_tight.mp4
what happens: tight clip of the marriage registration question.

bihe_darta_compact_workflow
source: footage/selects/story_clips/bihe_darta_compact_workflow.mp4
what happens: question flows into system handling.
```

Overlay:

```text
WHERE   -> Dharmadevi Nagarpalika
SERVICE -> marriage registration
INTENT  -> how do I do it?
```

Note:

```text
Existing footage may say Kirtipur/Bihe Darta. If the recorded VO says
Dharmadevi, keep the phone text less readable and let the overlay match VO.
```

### 1:13-1:20 - Gemma Runs Locally

VO cue:

```text
Gemma was pivotal because it is small enough for local deployment...
```

Screen:

- Raspberry Pi first.
- Then terminal/smoke-test result.

Clips:

```text
pi_gemma_local_inference_smoke_test
source: footage/selects/story_clips/pi_gemma_local_inference_smoke_test.mp4
what happens: Raspberry Pi close-up and terminal/iPad showing Gemma 2B local inference stats.
```

Overlay:

```text
Gemma on Raspberry Pi
local enough for offices
```

### 1:20-1:26 - Ask First, Then Answer

VO cue:

```text
reason through messy ASR text, ask the next question, and compose from sources.
The first job is not to answer, but to understand the case.
```

Screen:

- Show product asking a follow-up.
- Then source-backed answer.

Clips:

```text
chat_ask_first_sources
source: footage/selects/story_clips/chat_ask_first_sources.mp4
what happens: vague prompt -> compact follow-up -> Jiri answer with SOURCES USED.

kiosk_voice_asr_pi
source: footage/selects/story_clips/kiosk_voice_asr_pi.mp4
what happens: spoken Nepali appears as ASR transcript on tablet.
```

Overlay:

```text
understand first
answer second
```

### 1:26-1:38 - RAG + Self-Healing Source Layer

VO cue:

```text
RAG alone is weak...
registry of 800+ government sources, crawlers, health checks, and a self-healing pipeline.
```

Screen:

- Government homepage montage for scale.
- DigoBikas/source list to terminal.
- Architecture diagram push-in.

Clips / assets:

```text
gov_homepage_montage_20sites
source: footage/selects/story_clips/gov_homepage_montage_20sites.mp4
what happens: many government source surfaces flash by.

digobikas_scraping_tmux
source: footage/selects/story_clips/digobikas_scraping_tmux.mp4
what happens: government websites list, then terminal scraping/processing.

system_architecture
source: assets/graphics/previllage_system_architecture_1920x1080.png
what happens: diagram shows entry points, ASR/Gemma, resolver, RAG, practical sources, human loop.
```

Overlay:

```text
800+ government sources
crawl / health check / repair
```

### 1:38-1:47 - Interviews Capture Tacit Knowledge

VO cue:

```text
I also created a pipeline to capture tacit knowledge.
Government officials can answer simple questions that never go documented.
```

Screen:

- Use the real interview.
- Keep it human and specific.

Clip:

```text
jiri_officer_interview_full
source: footage/selects/story_clips/jiri_officer_interview_full.mp4
what happens: Jiri official explains office name, inquiry counter, forgotten documents, why citizens get sent back.
```

Best moments:

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
Which document do people forget?
Why are they sent back?
```

### 1:47-1:59 - Review Becomes Practical Source

VO cue:

```text
Those answers go through review, become practical sources, and can be cited later...
Tacit knowledge is only unfair when it stays trapped in one office corridor.
```

Screen:

- Interview -> admin review -> cited answer.
- This is the important proof that interviews become infrastructure.

Clips:

```text
admin_interview_review_transcribe
source: footage/selects/story_clips/admin_interview_review_transcribe.mp4
what happens: admin page shows interview submissions, audio players, approve/transcribe/reject controls.

chat_ask_first_sources
source: footage/selects/story_clips/chat_ask_first_sources.mp4
what happens: answer displays SOURCES USED from citizen/interview source.
```

Overlay:

```text
interview -> review -> practical source -> cited answer
```

### 1:59-2:15 - If Source Is Missing, Ask An Officer

VO cue:

```text
When PreVillage does not know, it should not hallucinate...
The answer is not invented. It is asked, reviewed, and folded back.
```

Screen:

- Show the WhatsApp/outreach flow clearly.
- This is the human-in-the-loop proof.

Clip:

```text
whatsapp_officer_outreach
source: footage/selects/story_clips/whatsapp_officer_outreach.mp4
what happens: WhatsApp demo says no authoritative source and drafts officer outreach message.
```

Overlay:

```text
no source?
do not hallucinate
ask officer
review reply
fold back
```

### 2:15-2:25 - We Trained Voice Too

VO cue:

```text
The internet UX of forms and buttons wasn't made with Nepali people in mind.
Nepal is voice and language rich. So I trained our own TTS and ASR too.
```

Screen:

- Show voice collection and TTS/G2P tools.
- This is the place for "we did the grunt work".

Clips:

```text
voice_collection_sister
source: footage/selects/story_clips/voice_collection_sister.mp4
what happens: voice contributor records speech for the voice stack.

tts_huggingface_kala
source: footage/selects/story_clips/tts_huggingface_kala.mp4
what happens: Hugging Face Space plays Real Nepali TTS v0.2 Kala.

tts_epoch_g2p_comparison
source: footage/selects/story_clips/tts_epoch_g2p_comparison.mp4
what happens: TTS comparison UI and G2P explanation.

g2p_newari_dialect_review
source: footage/selects/story_clips/g2p_newari_dialect_review.mp4
what happens: Newari vs mainstream Nepali G2P comparison with reviewer controls.
```

Overlay:

```text
custom Nepali ASR
custom Nepali TTS
G2P review
voice data collection
```

### 2:25-2:34 - Voice Pipeline In Action

VO cue:

```text
A citizen speaks. Our Nepali ASR transcribes.
Gemma fixes the rough text and plans the intent.
Retrieval finds official and practical sources. Our Nepali TTS speaks back.
```

Screen:

- Use kiosk first, then a simple pipeline overlay.
- Keep the text short.

Clips / assets:

```text
kiosk_voice_asr_pi
source: footage/selects/story_clips/kiosk_voice_asr_pi.mp4
what happens: tablet transcribes Nepali speech while Raspberry Pi is visible.

system_architecture
source: assets/graphics/previllage_system_architecture_1920x1080.png
what happens: pipeline from entry points to ASR/Gemma/RAG/TTS/human loop.
```

Overlay:

```text
speak -> ASR -> Gemma fix -> intent -> retrieve -> TTS
```

### 2:34-2:43 - Local Office Helpdesk

VO cue:

```text
On WhatsApp and kiosks in the office, help starts where people already ask for help.
PreVillage is small enough to run on Raspberry Pi for compute and centralized enough
to share and capture tacit knowledge.
```

Screen:

- Return to Pi and kiosk.
- Show the architecture one more time, but focused on local + central.

Clips / assets:

```text
kiosk_voice_asr_pi
source: footage/selects/story_clips/kiosk_voice_asr_pi.mp4
what happens: local kiosk with Pi visible.

pi_gemma_local_inference_smoke_test
source: footage/selects/story_clips/pi_gemma_local_inference_smoke_test.mp4
what happens: Gemma local inference proof on Raspberry Pi.

system_architecture
source: assets/graphics/previllage_system_architecture_1920x1080.png
what happens: central shared knowledge plus local office deployment.
```

Overlay:

```text
local compute
shared tacit knowledge
office-ready helpdesk
```

### 2:43-2:52 - Define PreVillage

VO cue:

```text
No narration, or use pickup if recorded later.
```

Screen:

- Full architecture diagram or clean product title.
- This is where the conclusion must say what PreVillage is.

Asset:

```text
system_architecture
source: assets/graphics/previllage_system_architecture_1920x1080.png
```

Overlay:

```text
PreVillage is a voice-first government-service navigator.

It asks first.
It checks official and practical sources.
It reaches officers when sources are missing.
It can run inside the office.
```

### 2:52-3:00 - Close

VO cue:

```text
Use final recorded line if present, otherwise title-card close.
```

Screen:

- Mountain/road return or person using WhatsApp/kiosk.
- End on PreVillage title.

Clips / assets:

```text
jiri_mountain_wide
source: footage/selects/story_clips/jiri_mountain_wide.mp4

road_to_jiri_motorcycle
source: footage/selects/story_clips/road_to_jiri_motorcycle.mp4
```

Overlay:

```text
PreVillage
public-service knowledge before privilege

PreVillage exists because it is still a privilege
to navigate government services.
```

## Add More Footage Rule

Only add footage if it answers one of these:

- Does this show why the problem is real?
- Does this show privilege being converted into infrastructure?
- Does this show why the product is not a generic chatbot?
- Does this show official sources, practical human sources, or human review?
- Does this show why voice/WhatsApp/kiosk/local Pi changes access?

If the clip does not answer one of these, it is probably filler.
