# Capture Update - 2026-05-18

## New Footage Staged On SSD

### Human Loop Interview

Full source found and staged:

```text
footage/selects/human_loop_interview/PXL_20260505_072911948_human_loop_interview_full.mp4
```

Original full source remains on the remote Mac:

```text
/Users/cdjk/video/PreVillageSpeaks 2/PXL_20260505_072911948.mp4
```

Existing short cut:

```text
footage/selects/govspeak-2/timeline1_cut_11_PXL_20260505_072911948.mp4
```

Gemini full-video analysis:

```text
analysis/gemini/human_loop_interview/clip_md/PXL_20260505_072911948_human_loop_interview_full.md
```

Strong moments from the full interview:

```text
0:10-0:20   office identity: Jiri Municipality Office, Jiri Dolakha
0:45-1:00   inquiry counter / citizens routed to departments
1:00-1:35   commonly forgotten documents
1:55-2:20   why citizens are sent back
2:25-2:35   what citizens should know before visiting
```

Use this as the human proof before the admin review screen. The story should say that interviews are not only research; they become practical source data.

### Government Website Montage

Recorded 20 real government homepages, with popup-close attempts during capture:

```text
footage/selects/gov_homepage_montage/gov_homepage_montage_20sites.mp4
analysis/gov_homepage_montage/capture_manifest.tsv
analysis/gov_homepage_montage/sites.json
analysis/gov_homepage_montage/screenshots/
```

Runtime: about 1:19.8.

Use as a fast cascade under:

```text
old websites -> PDFs -> registry -> crawlers -> health checks -> self-healing
```

### Helpdesk Product Captures

Privacy-safe redacted product recordings:

```text
footage/selects/helpdesk_product_captures/helpdesk_chat_ask_first_sources.mp4
footage/selects/helpdesk_product_captures/helpdesk_admin_interview_review.mp4
footage/selects/helpdesk_product_captures/helpdesk_whatsapp_officer_outreach.mp4
analysis/helpdesk_product_captures/capture_manifest.tsv
analysis/helpdesk_product_captures/contact_sheets/
```

Gemini analysis:

```text
analysis/gemini/helpdesk_product_captures/clip_md/
```

Runtimes:

```text
helpdesk_chat_ask_first_sources.mp4        12.24s
helpdesk_admin_interview_review.mp4        13.80s
helpdesk_whatsapp_officer_outreach.mp4      9.32s
```

What each proves:

- `helpdesk_chat_ask_first_sources.mp4`: vague prompt -> compact follow-up -> source-backed Jiri answer using a citizen interview source.
- `helpdesk_admin_interview_review.mp4`: interview audio/transcripts in admin review, including pending approve/transcribe flow.
- `helpdesk_whatsapp_officer_outreach.mp4`: missing acceptable source -> refusal/source status -> officer outreach message through the WhatsApp-style interface.

## Narration Update

`spec/narration_text.txt` is now V4:

```text
spec/narration_text.txt
spec/narration_text_v4_20260518.txt
```

Previous V3 backup:

```text
spec/narration_text.before_v4_20260518_0158.txt
```

Core V4 proof chain:

```text
field interview -> reviewed practical source -> cited answer
missing answer  -> officer outreach       -> future practical source
```

The human-loop line should be treated as central, not optional.
