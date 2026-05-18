# Audit - `previllage_master_delivery_v1.mp4`

File audited:

```text
/Volumes/TRANSCEND/video-creation/previllage-gemma-for-good-2026/renders/final/previllage_master_delivery_v1.mp4
```

QC references:

```text
/Volumes/TRANSCEND/video-creation/previllage-gemma-for-good-2026/renders/final/qc/previllage_master_delivery_v1_1fps_sheet.jpg
/Volumes/TRANSCEND/video-creation/previllage-gemma-for-good-2026/renders/final/qc/audit_midframes/
```

## Verdict

This is a rendered rough master, not a final submission cut.

It proves the project can be rendered end-to-end, but it is not yet deliberate
enough second by second. The main failures are editorial and narrative, not
technical encoding failures.

## Critical Issues

1. **The final spoken conclusion is missing.**
   - Captions/narration end at `162.84s`.
   - B19 runs `165-172s`; B20 runs `172-180s`.
   - That means the office-deployment close and final PreVillage definition are
     only visual/music, not voiced.
   - This is a direct problem because the close should say what PreVillage is.

2. **All source footage is muted.**
   - `MediaFrame` defaults every video to `muted=true`.
   - The Jiri phone/UX quote, interview clips, sister voice collection, and
     human-loop footage are visually present but not heard.
   - This breaks the intended "hear the mayor / hear the field" effect.

3. **There are placeholder asset cards on screen.**
   - Around `4s`, the video shows a `source asset` card for
     `mock_government_form_document.pdf`.
   - That reads like unfinished pipeline/debug UI, not a final edit.

4. **Beat starts briefly fade through black.**
   - Exact beat-start keyframes at `15s`, `23s`, `30s`, `36s`, etc. are black or
     near-black because each beat fades in from opacity 0.
   - In playback this is brief, but it creates unnecessary visual blinking.

5. **Caption errors remain visible.**
   - Last captions include:
     - `and ASR 2`
     - `help privilege is small enough...`
   - These should be corrected to ASR/TTS and PreVillage. In a submission video,
     wrong captions damage trust immediately.

## Story / Impact Issues

6. **The WhatsApp bihe-darta demo is too small.**
   - It appears as one piece in a grid instead of a hero moment.
   - The story needs at least one clear "person asks naturally -> system asks
     follow-up -> useful route" sequence.

7. **The RAG/self-healing architecture is not understandable enough.**
   - B13 shows source/crawler material, but it does not clearly explain:
     source registry -> crawl -> health check -> repair -> retrieval -> answer.
   - The human-loop flow is stronger, but still mostly UI screenshots and labels.

8. **The v0-to-v6 / iteration story is mostly missing.**
   - v0 web-first is present.
   - The evolution into resolver, RAG hardening, SFT failures/improvements,
     ASR/TTS, and human loop is not compactly visualized as an iteration arc.

9. **Gemma is stated, not fully proven.**
   - Raspberry Pi footage is visible, but benchmark numbers are not.
   - There is no clear visual proof of "small enough locally, capable enough to
     repair noisy ASR and ask follow-ups" beyond text labels.

10. **Custom ASR/TTS grunt work is underplayed.**
    - B17/B18 show technical footage, but the trained Nepali ASR/TTS achievement
      is not given enough visual hierarchy.
    - The sister voice / collection / training / output chain should read as a
      real build arc, not a background receipt.

## Craft Issues

11. **Too much of the video uses the same grammar.**
    - Paper-card screenshot + bottom caption + small chips repeats too often.
    - The video feels assembled, not edited.

12. **Some frames have large empty areas.**
    - Example: B12 around `83s` has a large blank white area with a small UI.
    - This wastes visual space during the "ask first, answer second" claim.

13. **Audio bed is functional but not emotionally directed.**
    - The score is quiet and loudness-normalized, but it is synthetic and only
      section-ducked.
    - It does not yet react to specific emotional moments: Reddit pain, Jiri
      field quote, human loop, or final definition.

14. **Original interview/field audio is absent.**
    - The video has no authentic field sound except what may be embedded under
      muted visuals.
    - This makes the real-world footage feel less alive.

## What To Fix First

1. Record/add a final VO line for B19-B20:
   - "PreVillage is a voice-first government-service navigator..."
   - "I used privilege to find the path..."
2. Unmute and duck selected real footage audio:
   - Jiri phone/UX quote;
   - one interview line;
   - sister voice collection for 1-2 seconds if useful.
3. Replace `mock_government_form_document.pdf` placeholder with a rendered image.
4. Correct captions from the locked text, not only Chirp2 output.
5. Make the WhatsApp bihe-darta demo a hero sequence.
6. Add a single clean architecture animation:
   - sources -> crawler -> health check -> RAG -> resolver -> answer;
   - missing answer -> officer -> review -> practical source.
7. Remove beat-start black flicker by using hard cuts or overlap transitions,
   not per-beat opacity resets.
