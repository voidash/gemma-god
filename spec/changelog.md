# Spec Changelog

## 2026-05-18 - Human Loop Evidence Path Placement

- Added the WhatsApp self-healing evidence-path board to B15 around `1:57`
  so reviewed interviews/officer replies read as practical sources, not filler.
- Rebuilt B16 around `2:10` as the concrete missing-source loop:
  citizen question, gap detection, contact found from scraped web content,
  WhatsApp officer outreach, review, and source repair.
- Replaced the previous generic B16 receipt stack with timed callouts and a
  readable full-board visual from
  `assets/previllage-writeup-gallery/submission/whatsapp_self_heal_flow.png`.

## 2026-05-18 - B15 Self-Healing Flowchart Correction

- Replaced the B15 WhatsApp-heavy board around `1:56` with a real
  self-healing RAG flowchart.
- B15 now shows repair triggers: stale/dead source, fetched-but-zero-chunk
  content, tacit room/counter questions, and weak retrieval/ranking.
- B15 repair paths now branch into recrawl/discover, parse/OCR, dedupe/rerank,
  interview/review, and WhatsApp officer bridge as only one human-contact path.

## 2026-05-18 - `sequence_spec_v1.json` Codex Review Fixes

- Promoted `spec/sequence_spec_v1.json` as the real machine-readable source of truth required by the footage skill.
- Added `global_assets` for locked narration audio, narration text, Chirp2 word timings, and subtitles.
- Added `asset_resolution` so semantic story clip names remain readable while `footage/selects/story_clips/ALIASES.tsv` maps them to the original media.
- Bound every beat-level ready asset to a visible layer or global asset; validation now passes with zero unused ready assets.
- Changed B03 into a readable receipt wall instead of a decorative news montage.
- Made B04's process reference image visibly used as a faint texture, removing the hidden-reference conflict.
- Selected B14's human-loop interview range: `0:50-1:14`, with optional cutaways for forgotten documents and sent-back reasons.
- Reworked B16 as a human-loop pattern break around the real WhatsApp/officer outreach demo instead of another architecture card.
- Strengthened B17-B18 so custom ASR, TTS, G2P, Gemma correction, retrieval, and spoken response are visible receipts.
- Reduced late architecture repetition and made B20 a grounded PreVillage definition/title close.

## 2026-05-18 - Full Remotion Project And Master Render

- Built the full Remotion project under `remotion/` on the 4TB SSD project, with `Master` plus B01-B20 beat compositions generated from `spec/sequence_spec_v1.json`.
- Added spec validation, asset staging, composition listing, and still-render validation scripts.
- Staged 51 public Remotion assets from the project media tree.
- Re-encoded only the B08 GoPro-derived story clip as a Remotion-safe derivative; the original source footage was left untouched.
- Switched the B05 privilege-flex clips to native looping video decode while keeping normal clips on offthread rendering, fixing the `ERR_UPLOAD_FILE_CHANGED` decode failure at the old frame-691 failure point.
- Validation passed:
  - TypeScript compile;
  - Remotion composition registration;
  - machine spec validation;
  - 60/60 beat stills.
- Rendered the full 180-second master to `renders/final/previllage_master.mp4` on the SSD.
- Final media probe: 1920x1080, 30fps H.264 video, AAC audio, 180.053 seconds, about 157 MiB.

## 2026-05-18 - Scored Delivery Pass

- Added an explicit `rules.audio_design` block to `spec/sequence_spec_v1.json`.
- Generated an original quiet score bed at `audio/music/previllage_score_bed.wav`; copied it into Remotion public assets.
- Added section-level score ducking in `remotion/src/Master.tsx`:
  - near-silent cold open;
  - low pressure under origin/problem;
  - slight lift for privilege/Jiri/system build;
  - ducked fieldwork, anti-hallucination, and officer-loop claims;
  - controlled lift through the silent close.
- Rendered the scored master to `renders/final/previllage_master_scored_v1.mp4`.
- Created the delivery-normalized master at `renders/final/previllage_master_delivery_v1.mp4` by copying video and normalizing audio.
- Final delivery probe:
  - 1920x1080, 30fps H.264 video;
  - 48kHz AAC audio;
  - 180.1 seconds;
  - about 163 MiB;
  - integrated loudness about `-16.4 LUFS`;
  - true peak `-1.5 dBFS`.
- Generated one-frame-per-second QC sheet at `renders/final/qc/previllage_master_delivery_v1_1fps_sheet.jpg`.

## 2026-05-18 - Delivery v2 Fix Pass

- Reworked `spec/sequence_spec_v1.json` and the Remotion renderer around the
  delivery v1 audit findings.
- Replaced the unfinished PDF source-card placeholder with
  `assets/sources/forms/mock_government_form_document.png`.
- Removed beat-level fade-through-black by disabling per-beat opacity fades.
- Added the selected Jiri phone/UX quote audio and ducked narration under it.
- Added a scratch spoken close at `165s` and manual close captions that define
  PreVillage directly.
- Corrected visible caption errors for ASR/TTS, PreVillage, and related terms.
- Promoted the fieldwork, WhatsApp, Pi/Gemma, RAG, human-loop, ASR/TTS/G2P, and
  onsite-office sections into deliberate custom layouts.
- Replaced fragile blank UI loops in the ask-first, human-loop, and voice-flow
  sections with clear receipt stills.
- Rendered the visual fix pass to `renders/final/previllage_master_fixpass_v2.mp4`.
- Created the delivery-normalized master at
  `renders/final/previllage_master_delivery_v2.mp4`.
- Final delivery probe:
  - 1920x1080, 30fps H.264 video;
  - 48kHz AAC stereo audio;
  - 180.1 seconds;
  - about 146 MiB;
  - integrated loudness about `-16.2 LUFS`;
  - true peak about `-1.8 dBFS`.
- Generated one-frame-per-second QC sheet at
  `renders/final/qc/previllage_master_delivery_v2_1fps_sheet.jpg`.

## 2026-05-18 - Quote And Natural-Question Alignment

- Tightened the B08 source-audio trim so the real Jiri Android/TikTok/Facebook
  quote lands audibly instead of starting too early in the setup.
- Trimmed the B08 quote video to the same source range for closer lip/gesture
  alignment.
- Changed the B10 route chips from a specific Dharmadevi overlay to
  `user's municipality`, because the locked VO says Dharmadevi but the captured
  WhatsApp source line says Kirtipur.

## 2026-05-18 - Layout Collision Pass

- Replaced the B02 synthetic four-office route graphic with the annotated route
  board from `/Users/cdjk/Downloads/shapes at 26-05-18 15.58.11 Large.png`,
  stored as `assets/graphics/four_office_route_annotated_large.png`.
- Added beat-aware caption safe zones in `NarrationCaptions.tsx` so global VO
  captions no longer always occupy the bottom of the frame.
- Hid captions on the densest proof-board / natural-question beats where the
  visual itself carries the same text and captions would cover the evidence.
- Moved captions to top or top-left on beats with bottom rails, lower-thirds,
  phone panels, or final title text.
- Hid global captions on the Jiri quote, practical interview, human-loop,
  voice-flow, and final-title beats where scene-native text already carries the
  meaning and the global caption would collide or duplicate.
- Removed the duplicate B15 top overlay so the human-loop review scene has a
  single clear pipeline statement instead of two competing text blocks.
- Replaced the generic B14 interview stack with a custom layout so the
  practical-source lower third no longer covers the question card.
- Hid the B09 global caption where it collided with the already-learned UX
  split-screen labels and small PreVi-lays visual.
- Shrunk and lifted the B09 PreVi-lays visual so it does not cover the
  `VOICE-FIRST` comparison label.

## 2026-05-18 - Process Animation Pass

- Rebuilt B03 as a dedicated middlemen/news evidence wall:
  - no raw JPG/PNG filenames on screen;
  - no unrelated office/interview cutaway;
  - six source screenshots load as visual evidence with publisher labels;
  - late beat wall uses a 3x2 grid so all six screenshots are visible.
- Rebuilt B04 as a custom Remotion animation instead of foregrounding the
  reference image:
  - online form;
  - print/documents;
  - office validation;
  - waiting in line;
  - job done.
- Kept the process reference video as a slow, looping background plate behind
  the animation.
- Rebuilt B02 from extracted crops of the user's annotated route image:
  - online form;
  - company registrar office;
  - IRD Tripureshwor;
  - IRD Kalimati;
  - IRD Kalanki;
  - animated form-version chips and a moving citizen marker.
- Hid B03 global captions so the evidence-wall bottom line is not covered.

## 2026-05-18 - User Frame Fix Pass

- Fixed B03 frame 294 by changing news evidence screenshots from cropped cover
  placement to contained placement, so the article image is not badly zoomed
  into body text.
- Rebuilt B05 privilege flex as a custom timed layout:
  - sister voice footage starts full screen;
  - slowed tmux/training footage enters as a 50 percent right panel at
    `playbackRate=0.5`;
  - AWS/GPU footage enters later as the third full-height panel;
  - screen videos use contained foregrounds over full-height columns so
    terminal and AWS details are not cropped away.

## 2026-05-18 - B06 Joined Cut Pass

- Rebuilt B06 as a single full-frame sequence of the user's requested DaVinci
  cuts:
  - `timeline1_cut_01_GX012647.mp4`;
  - `timeline1_cut_02_GX012652.mp4`;
  - `timeline1_cut_03_GX012653.mp4`;
  - `timeline1_cut_07_GX012668.mp4`.
- Removed the previous split/inset treatment from this beat so no two videos
  are visible in the same frame.

## 2026-05-18 - Mayor Quote Subtitle Cue Pass

- Added structured timed Nepali subtitle cues for the B08 Jiri mayor quote in
  `remotion/src/generated/mayorQuoteCaptions.json`.
- Rendered the quote subtitle as one short Nepali cue at a time, with an English
  conversion line underneath and a small cue progress rail so the timing reads
  second by second.
- Corrected the cue text against
  `analysis/transcripts/chirp2/jiri_man_bahadur_phone_ux_quote/subtitle_corrected_ne.srt`
  instead of using the earlier paraphrase.

## 2026-05-18 - UX Contrast And WhatsApp Voice Pass

- Enlarged the municipality pitch video during the post-mayor
  lack-of-information line so it reads as the main visual.
- Rebuilt the UX contrast beat as a clearer left/right argument:
  confusing web/form operation on the left, WhatsApp usage on the right.
- Added the user's WhatsApp annotated reference image as an animated reference
  board instead of a static pasted image.
- Re-cut the user-provided hen video from about 6s into
  `footage/selects/story_clips/privi_lays_hen_user_06s_08s.mp4` and placed it
  at the top of the To Lay / To Not Lay contrast.
- Gave the WhatsApp voice-question clip a full-screen source slot and separated
  founder narration from that moment.

## 2026-05-18 - B07 And Sister Footage Fix

- Rebuilt B07 as a custom single-video journey sequence so frame `1159` no
  longer has an inset/support video sitting on top of the background.
- Added a Remotion-only 16:9 framed derivative of the sister voice footage:
  `voice_collection_sister_framed.mp4`.
- Switched B05 to that derivative so the original phone rotation metadata does
  not turn into a hard crop that removes the person's head.

## 2026-05-18 - Privilege Mask Timing Pass

- Retimed the Jiri travel reveal so travel footage starts at the spoken
  `privilege` cue instead of appearing too early.
- Added a true SVG text mask for `PRIVILEGE`: the word is a transparent cutout
  showing travel video through a dark overlay, not white text.
- Continued the mask across B06/B07 and faded the overlay to transparent by the
  `I travelled 180 km to Jiri` narration phrase.
- Kept the travel footage as a one-video-at-a-time sequence while the mask
  clears.

## 2026-05-18 - Mayor Quote Pause Pass

- Created 1.25x mayor-quote selects:
  - `audio/selects/jiri_mayor_phone_ux_quote_1p25.wav`;
  - `footage/selects/story_clips/jiri_android_tiktok_facebook_call_quote_1p25.mp4`.
- Split the founder narration at the fieldwork/product-change moment so the
  mayor quote has its own slot instead of being mixed under ducked narration.
- Rebuilt B08 so the mayor quote is the dominant highlighted visual.
- Added readable Nepali subtitle plus English conversion during the mayor quote.

## 2026-05-18 - RAG Claim And Gemma Pivot Pass

- Moved the real marriage-registration WhatsApp source clip into the founder
  VO cutaway slot and kept it full-screen with source audio.
- Rebuilt B11 so the source question leads into a large `Gemma was pivotal`
  typography moment, then Pi inference proof, kiosk proof, and a compact
  v0-v6 iteration strip.
- Retimed B08-B20 to the editorial output clock after the mayor quote insert
  and the small WhatsApp example-phrase replacement, so later visuals no longer
  drift ahead of narration.
- Extended the B09 To Lay / To Not Lay contrast through frame `1996` and B10,
  removing the premature route/phone sequence.
- Moved the hen flash to the spoken `01:09:03` moment and limited it to roughly
  one second of the pre-trimmed 6s source moment.
- Put B12 on Gemma capability evidence, B13 on RAG/self-healing, and B14 on
  practical human-source interviews according to the corrected narration clock.

## 2026-05-18 - Planner Router Architecture Insert

- Inserted the SpeakGov RAG architecture at the `That is the job` line after
  the real WhatsApp source question.
- Focused the architecture visual on the planner contract/resolver/intake and
  source router crop instead of jumping straight to `Gemma was pivotal`.
- Moved `Gemma was pivotal` later in B11 and paired it with two claims:
  small enough for Raspberry Pi/local deployment, and capable enough for
  planner/router behavior.

## 2026-05-18 - Ask First Real WhatsApp Flow Pass

- Removed the `Gemma was pivotal` title from the filler after the real
  WhatsApp source question; B11 now stays on case extraction and routing at
  the `That is the job` line.
- Moved the `Gemma was pivotal` proof into the start of B12 with Pi inference
  plus planner/router architecture evidence.
- Added the real annotated WhatsApp flow image
  `assets/graphics/whatsapp_real_flow_20260518_165639.png` and made it
  dominate B12 around output `1:31`, when the narration says the first job is
  to understand the case.

## 2026-05-18 - Gemma Timing And Scattered Truth Pass

- Retimed B12 to start at output `1:20.85`, matching the spoken `Gemma was
  pivotal` cue instead of waiting until `1:24.61`.
- Replaced the vague v0-v6 strip with explicit CPT/SFT clarification:
  CPT helped domain language, SFT trained planner/composer behavior from
  synthetic Q/A validation and source-context examples, and the model should
  not memorize government facts.
- Rebuilt the start of B13 as a concrete `truth is scattered` board with old
  websites, PDF rules, office habits, and contact-officer memory before the
  registry/crawl/health-check/repair system appears.

## 2026-05-18 - Corpus Infrastructure And Evidence Repair Pass

- Rebuilt the B13 registry sequence around `1:40` as a corpus infrastructure
  board instead of a generic registry/crawler panel.
- Added the DigoBikas government website index as the source seed and showed
  the maintained pipeline: registry -> crawl -> extract -> chunks ->
  source pack.
- Updated hardening numbers on screen to `1,071 sources`, `46,051 live docs`,
  and `272,718 searchable chunks`.
- Added crawler failure-mode chips for broken sites, old PDF encodings,
  scanned notices, zero-text documents, duplicates, and stale/dead pages.
- Made self-healing explicit as `evidence-path repair`, mapping missing,
  stale, zero-text, duplicate, weak-ranking, and practical gaps into crawl,
  recipe repair, parsing/OCR, dedupe, eval/rerank, or interview/review work.

## 2026-05-18 - Human Question Grid Close

- Ran Chirp2 on the eleven late WhatsApp/user-question clips and saved word
  timestamps under `analysis/transcripts/chirp2/question_grid_20260518/`.
- Replaced the scratch TTS close with a grid of real users asking government
  service questions, one selected word per person.
- Rewired B19-B20 as one continuous close: the grid builds first, then the
  `PreVillage` title and tagline land over the completed human proof.
