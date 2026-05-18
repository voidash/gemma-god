# PreVillage Gemma for Good - Heavy Rough Spec v2

Deadline: 2026-05-19 05:44 NPT.

Target runtime: 180 seconds.

Working title: **PreVillage: public-service knowledge before privilege**.

This is the heavy planning document. Keep narration lean in `narration_text.txt`.

## Core Argument

Nepal's government information problem is not just "bad websites" or missing documents. It is a routing problem, an intent problem, a source-maintenance problem, and a tacit-knowledge problem.

People do not only need an answer. They need the system to first understand the case: which service, which ward or district, which office, which document, which counter, which fee, and what to do when the official source is silent.

PreVillage is the infrastructure layer for that:

- resolver/intake first, not generic Q&A;
- official RAG plus practical human sources;
- self-healing source crawl and health checks;
- human-in-the-loop officer/contact path when knowledge is missing;
- voice, kiosk, WhatsApp, and web entry points;
- small Gemma models for local/on-prem office deployment.

Core line:

> I used privilege to find the path. PreVillage exists so the next person does not need privilege to use their own government.

## Current Source Of Truth Files

Lean VO:

```text
spec/narration_text.txt
```

Capture/evidence updates:

```text
spec/capture_update_20260518.md
spec/visual_assets_plan_20260518.md
spec/sft_rag_evolution_cards.md
```

This heavy spec supersedes:

```text
spec/rough_spec_v1.md
```

## Preserved From Rough Spec v1

These are the important specific asks from `rough_spec_v1.md` that must not be lost.

### Reddit Origin Card

The opening still needs a clean Reddit/text-card recreation based on the origin post:

```text
https://www.reddit.com/r/Nepal/comments/1soq72i/3_weeks_4_office_and_4_times_i_filled_the_same/
```

Design intent:

- recreate the feel of the screenshot/text post, not a generic quote card;
- isolate these beats:
  - `3 weeks`;
  - `4 offices`;
  - `4 forms`;
  - `8k to middlemen`;
  - `paying for information, not service`;
- cut fast from text card into road/office/forms/source-registry footage.

Status: still required as a graphic.

### Privilege Flex Montage

The privilege section should preserve the v1 composition:

```text
sister voice recording -> AWS/GPU footage -> training/tmux screen -> Jiri road/mountain
```

Composition:

- first clip starts full screen;
- second clip enters and both become half-width;
- third clip enters and all become thirds;
- then a text/mask transition on `Privilege`;
- the text/mask clears into road or mountain footage for 2-3 seconds.

This is the visual flex, but it should still serve the story: privilege is the ability to keep pushing until the path becomes visible.

### PreVillage / Privi Lays Motif

Keep this as an optional visual motif, not a distraction:

```text
PreVillage
public-service knowledge before privilege
```

Possible graphic joke/wordplay:

- `pre village`;
- `previ lays`;
- a small chicken/egg metaphor only if it can be done quickly and tastefully;
- "laying infrastructure" before people need privilege.

Composition from v1:

```text
top 25%: "privi lays" / PreVillage motif
bottom 75%: split comparison
  left: To lay     -> WhatsApp / voice / kiosk interface
  right: To not lay -> regular chatbot / portal-first UX
```

Use only if it strengthens the UX argument. Do not let it steal time from the human-loop proof.

### Jiri Phone UX Quote

The exact v1 intent remains:

```text
Android phone त TikTok हेर्ने, Facebook हेर्ने,
अनि फोन गर्नेभन्दा अरू जान्दै जान्दैनन्।
```

This quote is not just color. It establishes that village UX should start from already learned behavior: voice, calls, WhatsApp, and simple kiosk interaction. We do not need people to know how to search/read government portals first.

### Old "Missing Footage" Status

Some v1 missing items are no longer blockers:

- Kiosk mode exists: `footage/selects/govspeak-2/kiosk.mp4`.
- Clean chat/source answer exists: `helpdesk_chat_ask_first_sources.mp4`.
- Admin practical-source review exists: `helpdesk_admin_interview_review.mp4`.
- WhatsApp/officer handoff exists: `helpdesk_whatsapp_officer_outreach.mp4`.
- Government website montage exists: `gov_homepage_montage_20sites.mp4`.
- Architecture and v1-v6 graphics now exist in `assets/graphics/`.

Still useful if time allows:

- more real WhatsApp user clips;
- a polished Reddit opening card;
- animated build-on version of the architecture diagram.

## Current Staged Evidence

### Real-World Footage

Curated footage:

```text
footage/selects/govspeak-2
analysis/gemini/govspeak-2/clip_index.md
analysis/gemini/govspeak-2/duration_report.tsv
```

Useful bins:

- Jiri road/mountain journey: privilege, fieldwork, 180 km travel.
- Public office pitch: real municipality meeting.
- Practical office/interview footage: information officer and office process.
- Sister voice collection: TTS training work.
- Training/tmux/AWS: technical grind.
- Raspberry Pi and kiosk: local/on-prem deployment proof.

### Kiosk Footage

Use:

```text
footage/selects/govspeak-2/kiosk.mp4
analysis/gemini/govspeak-2/clip_md/kiosk.md
```

Best beats:

```text
00:00-00:01   hand taps tablet
00:03-00:05   Nepali speech appears as live transcription
```

Purpose: proves kiosk, Nepali ASR, and visible Raspberry Pi/local deployment. No in-person kiosk reaction footage is required for the current cut.

### Human Loop Interview

Original full source on remote Mac:

```text
/Users/cdjk/video/PreVillageSpeaks 2/PXL_20260505_072911948.mp4
```

Staged full copy:

```text
footage/selects/human_loop_interview/PXL_20260505_072911948_human_loop_interview_full.mp4
analysis/gemini/human_loop_interview/clip_md/PXL_20260505_072911948_human_loop_interview_full.md
```

Strong beats:

```text
0:10-0:20   office identity: Jiri Municipality Office, Jiri Dolakha
0:45-1:00   inquiry counter / citizens routed to departments
1:00-1:35   commonly forgotten documents
1:55-2:20   why citizens are sent back
2:25-2:35   what citizens should know before visiting
```

Story purpose:

```text
field interview -> reviewed practical source -> cited answer
missing answer  -> officer outreach       -> future practical source
```

### Helpdesk Product Captures

Use:

```text
footage/selects/helpdesk_product_captures/helpdesk_chat_ask_first_sources.mp4
footage/selects/helpdesk_product_captures/helpdesk_admin_interview_review.mp4
footage/selects/helpdesk_product_captures/helpdesk_whatsapp_officer_outreach.mp4
analysis/helpdesk_product_captures/capture_manifest.tsv
analysis/gemini/helpdesk_product_captures/clip_md/
```

What each proves:

- `helpdesk_chat_ask_first_sources.mp4`: vague prompt -> compact follow-up -> source-backed Jiri answer using citizen interview source.
- `helpdesk_admin_interview_review.mp4`: interview audio/transcripts in admin review, including pending approve/transcribe flow.
- `helpdesk_whatsapp_officer_outreach.mp4`: missing acceptable source -> refusal/source status -> officer outreach message through WhatsApp-style interface.

### Government Homepage Montage

Use:

```text
footage/selects/gov_homepage_montage/gov_homepage_montage_20sites.mp4
analysis/gov_homepage_montage/capture_manifest.tsv
analysis/gov_homepage_montage/sites.json
analysis/gov_homepage_montage/screenshots/
```

Runtime: about 1:19.8.

Purpose: show the messy source surface and justify registry/crawler/self-healing architecture.

Cut as a fast cascade under:

```text
old websites -> PDFs -> registry -> crawlers -> health checks -> self-healing
```

### Jiri Phone UX Quote

Use:

```text
footage/selects/jiri_man_bahadur_phone_ux_quote_00m28s_24s.mp4
analysis/transcripts/chirp2/jiri_man_bahadur_phone_ux_quote/
```

Corrected subtitle:

```text
Android phone त TikTok हेर्ने, Facebook हेर्ने,
अनि फोन गर्नेभन्दा अरू जान्दै जान्दैनन्।
```

English:

```text
For many people, Android means TikTok, Facebook,
and phone calls. They do not know much beyond that.
```

Purpose: proves why web-first UX is privileged and why voice/WhatsApp/kiosk matter.

### Bihe Darta WhatsApp

Use:

```text
footage/selects/whatsapp_bihe_darta/bihe_darta_ask_only_01s20_05s20.mp4
footage/selects/whatsapp_bihe_darta/bihe_darta_compact_workflow_01s20_08s50.mp4
analysis/transcripts/chirp2/bihe_darta_whatsapp_kala/visual_phrase_beats.tsv
analysis/transcripts/chirp2/bihe_darta_whatsapp_kala/chirp2_word_beats.tsv
```

Visual treatment:

```text
किर्तिपुर नगरपालिका  -> WHERE
बिहे दर्ता           -> SERVICE
कसरी गर्न सकिन्छ?    -> INTENT
```

Purpose: show natural speech becoming routeable structure.

## Recorded Narration And Clip Reference

Use this section while cutting. It maps the actual recorded narration timing to
specific video files and says what each clip contains.

### Spec Files To Keep Open

Primary planning spec:

```text
spec/rough_spec_v2_heavy.md
```

Locked narration text:

```text
spec/narration_text.txt
```

Recorded narration audio and ASR timing:

```text
audio/narration/previllage_narration_20260518_113426_16k_mono.wav
audio/narration/previllage_narration_20260518_113426_original.m4a
analysis/transcripts/chirp2/narration_20260518_113426/chirp2_word_beats.tsv
analysis/transcripts/chirp2/narration_20260518_113426/chirp2_segments.json
analysis/transcripts/chirp2/narration_20260518_113426/chirp2_subtitle_en.srt
```

Chirp2 caveat:

```text
Raw ASR is only for timing. It mishears project terms like PreVillage, Gemma,
ASR, TTS, and RAG, so final captions should come from narration_text.txt.
```

### Recorded VO Cue Map

The recorded narration runs from about `0:01.04` to `2:42.84`. This leaves
roughly 17 seconds inside a 3-minute final cut for opening hold, visual breath,
architecture pauses, and closing title.

| Recorded VO time | Story beat | Audio cue | Primary clips to pull |
|---|---|---|---|
| `0:01-0:23` | Problem: hidden cost, UX, documented/undocumented tacit knowledge | "Nepal has a problem..." through "tacit knowledge" | Reddit origin card, `gov_homepage_montage_20sites.mp4`, `timeline1_cut_11_PXL_20260505_072911948.mp4`, fast office/form flashes |
| `0:23-0:40` | Privilege, v0, Kathmandu solution, travel to Jiri | "I have privilege..." through "remote government office actually works" | `sister_training_voices.mp4`, `ec2.mp4`, `tmux training.mp4`, `supervised_finetuning_v2_checking questions_from_deepseek.mp4`, `timeline1_cut_01_GX012647.mp4` through `timeline1_cut_07_GX012668.mp4` |
| `0:40-1:05` | UX pivot: To Not Lay vs To Lay | "That trip changed the product..." through "use WhatsApp" | `timeline1_cut_08_GX022671.mp4`, `jiri_man_bahadur_phone_ux_quote_00m28s_24s.mp4`, `bihe_darta_question_whatsapp_kala.mp4`, `company_darta.mp4`, portal/PDF/homepage shots |
| `1:05-1:13` | Natural sentence to route | "A citizen doesn't begin with a portal URL..." | `bihe_darta_ask_only_01s20_05s20.mp4`, `bihe_darta_compact_workflow_01s20_08s50.mp4`, `visual_phrase_beats.tsv` for WHERE/SERVICE/INTENT overlay |
| `1:13-1:26` | Gemma: local enough, fixes messy ASR, asks first | "Gemma was pivotal..." through "understand the case" | `pi_llama_request_where_i_want_you_to_show_our_smoke_test_results.mp4`, `kiosk.mp4`, `helpdesk_chat_ask_first_sources.mp4`, `previllage_evolution_v1_v6_1920x1080.png` |
| `1:26-1:38` | Official RAG and self-healing source layer | "RAG alone is weak..." through "self-healing pipeline" | `gov_homepage_montage_20sites.mp4`, `digo_bikash_with_gov_scraping_tmux_main.mp4`, `tmux training.mp4`, `previllage_system_architecture_1920x1080.png` |
| `1:38-1:59` | Tacit knowledge capture and review | "With this..." through "one office corridor" | `PXL_20260505_072911948_human_loop_interview_full.mp4`, `helpdesk_admin_interview_review.mp4`, `helpdesk_chat_ask_first_sources.mp4` |
| `1:59-2:15` | Missing source -> officer outreach | "When PreVillage does not know..." through "folded back" | `helpdesk_whatsapp_officer_outreach.mp4`, `previllage_system_architecture_1920x1080.png` |
| `2:15-2:43` | Voice stack, kiosk/WhatsApp/web, Pi, product definition close | "internet UX..." through "capture tacit knowledge" | `kiosk.mp4`, `tts_hugging_face_card.mp4`, `comparing_different_epoch_tts.mp4`, `tts_g2p_newari_dialect_fix.mp4`, `pi_llama_request_where_i_want_you_to_show_our_smoke_test_results.mp4`, final PreVillage title |

### Clip Inventory By Filename

| Clip | What it has | Best use |
|---|---|---|
| `footage/selects/gov_homepage_montage/gov_homepage_montage_20sites.mp4` | Rapid screen capture of 20 Nepal government websites, including working pages, errors, popups, and fragile portals. | Problem opening and RAG/self-healing section. |
| `footage/selects/govspeak-2/ampixa_live_chat_usage.mp4` | PreVillage chat UI, Nepali query, answer with source links, zoom into response. | Product/RAG proof, source-backed answer. |
| `footage/selects/govspeak-2/bihe_darta_question_whatsapp_kala.mp4` | Woman asks in Nepali about marriage registration in Kirtipur Municipality through WhatsApp-like flow. | Human sentence / WhatsApp access / natural intake. |
| `footage/selects/govspeak-2/company_darta.mp4` | Woman asks "Company kasari darta garne?" and scrolls chat response on phone. | Opening user montage, WhatsApp proof, company-registration pain echo. |
| `footage/selects/govspeak-2/comparing_different_epoch_tts.mp4` | TTS comparison UI, model outputs, G2P explanation, human review. | ASR/TTS grunt-work section; rotate/reframe if used. |
| `footage/selects/govspeak-2/digo_bikash_with_gov_scraping_tmux_main.mp4` | Government websites list, then terminal/tmux scraping or processing. | Source registry, crawler, self-healing RAG visual. |
| `footage/selects/govspeak-2/ec2.mp4` | AWS EC2 dashboard and cost/resource view. | Privilege/GPU/cloud access beat. |
| `footage/selects/govspeak-2/kiosk.mp4` | Tablet voice input, Nepali ASR text appears, Raspberry Pi visible beside kiosk. | Kiosk, ASR, local deployment, Pi proof. |
| `footage/selects/govspeak-2/pi_llama_request_where_i_want_you_to_show_our_smoke_test_results.mp4` | Raspberry Pi close-up and terminal/iPad showing Gemma 2B local inference stats. | Gemma local deployment and low-cost office compute proof. |
| `footage/selects/govspeak-2/sister_training_voices.mp4` | Sister/voice contributor speaking into mic while looking at laptop. | Privilege/help from people, custom voice/TTS data collection. |
| `footage/selects/govspeak-2/supervised_finetuning_v2_checking questions_from_deepseek.mp4` | SFT evaluation dashboard, Nepali question/answer, approve/edit/drop style review. | Training/SFT iteration and human evaluation. |
| `footage/selects/govspeak-2/tmux training.mp4` | Four terminal panes with training logs, ASR/TTS workers, RAG audit, demo status. | Fast technical proof under privilege/Gemma/RAG sections. |
| `footage/selects/govspeak-2/tts_g2p_newari_dialect_fix.mp4` | G2P comparison UI for Newari dialect vs mainstream Nepali, reviewer decision controls. | TTS/G2P human-loop and language depth. |
| `footage/selects/govspeak-2/tts_hugging_face_card.mp4` | Hugging Face Space "Real Nepali TTS v0.2 Kala", waveform playback, Nepali sentence. | Show trained TTS model exists and speaks. |
| `footage/selects/govspeak-2/timeline1_cut_01_GX012647.mp4` | Very short motorcycle POV through green hills. | Fast travel/180 km flash. |
| `footage/selects/govspeak-2/timeline1_cut_02_GX012652.mp4` | Motorcycle POV in sunny mountain terrain. | Fast travel/fieldwork flash. |
| `footage/selects/govspeak-2/timeline1_cut_03_GX012653.mp4` | Motorcycle POV through rural/semi-urban road. | Fast travel transition. |
| `footage/selects/govspeak-2/timeline1_cut_04_GX012656.mp4` | Mountain landscape, valley, snow peaks/power lines. | Privilege text-mask clearing into mountains. |
| `footage/selects/govspeak-2/timeline1_cut_05_GX012660.mp4` | Motorcycle POV on paved rural mountain road. | Travel to Jiri montage. |
| `footage/selects/govspeak-2/timeline1_cut_06_GX012660.mp4` | Longer motorcycle POV on winding mountain road. | Main road/fieldwork transition. |
| `footage/selects/govspeak-2/timeline1_cut_07_GX012668.mp4` | Motorcycle entering a compound, likely office. | Arrival at municipality / fieldwork bridge. |
| `footage/selects/govspeak-2/timeline1_cut_08_GX022671.mp4` | Meeting room discussion; speaker says people use Android mostly for TikTok, Facebook, calls. | UX pivot and Jiri phone quote. |
| `footage/selects/govspeak-2/timeline1_cut_09_MVI_3829.mp4` | Presenter in front of screen discussing Gemma. | Gemma introduction / public pitch proof. |
| `footage/selects/govspeak-2/timeline1_cut_10_MVI_3829.mp4` | Presenter points to references/source explanation on screen. | Source-backed RAG and citation proof. |
| `footage/selects/govspeak-2/timeline1_cut_11_PXL_20260505_072911948.mp4` | Government office desk, laptop with form, papers, Jiri Municipality Office audio mention. | Real office context and fieldwork proof. |
| `footage/selects/jiri_man_bahadur_phone_ux_quote_00m28s_24s.mp4` | Extracted Jiri UX quote with corrected Chirp2 subtitles available. | Strongest UX proof; use around `0:40-1:05` recorded VO. |
| `footage/selects/whatsapp_bihe_darta/bihe_darta_ask_only_01s20_05s20.mp4` | Tight clip of the marriage-registration WhatsApp question. | Natural-sentence-to-route beat. |
| `footage/selects/whatsapp_bihe_darta/bihe_darta_compact_workflow_01s20_08s50.mp4` | Compact workflow from question into system handling. | Show working style and sequence. |
| `footage/selects/whatsapp_bihe_darta/bihe_darta_followup_partial_16s30_20s93.mp4` | Follow-up portion of same WhatsApp flow. | Optional "asks first" proof. |
| `footage/selects/helpdesk_product_captures/helpdesk_chat_ask_first_sources.mp4` | Vague prompt -> compact follow-up -> Jiri answer with `SOURCES USED`. | Ask-first resolver and practical-source citation proof. |
| `footage/selects/helpdesk_product_captures/helpdesk_admin_interview_review.mp4` | Admin page, interview submissions, audio players, approve/transcribe/reject controls. | Human review pipeline and tacit-source ingestion. |
| `footage/selects/helpdesk_product_captures/helpdesk_whatsapp_officer_outreach.mp4` | WhatsApp demo says no authoritative source, then drafts officer outreach message. | Honest refusal + human-in-the-loop self-healing. |
| `footage/selects/human_loop_interview/PXL_20260505_072911948_human_loop_interview_full.mp4` | Full Jiri government-official interview: office name, inquiry counter, missing documents, why people get sent back. | Tacit knowledge capture; use short beats, not the whole clip. |
| `assets/graphics/previllage_evolution_v1_v6_1920x1080.png` | v1-v6 evolution card: grounded, refusal, anti-template, corpus, v5 warning, planner/composer. | SFT/Gemma iteration proof. |
| `assets/graphics/previllage_system_architecture_1920x1080.png` | Full system diagram: entry points -> ASR/Gemma -> resolver -> RAG/practical sources -> human loop. | Architecture explanation and closing definition. |

## Visual Assets

Editable SVG + PNG:

```text
assets/graphics/previllage_evolution_v1_v6_1920x1080.svg
assets/graphics/previllage_evolution_v1_v6_1920x1080.png
assets/graphics/previllage_system_architecture_1920x1080.svg
assets/graphics/previllage_system_architecture_1920x1080.png
```

### Evolution Card

Use around Gemma/SFT section.

Message:

```text
v1 grounded but too trusting
v2 refusal + Roman repair
v3 anti-template but regressions
v4 corpus discipline
v5 low loss, bad product, do not deploy
v6 planner/composer split
```

Voice line it supports:

```text
The win was not a magic adapter. The win was resolver, RAG, evals, and human review around Gemma.
```

### Architecture Diagram

Use during RAG/human-loop section.

System path:

```text
entry points
  -> Nepali ASR / Gemma fixer
  -> resolver / planner / case memory
  -> official RAG + practical sources
  -> Gemma composer
  -> answer / follow-up / refusal
  -> officer outreach when source is missing
  -> verified reply folded back as practical source
```

## Locked VO To Scene Map

Narration is locked in:

```text
spec/narration_text.txt
```

This section maps the locked VO to scenes. Do not rewrite VO here; use this as the edit map.

For actual recorded audio timing, use `Recorded Narration And Clip Reference`
above. The headings below preserve the target 3-minute story structure; the
recorded take is shorter and should be padded with visual holds, captions, and
architecture/title beats.

### 0:00-0:16 - Problem / UX + Knowledge Gap

VO:

```text
Nepal has a problem.
Three weeks. Four offices. Four versions of the same form. Almost eight thousand rupees paid to middlemen.
i paid for information. But the problem is much deeper.

nepal offices have internet forms but you still have to visit office
it's a problem of UX, documented and undocumented tacit knowledge
it's the gap that every country transitioning into modern world faces.
```

Primary visuals:

- Recreated Reddit/text-card opening.
- Fast flashes of:
  - government forms / office desk;
  - internet form or portal followed by office visit / counter;
  - government homepage montage;
  - PDF/source registry/tmux;
  - Jiri office/interview frame.

Assets:

```text
footage/selects/gov_homepage_montage/gov_homepage_montage_20sites.mp4
footage/selects/govspeak-2
```

Graphic still required:

```text
Reddit origin card recreation
```

On-screen words:

```text
3 weeks
4 offices
4 forms
8k to middlemen

I paid for information.

UX problem
documented tacit knowledge
undocumented tacit knowledge
```

Edit intent:

- Start with civic pain, not product UI.
- Show that the issue is deeper than one bad form: forms exist, but the actual path still requires office visits and hidden context.
- Show both kinds of knowledge problem: documented-but-buried and undocumented/tacit.

### 0:16-0:35 - Privilege / v0 / Fieldwork

VO:

```text
I had previlege :
GPU access, technical knowledge, people who helped me,
and obsession to keep debugging
with which v0 was born.

it was a web interface where people could type questions.
But that is a kathmandu solution

and Kathmandu is also a privilege.
So I travelled 180 kilometers to  Jiri to see how an remote gov office actually works
```

Primary visuals:

- Sister voice recording.
- AWS/GPU or epoch/training replay.
- Tmux training screen.
- v0 web interface / chat UI if available.
- Road to Jiri and mountain footage.
- Public office pitch frame.

Composition:

```text
clip 1 full screen -> 2-way split -> 3-way split -> "Privilege" mask -> Jiri road/mountain
```

Assets:

```text
footage/selects/govspeak-2
research/training-replay/
assets/graphics/previllage_evolution_v1_v6_1920x1080.png
```

On-screen words:

```text
GPU access
technical knowledge
voice help
v0: web question box
Kathmandu solution
180 km to Jiri
```

Edit intent:

- This section is allowed to feel like a flex, but it should land as confession: privilege made the work possible.
- v0 should be visible as primitive/early and explicitly web-first, so the later voice/WhatsApp pivot feels earned.

### 0:35-0:50 - UX Problem / To Lay vs Not Lay

VO:

```text
That trip changed the product.

The problem was not only lack of information but also a UX problem

to not Lay:
the internet of nepal wasn't built for pdfs, html forms and buttons which has brought in
interface problem, routing problem, read 20 page pdf for information problem.

To Lay:
but nepal that exports labor imports internet to connect with people abroad.
people already know how to speak, call, and use WhatsApp.
I thought maybe we should start there.
```

Primary visuals:

- Jiri phone UX quote with subtitles.
- Split screen:
  - "To not lay": PDFs, HTML forms, portal UI, regular chatbot/portal-first UX.
  - "To lay": WhatsApp, voice, kiosk, call-like interaction.
- Optional top strip: PreVillage / privi lays / public-service knowledge before privilege.

Assets:

```text
footage/selects/jiri_man_bahadur_phone_ux_quote_00m28s_24s.mp4
analysis/transcripts/chirp2/jiri_man_bahadur_phone_ux_quote/subtitle_corrected_ne.srt
analysis/transcripts/chirp2/jiri_man_bahadur_phone_ux_quote/subtitle_translation_en.srt
footage/selects/helpdesk_product_captures/helpdesk_whatsapp_officer_outreach.mp4
footage/selects/govspeak-2/kiosk.mp4
```

On-screen words:

```text
TO NOT LAY
PDFs / forms / buttons / portals / 20-page PDFs

TO LAY
voice / call / WhatsApp / kiosk
```

Edit intent:

- This is the conceptual pivot.
- The Jiri quote proves the UX claim; do not bury it under too many graphics.

### 0:50-1:12 - Natural Sentence To Route

VO:

```text
A citizen does not begin with a portal URL.

they ask naturally: dharmadevi nagarpalika, marriage registration, how do I do it?

That is the job: turn a human sentence into a route.
```

Primary visuals:

- WhatsApp/user question clip.
- Word/phrase extraction overlay.
- Small route animation from sentence -> structured slots.

Assets:

```text
footage/selects/whatsapp_bihe_darta/bihe_darta_ask_only_01s20_05s20.mp4
footage/selects/whatsapp_bihe_darta/bihe_darta_compact_workflow_01s20_08s50.mp4
analysis/transcripts/chirp2/bihe_darta_whatsapp_kala/visual_phrase_beats.tsv
analysis/transcripts/chirp2/bihe_darta_whatsapp_kala/chirp2_word_beats.tsv
```

On-screen words:

```text
Dharmadevi nagarpalika -> WHERE
marriage registration  -> SERVICE
how do I do it?        -> INTENT
```

Note:

- Existing captured clip says Kirtipur/Bihe Darta. If VO stays Dharmadevi, use overlay text matching VO or select a visual that does not conflict. Do not show contradictory location text too clearly.

Edit intent:

- This is the cleanest place to show "navigator, not chatbot."
- Every word/phrase should carry weight.
- Keep the clip chopped tight: natural sentence -> highlighted entities -> route.

### 1:12-1:35 - Gemma / Ask First

VO:

```text
Gemma was pivotal because it is small enough for local deployment,
but still can reason through messy ASR text,
ask the next question, and compose from sources.

The first job is not to answer. The first job is to understand the case.
```

Primary visuals:

- Raspberry Pi / llama.cpp / local model footage.
- Helpdesk ask-first clip.
- Kiosk ASR clip.
- Evolution card as fast proof that Gemma was iterated around system behavior.

Assets:

```text
footage/selects/govspeak-2/pi_llama_request_where_i_want_you_to_show_our_smoke_test_results.mp4
footage/selects/govspeak-2/kiosk.mp4
footage/selects/helpdesk_product_captures/helpdesk_chat_ask_first_sources.mp4
assets/graphics/previllage_evolution_v1_v6_1920x1080.png
```

On-screen words:

```text
small enough for offices
fix messy ASR
ask the next question
compose from sources

understand first
answer second
```

Edit intent:

- Avoid presenting Gemma as a magic chatbot.
- Show Gemma inside a resolver/source system.

### 1:35-1:58 - Official RAG / Self-Healing Source Layer

VO:

```text
RAG alone is weak when truth is scattered across
old websites, PDFs, office habits, and the memory of one contact officer.

So i built a registry of 800+ government sources, crawlers, health checks, and a self-healing pipeline
```

Primary visuals:

- 20-site government homepage montage.
- DigoBikas / MoHA office directory.
- Tmux crawler/source registry/health audit.
- Architecture diagram push-in on "Official RAG."

Assets:

```text
footage/selects/gov_homepage_montage/gov_homepage_montage_20sites.mp4
footage/selects/govspeak-2/digo_bikash_with_gov_scraping_tmux_main.mp4
assets/graphics/previllage_system_architecture_1920x1080.png
```

On-screen words:

```text
800+ government sources
crawlers
health checks
self-healing

law is written
the path is lived
```

Edit intent:

- This is where volume matters. Cut many sites quickly.
- The architecture diagram should clarify that official RAG is only one half of the system.
- Do not over-explain official RAG in VO; let the visuals carry registry, crawler, and health-check detail.

### 1:58-2:24 - Tacit Knowledge Capture / Admin Review

VO:

```text
with this i also have created a pipeline to capture tacit knowledge.
government officials can answer simple questions that never go documented
Which counter first? Which room? What time is easiest? Which document do people forget? Why are they sent back?

Those answers go through review, become practical sources, and can be cited later beside official government sources.

Tacit knowledge is only unfair when it stays trapped in one office corridor.
```

Primary visuals:

- Full human-loop interview beats.
- Admin review screen.
- Chat answer citing citizen/interview source.

Assets:

```text
footage/selects/human_loop_interview/PXL_20260505_072911948_human_loop_interview_full.mp4
analysis/gemini/human_loop_interview/clip_md/PXL_20260505_072911948_human_loop_interview_full.md
footage/selects/helpdesk_product_captures/helpdesk_admin_interview_review.mp4
footage/selects/helpdesk_product_captures/helpdesk_chat_ask_first_sources.mp4
```

Best interview beats:

```text
0:45-1:00   inquiry counter / citizens routed to departments
1:00-1:35   commonly forgotten documents
1:55-2:20   why citizens are sent back
2:25-2:35   what citizens should know before visiting
```

On-screen words:

```text
counter first?
which room?
what time?
forgotten documents?
why sent back?

interview -> review -> practical source -> cited answer
```

Edit intent:

- Make interviews feel like data infrastructure, not documentary flavor.
- Cut from interview answer to admin review to cited chat answer.

### 2:24-2:42 - Source Gap / Officer Outreach

VO:

```text
When PreVillage does not know, it should not hallucinate.

It says what is missing, shows what sources it checked, and turns the citizen's question into an officer outreach message through the WhatsApp bridge.

The answer is not invented. It is asked, reviewed, and folded back into the system for the next person. (Pre will age)
```

Primary visuals:

- WhatsApp officer outreach capture.
- Architecture diagram push-in on Human Loop.
- Optional subtle loop animation back into Practical Sources.

Assets:

```text
footage/selects/helpdesk_product_captures/helpdesk_whatsapp_officer_outreach.mp4
assets/graphics/previllage_system_architecture_1920x1080.png
```

On-screen words:

```text
no source?
do not hallucinate
ask officer
review reply
fold back
```

Edit intent:

- This is the "human in the loop" proof.
- Show the refusal and outreach draft clearly enough that the viewer understands the system is honest.

### 2:42-End - Voice Stack / Access / Product Definition

VO:

```text
As we established the internet UX of forms and buttons wasn't made with Nepali people in mind.
But nepal is voice and language rich.
so i trained our own TTS and ASR too.

A citizen speaks. Our Nepali ASR transcribes.
Gemma fixes the rough text and plans the intent.
Retrieval finds official and practical sources. Our Nepali TTS speaks back.

On WhatsApp and kiosks in the office, help starts where people already ask for help.

PreVillage is small enough to run on raspberry pi for compute and centralized enough to share and capture tacit knowledge.

PreVillage exists because it's still a privilege to navigate our government services.
```

Primary visuals:

- Kiosk clip with tablet ASR + visible Pi.
- ASR/TTS Ampixa/Hugging Face pages.
- Sister voice footage if not already used.
- WhatsApp interface.
- Pi/kiosk or office desk.
- Architecture diagram final line.
- PreVillage title.
- Road/mountain return if it feels emotionally stronger.

Assets:

```text
footage/selects/govspeak-2/kiosk.mp4
footage/selects/govspeak-2/tts_hugging_face_card.mp4
footage/selects/govspeak-2/ampixa_live_chat_usage.mp4
footage/selects/govspeak-2/pi_llama_request_where_i_want_you_to_show_our_smoke_test_results.mp4
assets/graphics/previllage_system_architecture_1920x1080.png
```

On-screen words:

```text
PreVillage
voice-first government-service navigator

ASR -> Gemma fix -> intent -> retrieve -> TTS
WhatsApp + kiosk + web
local compute + shared tacit knowledge
official sources + practical sources
human loop when source is missing

public-service knowledge before privilege
```

Edit intent:

- This is the broad access section and product definition close.
- Keep it concrete: show actual ASR/TTS, kiosk, WhatsApp, and Pi/local compute, not just diagram.
- Conclusion must define what PreVillage is.
- End with the product identity, not only the privilege slogan.

## 3-Minute Timeline

### 0:00-0:16 - Hidden Route

Visuals:

- Reddit/text card recreation:
  - 3 weeks;
  - 4 offices;
  - 4 forms;
  - 8k to middlemen;
  - paying for information, not service.
- Recreate the old Reddit screenshot/text-post energy. The image reference from v1 matters here; do not replace it with a generic title card.
- Fast flashes of road, office, forms, source registry.

On-screen:

```text
I paid for information.
The problem is deeper.

UX
documented tacit knowledge
undocumented tacit knowledge
```

### 0:16-0:35 - Privilege

Visuals:

- Sister voice collection.
- AWS/GPU or epoch replay.
- Training/tmux screen.
- Road to Jiri/mountain shot.

Composition:

- Start one clip full screen.
- Split to two.
- Split to three.
- Then wipe/mask into road/mountain.
- Preserve the v1 "Privilege" text-mask idea: the word appears, then clears away into the Jiri mountain/road shot for 2-3 seconds.

On-screen:

```text
Privilege = the ability to keep pushing
```

### 0:35-0:50 - Jiri Ground Truth / UX

Visuals:

- Jiri phone UX quote with corrected Nepali and English subtitle.
- Optional phone/WhatsApp visual.
- Optional `PreVillage / privi lays` comparison:
  - top strip: PreVillage / public-service knowledge before privilege;
  - lower split: "To lay" with WhatsApp/voice/kiosk vs "To not lay" with regular chatbot/portal UX.

Purpose:

- Establish that the interface needs to match learned behavior: voice, calls, WhatsApp.

### 0:50-1:12 - Natural Speech To Route

Visuals:

- Bihe darta WhatsApp clip.
- Phrase-beat overlay:
  - WHERE;
  - SERVICE;
  - INTENT.

Purpose:

- Show why the product is a navigator, not plain Q&A.

### 1:12-1:35 - Why Gemma / Iteration

Visuals:

- Pi/local model footage.
- SFT/RAG evolution card.
- Training screen.

Key idea:

- Gemma matters because it can sit inside a constrained system: small enough for local deployment, capable enough for text repair, planning, and composition.
- Do not imply v5 adapter is deployed. The honest story is the system around Gemma.

### 1:35-1:58 - Official RAG / Self Healing

Visuals:

- Government homepage montage.
- DigoBikas / MoHA directory / source registry.
- Tmux RAG/crawler/health-check footage.
- Architecture diagram push-in.

Key idea:

- RAG alone is weak if sources rot. PreVillage maintains a source registry, crawls periodically, runs health checks, and routes retrieval by question type.

### 1:58-2:24 - Interviews Become Practical Sources

Visuals:

- Human-loop interview full clip beats.
- Admin interview review capture.
- Chat answer citing citizen interview source.

Key idea:

- Interviews are not just research. They become reviewed, named practical sources.

### 2:24-2:42 - Human Loop When Source Is Missing

Visuals:

- WhatsApp officer outreach capture.
- Architecture diagram human-loop segment.

Key idea:

- When the system lacks a reliable answer, it refuses honestly and drafts a contact/officer message rather than hallucinating.

Important wording:

```text
The answer is not invented. It is asked, reviewed, and folded back into the system.
```

### 2:42-2:55 - Voice / WhatsApp / Kiosk

Visuals:

- Kiosk clip.
- ASR/TTS pages on Ampixa.
- WhatsApp montage.
- Pi/local shot.

Key idea:

- Nepal is voice-rich; web UX is the privileged layer. Use the channels people already use.

### 2:55-3:00 - Close

Visuals:

- Pi/office/kiosk or road return.
- PreVillage title.
- Optional final architecture summary line.

The close must define the product with visuals and on-screen text, because the locked VO ends compactly:

```text
PreVillage is small enough to run on raspberry pi for compute and centralized enough to share and capture tacit knowledge.

PreVillage exists because it's still a privilege to navigate our government services.
```

On-screen:

```text
PreVillage
voice-first government-service navigator
WhatsApp + kiosk + web + local office helpdesk
official sources + practical sources + human loop

public-service knowledge before privilege
```

## Remaining Work

Required:

- Final VO timing pass against the actual rough cut.
- Reddit/text-card recreation.
- Decide whether architecture diagram remains static or gets simple build-on animation.

Optional:

- Additional person-using-kiosk reaction footage.
- More WhatsApp user montage, if it can be captured without privacy risk.
