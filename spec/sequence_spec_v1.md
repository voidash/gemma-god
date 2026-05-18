# PreVillage Gemma for Good - Sequence Spec v1

Deadline: 2026-05-19 05:44 NPT.

Target runtime: 3:00.

## Source Of Truth

The build source of truth is the machine-readable file:

```text
spec/sequence_spec_v1.json
```

This Markdown file is the readable companion for editing decisions. If this and the JSON disagree, fix the JSON first, then refresh this companion.

All media paths resolve from:

```text
/Volumes/TRANSCEND/video-creation/previllage-gemma-for-good-2026
```

Semantic clip aliases live at:

```text
footage/selects/story_clips/ALIASES.tsv
```

## Locked Audio

Narration drives the timeline. Do not stretch or reposition narration; move visuals around it.

```text
audio/narration/previllage_narration_20260518_113426_16k_mono.wav
analysis/transcripts/chirp2/narration_20260518_113426/chirp2_word_beats.tsv
analysis/transcripts/chirp2/narration_20260518_113426/chirp2_subtitle_en.srt
```

Recorded VO starts around `1.04s` and ends around `162.84s`. The final tail is definition/title space.

Caption corrections:

- `VZERA` -> `v0`
- `JMA` -> `Gemma`
- `P portal` -> `pivotal`
- `SR` -> `ASR`
- `ESR` -> `ASR`
- `TS` -> `TTS`
- `TDS` -> `TTS`
- `root` -> `route`
- `dataset knowledge` -> `tacit knowledge`

## Story Spine

PreVillage is a voice-first government-service navigator. It asks first, checks official and practical sources, reaches officers when sources are missing, and can run inside the office.

Core close:

```text
PreVillage
public-service knowledge before privilege
```

## Validation Snapshot

- Beats: `20`
- Timing source: `narration`
- Codex review applied: `True`
- Latest validation report: `renders/validation/sequence_spec_v1_report.json`

## Timeline

### B01 - Cold Open

Time: `0:00-0:02` (`2.2s`).

Purpose: Establish lived public-service pain before any tech appears.

VO cue:

```text
Nepal has a problem.
```

On-screen text:

```text
Nepal has a problem.
```

Assets:

- `assets/graphics/reddit_origin_card_1920x1080.png`

Visual layers:

- `reddit_card` (hero / image): Recreated r/Nepal post card fills 80 percent of frame, slightly off-center over dark textured background.
  asset: `assets/graphics/reddit_origin_card_1920x1080.png`
  position: center, 1428x880 card, slight 0.4deg rotation
  motion: slow 102 percent to 100 percent settle, expo out
- `hook_text` (support / text): Large title text slams on top: Nepal has a problem.
  text: `Nepal has a problem.`
  position: lower-left safe area
  motion: 2-frame anticipation then 10-frame slam, back easing
- `origin_texture` (atmosphere / shape): Subtle red and blue circles from the card background, with 4 percent grain.

Transition in: fade up from black

Transition out: hard cut on word Three

### B02 - Hidden Knowledge Has A Price

Time: `0:02-0:07` (`4.8s`).

Purpose: Turn origin story into concrete numbers and route pain.

VO cue:

```text
Three weeks. Four offices. Four versions of the same form. Almost eight thousand rupees paid to middlemen.
```

On-screen text:

```text
3 weeks / 4 offices / 4 forms / Rs 8k
```

Assets:

- `assets/graphics/four_office_route_map_1920x1080.png`
- `assets/graphics/four_office_route_map_1920x1080.svg`
- `assets/sources/forms/mock_government_form_document.pdf`
- `assets/sources/four_office_route/capture_manifest.tsv`

Visual layers:

- `route_map` (hero / image): Four-office route graphic fills frame; office cards appear sequentially with route dots.
  asset: `assets/graphics/four_office_route_map_1920x1080.png`
  assets: `assets/graphics/four_office_route_map_1920x1080.png`, `assets/graphics/four_office_route_map_1920x1080.svg`
  position: full frame, map line anchored center-right, number chips left 22 percent
  motion: office cards reveal in 4 timed pops mapped to weeks/offices/forms/Rs 8k
- `form_stamp` (support / animated_document): One paper copy moves between offices and receives red 'again' stamps at each redirect.
  asset: `assets/sources/forms/mock_government_form_document.pdf`
  motion: paper slides along route, stamp hit at each office
- `number_chips` (support / text_chips): 3 weeks, 4 offices, 4 forms, Rs 8k extra remain readable on left.
- `source_note` (atmosphere / source_label): Tiny visible source note cites OCR/CAMIS and IRD Tripureshwor, Kalimati, Kalanki captures from capture_manifest.tsv.
  assets: `assets/sources/four_office_route/capture_manifest.tsv`
  position: bottom-right, 20px mono text on paper strip

Transition in: hard cut

Transition out: smash cut to headlines

### B03 - Not A One-Off

Time: `0:07-0:15` (`8.0s`).

Purpose: Show middlemen/routing problem is broad, not one Reddit post.

VO cue:

```text
People are leveraging lack of proper pipeline and well documentation. I wanted to solve this.
```

On-screen text:

```text
People pay for information, not the service.
```

Assets:

- `assets/sources/middlemen_news/SELECTS.tsv`
- `assets/sources/middlemen_news/screenshots/01b_myrepublica_amp_good_governance_on_hold.png`
- `assets/sources/middlemen_news/screenshots/02_rising_nepal_ending_sway_middlemen.png`
- `assets/sources/middlemen_news/screenshots/03_ekantipur_middlemen_prohibited_land_revenue.png`
- `assets/sources/middlemen_news/screenshots/04_ratopati_land_revenue_middlemen_crackdown.png`
- `assets/sources/middlemen_news/screenshots/05_nepalnews_brokers_hijack_services.png`
- `assets/sources/middlemen_news/screenshots/06_arthasarokar_sarlahi_middlemen.png`
- `footage/selects/story_clips/fieldwork_jiri_office_form_laptop.mp4`  \n  what happens: Jiri office desk, laptop form, papers, officials around the process  \n  resolves to: `footage/selects/govspeak-2/timeline1_cut_11_PXL_20260505_072911948.mp4`

Visual layers:

- `headline_montage` (hero / image_sequence): Receipt wall, not decorative montage: first two headlines become large hero cards for readability, remaining four stack as smaller but legible proof around them.
  assets: `assets/sources/middlemen_news/SELECTS.tsv`, `assets/sources/middlemen_news/screenshots/01b_myrepublica_amp_good_governance_on_hold.png`, `assets/sources/middlemen_news/screenshots/02_rising_nepal_ending_sway_middlemen.png`, `assets/sources/middlemen_news/screenshots/03_ekantipur_middlemen_prohibited_land_revenue.png`, `assets/sources/middlemen_news/screenshots/04_ratopati_land_revenue_middlemen_crackdown.png`, `assets/sources/middlemen_news/screenshots/05_nepalnews_brokers_hijack_services.png`, `assets/sources/middlemen_news/screenshots/06_arthasarokar_sarlahi_middlemen.png`
  position: hero card at right 68 percent width for 0-3.4s, then six-card evidence wall with publisher labels
  motion: hard cuts on narration clauses; red underline locks to visible words middlemen/brokers; no screenshot held under 30 frames
- `office_form_cutaway` (support / video): Jiri office laptop/forms footage interrupts headline montage twice.
  asset: `footage/selects/story_clips/fieldwork_jiri_office_form_laptop.mp4`
  motion: 2-frame flash cuts with handheld crop
- `cost_line` (support / text): A concise line reframes the issue as a repeatable route problem, not only personal frustration.
  text: `Not one office. Not one website. A missing route.`
  position: bottom third on black solid strip
- `grain` (atmosphere / texture): 5 percent paper grain and faint page shadows.

Transition in: smash cut

Transition out: push into process diagram

### B04 - E-Governance Gap

Time: `0:15-0:23` (`8.0s`).

Purpose: Diagnose UX plus documented and undocumented knowledge.

VO cue:

```text
It's the gap every country transitioning into modern e-governance faces. Nepal has internet forms, but you still have to visit offices.
```

On-screen text:

```text
documented knowledge
tacit knowledge
```

Assets:

- `footage/selects/story_clips/forms_process_reference_20260518_122823.mp4`
- `assets/graphics/form_process_overlay_1920x1080.png`
- `assets/graphics/form_process_overlay_1920x1080.svg`
- `assets/references/process_animation_reference_image_1.png`

Visual layers:

- `process_bg` (hero / video): Form/process reference video plays under warm translucent grade.
  asset: `footage/selects/story_clips/forms_process_reference_20260518_122823.mp4`
  motion: slow 1.02x push, muted contrast
- `process_overlay` (support / image_overlay): Transparent overlay shows online form, print/check, office visit, redirect, repeat loop.
  asset: `assets/graphics/form_process_overlay_1920x1080.png`
  assets: `assets/graphics/form_process_overlay_1920x1080.png`, `assets/graphics/form_process_overlay_1920x1080.svg`
  motion: nodes assemble left to right; red loop draws last
- `knowledge_split` (support / text): Documented knowledge and tacit knowledge labels stay visible at bottom.
- `reference_style` (atmosphere / image_texture): Process reference image is visible as a faint 12 percent opacity paper sketch behind the animated loop, proving the design reference is used.
  asset: `assets/references/process_animation_reference_image_1.png`
  position: full frame background texture, cropped to cover, underneath process overlay
  motion: static paper texture with 0.5px/s parallax; never foregrounded

Transition in: push in

Transition out: hard cut to privilege flex

### B05 - Privilege Flex

Time: `0:23-0:30` (`7.0s`).

Purpose: Own the privilege that made the attempt possible.

VO cue:

```text
I had privilege: GPU access, technical knowledge, people who helped me, and obsession to keep debugging.
```

On-screen text:

```text
Privilege = ability to keep pushing
```

Assets:

- `footage/selects/story_clips/voice_collection_sister.mp4`  \n  what happens: voice contributor speaks into mic for voice data collection  \n  resolves to: `footage/selects/govspeak-2/sister_training_voices.mp4`
- `footage/selects/story_clips/aws_ec2_gpu_access.mp4`  \n  what happens: AWS EC2 dashboard and cost/resource view  \n  resolves to: `footage/selects/govspeak-2/ec2.mp4`
- `footage/selects/story_clips/training_tmux_status.mp4`  \n  what happens: terminal panes with training logs, ASR/TTS workers, RAG audit, demo status  \n  resolves to: `footage/selects/govspeak-2/tmux training.mp4`

Visual layers:

- `sister_voice` (hero / video): Voice contributor footage starts full frame, human help first.
  asset: `footage/selects/story_clips/voice_collection_sister.mp4`
  motion: full frame for first third, then resizes into left column
- `aws_gpu` (support / video): AWS/GPU access joins as second column.
  asset: `footage/selects/story_clips/aws_ec2_gpu_access.mp4`
  motion: slides in from right, no generic cloud icons
- `training_tmux` (support / video): Training terminal becomes third column with epoch/log motion.
  asset: `footage/selects/story_clips/training_tmux_status.mp4`
  motion: bottom crop pans vertically to show logs
- `privilege_labels` (support / text_chips): GPU access, technical knowledge, people who helped, obsession to debug.

Transition in: hard cut

Transition out: cut to web UI

### B06 - v0 Was Web-First

Time: `0:30-0:36` (`6.0s`).

Purpose: Show early useful web product was still a Kathmandu solution.

VO cue:

```text
With which v0 was born. It was a web interface where people could type questions. But that was a Kathmandu solution.
```

On-screen text:

```text
v0: type a question
useful, but still web-first
```

Assets:

- `footage/selects/story_clips/web_question_box_or_chat.mp4`  \n  what happens: PreVillage chat UI receives Nepali query and shows sourced response  \n  resolves to: `footage/selects/govspeak-2/ampixa_live_chat_usage.mp4`
- `footage/selects/story_clips/sft_eval_dashboard.mp4`  \n  what happens: SFT evaluation dashboard with Nepali question/answer and human review controls  \n  resolves to: `footage/selects/govspeak-2/supervised_finetuning_v2_checking questions_from_deepseek.mp4`

Visual layers:

- `web_chat` (hero / video): Helpdesk web chat shows a Nepali query and source-backed answer.
  asset: `footage/selects/story_clips/web_question_box_or_chat.mp4`
  motion: screen crop follows query then source area
- `sft_eval` (support / video): SFT/eval dashboard flashes as iteration proof.
  asset: `footage/selects/story_clips/sft_eval_dashboard.mp4`
  motion: fast inset, 2-second hold max
- `v0_label` (support / text): v0: type a question. Useful, but still web-first.
  text: `v0: type a question / useful, but still web-first`
  position: left third

Transition in: hard cut

Transition out: privilege mask reveal

### B07 - Leaving Kathmandu

Time: `0:36-0:42` (`6.0s`).

Purpose: Move from desk privilege to remote office reality.

VO cue:

```text
Kathmandu itself is a privilege. So I travelled 180 kilometers to Jiri...
```

On-screen text:

```text
180 km to Jiri
Kathmandu is also privilege
```

Assets:

- `footage/selects/story_clips/jiri_mountain_wide.mp4`  \n  what happens: wide mountain landscape, valley, distant peaks  \n  resolves to: `footage/selects/govspeak-2/timeline1_cut_04_GX012656.mp4`
- `footage/selects/story_clips/road_to_jiri_motorcycle.mp4`  \n  what happens: motorcycle POV on winding mountain road  \n  resolves to: `footage/selects/govspeak-2/timeline1_cut_06_GX012660.mp4`
- `footage/selects/story_clips/arrival_office_compound.mp4`  \n  what happens: motorcycle enters office-like compound  \n  resolves to: `footage/selects/govspeak-2/timeline1_cut_07_GX012668.mp4`

Visual layers:

- `privilege_mask` (hero / text_mask): Huge word PRIVILEGE acts as mask revealing mountain footage on the spoken word privilege.
  motion: mask expands from center, 18-frame reveal
- `mountain` (hero / video): Jiri mountain wide becomes full-bleed after mask reveal.
  asset: `footage/selects/story_clips/jiri_mountain_wide.mp4`
  motion: slow push-in
- `road` (support / video): Motorcycle road footage cuts in on 180 km.
  asset: `footage/selects/story_clips/road_to_jiri_motorcycle.mp4`
  motion: motivated motion cut
- `arrival` (support / video): Arrival compound shot for destination punctuation.
  asset: `footage/selects/story_clips/arrival_office_compound.mp4`

Transition in: text mask

Transition out: cut to meeting room

### B08 - Fieldwork Changed Product

Time: `0:42-0:50` (`8.0s`).

Purpose: Show product direction changed because of real officials and phone UX reality.

VO cue:

```text
That trip changed the product. The problem was not only lack of information, but also a UX problem.
```

On-screen text:

```text
fieldwork changed the product
```

Assets:

- `footage/selects/story_clips/jiri_meeting_phone_ux_context.mp4`  \n  what happens: meeting room discussion about Android phones, TikTok, Facebook, calls  \n  resolves to: `footage/selects/govspeak-2/timeline1_cut_08_GX022671.mp4`
- `footage/selects/story_clips/jiri_android_tiktok_facebook_call_quote.mp4`  \n  what happens: extracted Jiri UX quote with subtitles available  \n  resolves to: `footage/selects/jiri_man_bahadur_phone_ux_quote_00m28s_24s.mp4`
- `footage/selects/story_clips/public_pitch_gemma_screen.mp4`  \n  what happens: presenter near screen discussing Gemma  \n  resolves to: `footage/selects/govspeak-2/timeline1_cut_09_MVI_3829.mp4`

Visual layers:

- `meeting_room` (hero / video): Jiri meeting room establishes real public office context.
  asset: `footage/selects/story_clips/jiri_meeting_phone_ux_context.mp4`
  motion: conversational push-in
- `android_quote` (support / video_quote): Official quote about Android phones, TikTok, Facebook, calls; subtitle carries meaning.
  asset: `footage/selects/story_clips/jiri_android_tiktok_facebook_call_quote.mp4`
  motion: duck VO if original audio used
- `pitch_screen` (support / video): Presenter near Gemma/public pitch screen flashes as field validation.
  asset: `footage/selects/story_clips/public_pitch_gemma_screen.mp4`
- `nepali_subtitle` (support / subtitle): Android phone त TikTok हेर्ने, Facebook हेर्ने, अनि फोन गर्नेभन्दा अरू जान्दै जान्दैनन्।

Transition in: hard cut

Transition out: split to UX comparison

### B09 - Already Learned UX

Time: `0:50-1:05` (`15.0s`).

Purpose: Show that the solution must use interfaces Nepalis already understand: voice, call, WhatsApp, kiosk.

VO cue:

```text
The internet of Nepal wasn't built for PDFs, HTML forms, and buttons. People already know how to speak, call, and use WhatsApp. I thought maybe we should start there.
```

On-screen text:

```text
already learned UX
voice / call / WhatsApp / kiosk
```

Assets:

- `footage/selects/story_clips/gov_homepage_montage_20sites.mp4`  \n  what happens: 20 government sites; working pages, errors, popups, fragile portals  \n  resolves to: `footage/selects/gov_homepage_montage/gov_homepage_montage_20sites.mp4`
- `footage/selects/story_clips/whatsapp_company_darta_user.mp4`  \n  what happens: woman asks how to register a company and scrolls WhatsApp response  \n  resolves to: `footage/selects/govspeak-2/company_darta.mp4`
- `footage/selects/story_clips/whatsapp_bihe_darta_user.mp4`  \n  what happens: woman asks about marriage registration in Nepali through WhatsApp-like flow  \n  resolves to: `footage/selects/govspeak-2/bihe_darta_question_whatsapp_kala.mp4`
- `footage/selects/story_clips/kiosk_voice_asr_pi.mp4`  \n  what happens: tablet transcribes Nepali speech while Raspberry Pi is visible  \n  resolves to: `footage/selects/govspeak-2/kiosk.mp4`
- `footage/selects/story_clips/privi_lays_hen_06s_08s.mp4`

Visual layers:

- `bad_fit` (hero / video_grid): Left side shows portals, PDFs, forms, popups from government homepage montage.
  asset: `footage/selects/story_clips/gov_homepage_montage_20sites.mp4`
  position: left 48 percent
- `already_known` (hero / video_grid): Right side shows WhatsApp and kiosk voice as familiar UX.
  assets: `footage/selects/story_clips/whatsapp_company_darta_user.mp4`, `footage/selects/story_clips/whatsapp_bihe_darta_user.mp4`, `footage/selects/story_clips/kiosk_voice_asr_pi.mp4`
  position: right 48 percent
- `hen_flash` (support / video): Hen clip appears as a sub-second visual pun on privi-lays, then disappears before the UX comparison starts.
  asset: `footage/selects/story_clips/privi_lays_hen_06s_08s.mp4`
  motion: 10-14 frame flash only; no extended chicken gag
- `to_lay_labels` (support / text): Labels anchor the real point: website UX is not enough; already-learned voice and WhatsApp behavior is the deployment surface.
  text: `WEB-FIRST: portals, PDFs, hidden rooms / VOICE-FIRST: ask like a person, route like a system`

Transition in: split-screen build

Transition out: cut to WhatsApp sentence

### B10 - Human Sentence Becomes Route

Time: `1:05-1:13` (`8.0s`).

Purpose: Explain resolver job as turning natural language into route.

VO cue:

```text
A citizen does not begin with a portal URL. They ask naturally: Dharmadevi Nagarpalika, marriage registration, how do I do it? That is the job: turn a human sentence into a route.
```

On-screen text:

```text
human sentence -> route
```

Assets:

- `footage/selects/story_clips/bihe_darta_question_tight.mp4`  \n  what happens: tight clip of the marriage-registration WhatsApp question  \n  resolves to: `footage/selects/whatsapp_bihe_darta/bihe_darta_ask_only_01s20_05s20.mp4`
- `footage/selects/story_clips/bihe_darta_compact_workflow.mp4`  \n  what happens: compact workflow from question into system handling  \n  resolves to: `footage/selects/whatsapp_bihe_darta/bihe_darta_compact_workflow_01s20_08s50.mp4`
- `footage/selects/story_clips/whatsapp_bihe_darta_user.mp4`  \n  what happens: woman asks about marriage registration in Nepali through WhatsApp-like flow  \n  resolves to: `footage/selects/govspeak-2/bihe_darta_question_whatsapp_kala.mp4`

Visual layers:

- `phone_question` (hero / video): Tight question clip is the hero; full WhatsApp recording is available for context or cutaway during the same beat.
  asset: `footage/selects/story_clips/bihe_darta_question_tight.mp4`
  assets: `footage/selects/story_clips/bihe_darta_question_tight.mp4`, `footage/selects/story_clips/whatsapp_bihe_darta_user.mp4`
  position: right third vertical phone crop
- `extraction` (support / animated_labels): WHERE, SERVICE, INTENT labels extract from sentence and connect to phone bubbles.
  text: `WHERE -> Dharmadevi Nagarpalika / SERVICE -> marriage registration / INTENT -> how do I do it?`
- `workflow` (support / video): Compact workflow clip shows question moving into handling.
  asset: `footage/selects/story_clips/bihe_darta_compact_workflow.mp4`

Transition in: phone pop in

Transition out: cut to Pi

### B11 - Why Gemma

Time: `1:13-1:20` (`7.0s`).

Purpose: Make Gemma pivotal: local, open, capable enough for messy service navigation.

VO cue:

```text
Gemma was pivotal because it is small enough for local deployment...
```

On-screen text:

```text
Gemma on Raspberry Pi
local enough for offices
```

Assets:

- `footage/selects/story_clips/pi_gemma_local_inference_smoke_test.mp4`  \n  what happens: Raspberry Pi close-up and terminal/iPad showing Gemma local inference stats  \n  resolves to: `footage/selects/govspeak-2/pi_llama_request_where_i_want_you_to_show_our_smoke_test_results.mp4`

Visual layers:

- `pi_closeup` (hero / video): Raspberry Pi local inference proof is full frame or large left hero.
  asset: `footage/selects/story_clips/pi_gemma_local_inference_smoke_test.mp4`
- `benchmark_chip` (support / text_chip): Gemma E2B Q4 via llama.cpp; about 6-8 generated tokens/sec on short service-navigation answers.
  text: `Gemma E2B Q4 on Raspberry Pi / ~6-8 tok/s for short service answers`
- `local_office_label` (support / text): local enough for offices
  text: `local enough for offices`

Transition in: hard cut

Transition out: cut to ask-first UI

### B12 - Ask First, Answer Second

Time: `1:20-1:26` (`6.0s`).

Purpose: Show navigator behavior, not answering machine behavior.

VO cue:

```text
It can reason through messy ASR text, ask the next question, and compose from sources. The first job is not to answer, but to understand the case.
```

On-screen text:

```text
understand first
answer second
```

Assets:

- `footage/selects/story_clips/chat_ask_first_sources.mp4`  \n  what happens: vague prompt, compact follow-up, Jiri answer with SOURCES USED  \n  resolves to: `footage/selects/helpdesk_product_captures/helpdesk_chat_ask_first_sources.mp4`
- `footage/selects/story_clips/kiosk_voice_asr_pi.mp4`  \n  what happens: tablet transcribes Nepali speech while Raspberry Pi is visible  \n  resolves to: `footage/selects/govspeak-2/kiosk.mp4`

Visual layers:

- `ask_first_ui` (hero / video): Vague prompt becomes compact follow-up, then source-backed answer.
  asset: `footage/selects/story_clips/chat_ask_first_sources.mp4`
- `asr_noise` (support / video): Kiosk ASR shows messy speech becoming text.
  asset: `footage/selects/story_clips/kiosk_voice_asr_pi.mp4`
  position: small inset
- `principle` (support / text): understand first / answer second
  text: `understand first / answer second`

Transition in: hard cut

Transition out: diagram push

### B13 - RAG Is Necessary But Not Enough

Time: `1:26-1:38` (`12.0s`).

Purpose: Explain official source registry, crawlers, health checks, self-healing source maintenance.

VO cue:

```text
RAG alone is weak when truth is scattered across old websites, PDFs, office habits, and the memory of one contact officer. So I built a registry of 800+ government sources, crawlers, health checks, and a self-healing pipeline.
```

On-screen text:

```text
800+ government sources
crawl / health check / repair
```

Assets:

- `footage/selects/story_clips/gov_homepage_montage_20sites.mp4`  \n  what happens: 20 government sites; working pages, errors, popups, fragile portals  \n  resolves to: `footage/selects/gov_homepage_montage/gov_homepage_montage_20sites.mp4`
- `footage/selects/story_clips/digobikas_scraping_tmux.mp4`  \n  what happens: government websites list, then terminal scraping/processing  \n  resolves to: `footage/selects/govspeak-2/digo_bikash_with_gov_scraping_tmux_main.mp4`
- `assets/graphics/previllage_system_architecture_1920x1080.png`
- `assets/graphics/previllage_system_architecture_1920x1080.svg`

Visual layers:

- `gov_sites` (hero / video): Government homepage montage fills the first half as overwhelming source sprawl: popups, PDFs, broken-looking pages, fragile portals.
  asset: `footage/selects/story_clips/gov_homepage_montage_20sites.mp4`
- `crawl_tmux` (support / video): DigoBikas scraping tmux appears as the active self-healing worker over the source sprawl.
  asset: `footage/selects/story_clips/digobikas_scraping_tmux.mp4`
- `architecture_rag` (support / image): Architecture graphic appears only in the last third of the beat, assembling from crawler -> registry -> health check -> retrieval, then exits.
  asset: `assets/graphics/previllage_system_architecture_1920x1080.png`
  assets: `assets/graphics/previllage_system_architecture_1920x1080.png`, `assets/graphics/previllage_system_architecture_1920x1080.svg`
  motion: assemble boxes on nouns; crop to Official RAG and Source Registry, not full diagram for entire beat
- `rag_labels` (support / text_chips): 800+ government sources; crawl; health check; repair
  text: `800+ government sources / crawl / health check / repair`

Transition in: diagram push

Transition out: cut to interview

### B14 - Field Interviews Capture Practical Truth

Time: `1:38-1:50` (`12.0s`).

Purpose: Show tacit office knowledge entering system through interviews.

VO cue:

```text
With this I also created a pipeline to capture tacit knowledge. Government officials can answer simple questions that never go documented.
```

On-screen text:

```text
Which counter first?
Which room?
Which document do people forget?
```

Assets:

- `footage/selects/story_clips/jiri_officer_interview_full.mp4`  \n  what happens: Jiri official interview: inquiry counter, missing documents, sent-back reasons  \n  resolves to: `footage/selects/human_loop_interview/PXL_20260505_072911948_human_loop_interview_full.mp4`

Visual layers:

- `officer_interview` (hero / video): Use 0:50-1:14 from the Jiri information officer interview: inquiry counter and routing citizens to departments.
  asset: `footage/selects/story_clips/jiri_officer_interview_full.mp4`
  source range: `50-74s`
  motion: slow conversational push-in
- `question_cards` (support / text_cards): Questions appear one by one: counter, room, time, forgotten document, why sent back.
  text: `Which counter first? / Which room? / Which document do people forget? / Why are they sent back?`
  position: right side stacked cards, entering only after interview face is established
- `source_tag` (support / lower_third): Jiri municipality practical-source interview
  text: `Jiri municipality practical-source interview`

Transition in: hard cut

Transition out: match cut to admin review

Notes:

- Selected source window from Gemini analysis: 0:50-1:14, covering inquiry counter and practical routing context. Optional cutaways: 1:00-1:35 forgotten documents; 1:55-2:20 sent-back reasons.

### B15 - Review Turns Interview Into Source

Time: `1:50-2:05` (`15.0s`).

Purpose: Prove human knowledge is reviewed and citeable.

VO cue:

```text
Those answers go through review, become practical sources, and can be cited later beside official government sources. Tacit knowledge is only unfair when it stays trapped in one office corridor.
```

On-screen text:

```text
interview -> review -> practical source -> cited answer
```

Assets:

- `footage/selects/story_clips/admin_interview_review_transcribe.mp4`  \n  what happens: admin review page with interview submissions, audio players, approve/transcribe/reject controls  \n  resolves to: `footage/selects/helpdesk_product_captures/helpdesk_admin_interview_review.mp4`
- `footage/selects/story_clips/chat_ask_first_sources.mp4`  \n  what happens: vague prompt, compact follow-up, Jiri answer with SOURCES USED  \n  resolves to: `footage/selects/helpdesk_product_captures/helpdesk_chat_ask_first_sources.mp4`
- `footage/selects/story_clips/source_reference_pitch.mp4`  \n  what happens: presenter points to references/source explanation on screen  \n  resolves to: `footage/selects/govspeak-2/timeline1_cut_10_MVI_3829.mp4`

Visual layers:

- `admin_review` (hero / video): Admin review UI shows interview submissions, audio player, approve/transcribe/reject controls.
  asset: `footage/selects/story_clips/admin_interview_review_transcribe.mp4`
- `cited_answer` (support / video): Source-backed answer clip shows practical source appearing beside official sources.
  asset: `footage/selects/story_clips/chat_ask_first_sources.mp4`
- `source_reference` (support / video): Pitch/source reference clip reinforces citation behavior if needed.
  asset: `footage/selects/story_clips/source_reference_pitch.mp4`
- `pipeline_text` (support / text): interview -> review -> practical source -> cited answer
  text: `interview -> review -> practical source -> cited answer`

Transition in: match cut

Transition out: cut to missing-source flow

### B16 - Human Loop When Source Is Missing

Time: `2:05-2:24` (`19.0s`).

Purpose: Show anti-hallucination and WhatsApp officer outreach loop.

VO cue:

```text
When PreVillage does not know, it should not hallucinate. It says what is missing, shows what sources it checked, and turns the citizen's question into an officer outreach message through the WhatsApp bridge. The answer is not invented. It is asked, reviewed, and folded back into the system for the next person.
```

On-screen text:

```text
no source?
do not hallucinate
ask officer
fold back
```

Assets:

- `footage/selects/story_clips/whatsapp_officer_outreach.mp4`  \n  what happens: WhatsApp demo says no authoritative source and drafts officer outreach message  \n  resolves to: `footage/selects/helpdesk_product_captures/helpdesk_whatsapp_officer_outreach.mp4`
- `footage/selects/story_clips/admin_interview_review_transcribe.mp4`  \n  what happens: admin review page with interview submissions, audio players, approve/transcribe/reject controls  \n  resolves to: `footage/selects/helpdesk_product_captures/helpdesk_admin_interview_review.mp4`

Visual layers:

- `no_source_flow` (hero / video): WhatsApp/outreach demo is the hero: it shows no authoritative source, refusal/status, and drafted officer message.
  asset: `footage/selects/story_clips/whatsapp_officer_outreach.mp4`
- `human_loop_flow` (support / animated_flow): A simple left-to-right flow draws over the real UI: no source -> officer outreach -> review -> practical source. It is an overlay, not a diagram card.
  text: `no source -> officer -> review -> source`
  position: lower third, thin source_blue line with human_green review node
  motion: draw line in four steps synced to narration, expo out
- `review_return` (support / video): Admin review returns for only the last 4 seconds to show the reply can be reviewed and folded back.
  asset: `footage/selects/story_clips/admin_interview_review_transcribe.mp4`
- `no_hallucination_labels` (support / text_chips): no source? do not hallucinate; ask officer; review reply; fold back
  text: `no source? / do not hallucinate / ask officer / review reply / fold back`

Transition in: hard cut

Transition out: cut to voice training

### B17 - Custom Voice Stack

Time: `2:24-2:36` (`12.0s`).

Purpose: Show ASR/TTS grunt work and why voice matters.

VO cue:

```text
The internet UX of forms and buttons was not made with Nepali people in mind. Nepal is voice and language rich. So I trained our own TTS and ASR too.
```

On-screen text:

```text
custom Nepali ASR
custom Nepali TTS
```

Assets:

- `footage/selects/story_clips/voice_collection_sister.mp4`  \n  what happens: voice contributor speaks into mic for voice data collection  \n  resolves to: `footage/selects/govspeak-2/sister_training_voices.mp4`
- `footage/selects/story_clips/tts_huggingface_kala.mp4`  \n  what happens: Hugging Face Space plays Real Nepali TTS v0.2 Kala  \n  resolves to: `footage/selects/govspeak-2/tts_hugging_face_card.mp4`
- `footage/selects/story_clips/tts_epoch_g2p_comparison.mp4`  \n  what happens: TTS comparison UI and G2P explanation  \n  resolves to: `footage/selects/govspeak-2/comparing_different_epoch_tts.mp4`
- `footage/selects/story_clips/g2p_newari_dialect_review.mp4`  \n  what happens: Newari vs mainstream Nepali G2P comparison with reviewer controls  \n  resolves to: `footage/selects/govspeak-2/tts_g2p_newari_dialect_fix.mp4`
- `footage/selects/story_clips/training_tmux_status.mp4`  \n  what happens: terminal panes with training logs, ASR/TTS workers, RAG audit, demo status  \n  resolves to: `footage/selects/govspeak-2/tmux training.mp4`
- `footage/selects/story_clips/kiosk_voice_asr_pi.mp4`  \n  what happens: tablet transcribes Nepali speech while Raspberry Pi is visible  \n  resolves to: `footage/selects/govspeak-2/kiosk.mp4`

Visual layers:

- `voice_collection` (hero / video): Sister voice collection returns as human data/work proof.
  asset: `footage/selects/story_clips/voice_collection_sister.mp4`
- `custom_asr_receipt` (support / video): Kiosk/ASR clip is cropped to the live Nepali transcript area as proof that custom Nepali ASR is part of the stack.
  asset: `footage/selects/story_clips/kiosk_voice_asr_pi.mp4`
  position: top-right 38 percent, transcript crop emphasized
  motion: slide in after sister voice, 8-frame expo out
- `tts_space` (support / video): Hugging Face TTS space plays Real Nepali TTS Kala.
  asset: `footage/selects/story_clips/tts_huggingface_kala.mp4`
- `g2p_review` (support / video): G2P/Newari review UI demonstrates language-specific work.
  asset: `footage/selects/story_clips/g2p_newari_dialect_review.mp4`
- `tts_training` (support / video): TTS epoch/G2P comparison is visible as the training-quality receipt, not just a terminal flash.
  asset: `footage/selects/story_clips/tts_epoch_g2p_comparison.mp4`
- `voice_labels` (support / text_chips): custom Nepali ASR; custom Nepali TTS; G2P review; voice data collection
  text: `ASR trained for Nepali speech / TTS trained from collected voice / G2P review for Nepali + local variants`
- `voice_training_terminal` (support / video): Training tmux appears as a narrow terminal strip showing ASR/TTS jobs, epochs, and checkpoints.
  asset: `footage/selects/story_clips/training_tmux_status.mp4`
  position: bottom 18 percent full width
  motion: vertical crop pan over logs, no more than 4 seconds continuous

Transition in: hard cut

Transition out: cut to pipeline in action

### B18 - Voice Pipeline In Action

Time: `2:36-2:45` (`9.0s`).

Purpose: Show the complete speak-to-answer loop as product evidence: speech, ASR, Gemma fixing/planning, retrieval, and TTS response.

VO cue:

```text
A citizen speaks. Our Nepali ASR transcribes. Gemma fixes the rough text and plans the intent. Retrieval finds official and practical sources. Our Nepali TTS speaks back.
```

On-screen text:

```text
speak -> ASR -> Gemma fix -> intent -> retrieve -> TTS
```

Assets:

- `footage/selects/story_clips/kiosk_voice_asr_pi.mp4`  \n  what happens: tablet transcribes Nepali speech while Raspberry Pi is visible  \n  resolves to: `footage/selects/govspeak-2/kiosk.mp4`
- `footage/selects/story_clips/chat_ask_first_sources.mp4`  \n  what happens: vague prompt, compact follow-up, Jiri answer with SOURCES USED  \n  resolves to: `footage/selects/helpdesk_product_captures/helpdesk_chat_ask_first_sources.mp4`
- `footage/selects/story_clips/tts_huggingface_kala.mp4`  \n  what happens: Hugging Face Space plays Real Nepali TTS v0.2 Kala  \n  resolves to: `footage/selects/govspeak-2/tts_hugging_face_card.mp4`

Visual layers:

- `kiosk_asr` (hero / video): Kiosk voice demo shows speech becoming transcript with Pi visible.
  asset: `footage/selects/story_clips/kiosk_voice_asr_pi.mp4`
- `pipeline_overlay` (support / text): speak -> ASR -> Gemma fix -> intent -> retrieve -> TTS
  text: `speak -> ASR -> Gemma fix -> ask/retrieve -> TTS`
  position: bottom rail, icons/labels above actual clips, not center text card
- `gemma_fix_retrieve_receipt` (support / video): Chat ask-first/source-backed clip is cropped to the follow-up and SOURCES USED area, proving Gemma fixes/plans before retrieval.
  asset: `footage/selects/story_clips/chat_ask_first_sources.mp4`
  position: right 42 percent, stacked above TTS receipt
  motion: snap crop to follow-up, then source-card area
- `tts_answer_receipt` (support / video): TTS Hugging Face Kala clip plays as the spoken answer proof after retrieval.
  asset: `footage/selects/story_clips/tts_huggingface_kala.mp4`
  position: right 42 percent lower stack
  motion: enter after retrieve word, 10-frame expo out

Transition in: hard cut

Transition out: cut to office deployment

### B19 - Office Deployment

Time: `2:45-2:52` (`7.0s`).

Purpose: Show office does not need L40 GPU; local device can run helpdesk onsite.

VO cue:

```text
On WhatsApp and kiosks in the office, help starts where people already ask for help. PreVillage is small enough to run on Raspberry Pi for compute and centralized enough to share and capture tacit knowledge.
```

On-screen text:

```text
local compute
shared tacit knowledge
office-ready helpdesk
```

Assets:

- `footage/selects/story_clips/pi_gemma_local_inference_smoke_test.mp4`  \n  what happens: Raspberry Pi close-up and terminal/iPad showing Gemma local inference stats  \n  resolves to: `footage/selects/govspeak-2/pi_llama_request_where_i_want_you_to_show_our_smoke_test_results.mp4`
- `footage/selects/story_clips/kiosk_voice_asr_pi.mp4`  \n  what happens: tablet transcribes Nepali speech while Raspberry Pi is visible  \n  resolves to: `footage/selects/govspeak-2/kiosk.mp4`
- `footage/selects/story_clips/whatsapp_bihe_darta_user.mp4`  \n  what happens: woman asks about marriage registration in Nepali through WhatsApp-like flow  \n  resolves to: `footage/selects/govspeak-2/bihe_darta_question_whatsapp_kala.mp4`

Visual layers:

- `pi_proof` (hero / video): Raspberry Pi local Gemma proof returns as deployment evidence.
  asset: `footage/selects/story_clips/pi_gemma_local_inference_smoke_test.mp4`
- `kiosk_whatsapp` (support / video_pair): Kiosk and WhatsApp clips show office and phone entry points.
  assets: `footage/selects/story_clips/kiosk_voice_asr_pi.mp4`, `footage/selects/story_clips/whatsapp_bihe_darta_user.mp4`
- `onsite_boundary` (support / animated_boundary): A thin office-shaped boundary draws around Pi, kiosk, and WhatsApp entry points to show onsite deployment and privacy locality.
  text: `onsite office helpdesk`
  position: around pi_proof and kiosk/WhatsApp pair, 24px inset
  motion: line draws clockwise in 18 frames; human_green pulse on local node
- `deployment_line` (support / text): heavy work builds the knowledge / small local model runs the helpdesk onsite
  text: `heavy work builds knowledge / small local model runs the office helpdesk`
  position: top-left over solid paper strip

Transition in: hard cut

Transition out: decelerate to title

### B20 - Definition And Close

Time: `2:52-3:00` (`8.0s`).

Purpose: Ensure conclusion clearly defines PreVillage and lands the privilege line.

VO cue:

```text
Title-card close after recorded narration tail.
```

On-screen text:

```text
PreVillage
public-service knowledge before privilege
```

Assets:

- `footage/selects/story_clips/jiri_mountain_wide.mp4`  \n  what happens: wide mountain landscape, valley, distant peaks  \n  resolves to: `footage/selects/govspeak-2/timeline1_cut_04_GX012656.mp4`
- `footage/selects/story_clips/road_to_jiri_motorcycle.mp4`  \n  what happens: motorcycle POV on winding mountain road  \n  resolves to: `footage/selects/govspeak-2/timeline1_cut_06_GX012660.mp4`

Visual layers:

- `jiri_close_background` (hero / video): Jiri mountain footage fills the background; road footage can cross-cut for one final movement beat.
  assets: `footage/selects/story_clips/jiri_mountain_wide.mp4`, `footage/selects/story_clips/road_to_jiri_motorcycle.mp4`
  position: full-bleed background with warm paper grade
  motion: slow push; no new diagram motion
- `definition` (support / text): PreVillage definition appears in four short lines.
  text: `PreVillage is a voice-first government-service navigator. / It asks first, checks official and practical sources, / reaches officers when sources are missing, / and can run inside the office.`
  position: left half, four lines max, large readable Devanagari-capable sans
- `final_title` (hero / text): PreVillage title and public-service knowledge before privilege close the video.
  text: `PreVillage / public-service knowledge before privilege`
  position: final 2.5 seconds, center-left, title only

Transition in: soft decelerating fade

Transition out: fade to black

Notes:

- Keep this quiet. The definition should land before the final title; do not crowd the close with both the full privilege line and tagline simultaneously.

## Edit Rule

Every technical shot must answer at least one question:

- Why is the problem real?
- Why was Gemma necessary?
- Why is this more than a chatbot?
- Why can it run where government service happens?
- Why will a normal person use it?
