# Audit - `previllage_master_delivery_v2.mp4`

File audited:

```text
/Volumes/TRANSCEND/video-creation/previllage-gemma-for-good-2026/renders/final/previllage_master_delivery_v2.mp4
```

QC reference:

```text
/Volumes/TRANSCEND/video-creation/previllage-gemma-for-good-2026/renders/final/qc/previllage_master_delivery_v2_1fps_sheet.jpg
```

## Verdict

This is now the primary review/upload candidate.

The v2 pass fixes the v1 blocking issues: the close now defines PreVillage, the
PDF/debug placeholder is gone, beat-start black flashes are removed, the Jiri
phone/UX quote is audible, key caption errors are corrected, and the weak/blank
UI sections now have readable proof receipts.

## Fixed Since v1

1. **Conclusion now says what PreVillage is.**
   - Scratch editorial VO starts at `165s`.
   - Manual close captions run through the final definition.

2. **One real field quote is audible.**
   - The Jiri Android/phone UX quote is mixed under the narration.
   - Narration is ducked during the quote so the subtitle/audio moment reads.

3. **The unfinished form placeholder is gone.**
   - The old `mock_government_form_document.pdf` source-card is replaced by a
     clean rendered form image.

4. **Beat-start black flicker is removed.**
   - Beat-level opacity fades are disabled.

5. **Caption errors are patched.**
   - ASR/TTS, PreVillage, and other visible recognition mistakes are corrected.

6. **WhatsApp, Pi/Gemma, RAG, human loop, ASR/TTS, and onsite deployment are
   visually clearer.**
   - These sections now use dedicated layouts instead of repeating the same
     generic card grammar.

## Remaining Risks

1. **The close voice is scratch, not founder narration.**
   - Replace `audio/narration/previllage_close_scratch_20260518.wav` with a
     founder-recorded line if time allows.

2. **The human-loop proof is readable but static.**
   - The officer outreach receipt communicates the mechanism, but a live screen
     recording would feel stronger.

3. **The final title hold is quiet.**
   - Scratch close audio ends before the video ends, leaving the last few
     seconds mostly score/title hold. This is acceptable for review, but can be
     tightened if a final VO is recorded.

## Encoding Check

- Video: 1920x1080, 30fps, H.264.
- Audio: AAC, 48kHz, stereo.
- Runtime: 180.1 seconds.
- File size: about 146 MiB.
- Loudness: about `-16.2 LUFS`, true peak about `-1.8 dBFS`.
