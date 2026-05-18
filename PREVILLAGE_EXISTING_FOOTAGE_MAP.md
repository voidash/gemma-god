# PreVillage existing footage map

Source host: `cdjk@<video-workstation-tailnet-ip>`

Source folder:

```text
/Users/cdjk/video/PreVillageSpeaks 2
```

Raw footage copy on the 4TB SSD:

```text
/mnt/transcend4tb/video-creation/previllage-gemma-for-good-2026/footage/raw/PreVillageSpeaks2
```

SSD manifest:

```text
/mnt/transcend4tb/video-creation/previllage-gemma-for-good-2026/footage/raw/PreVillageSpeaks2_manifest.tsv
```

Inventory date: 2026-05-17.

Total media found: 19 videos + 1 photo, about 27 GB. Estimated video duration:
about 86 minutes.

Thumbnail storyboard generated at:

```text
/Users/cdjk/video/PreVillageSpeaks2_inventory/thumbs
```

Local copy of storyboard thumbnails:

```text
/Users/cdjk/github/llm/gemma-god/tmp/previllage_footage_thumbs/
```

## Existing Footage Groups

### A. Journey to Jiri / Remoteness

These are strong visual proof that the project left the laptop and went to a
real municipality.

| File | Duration | Format | Observed content | Use in edit |
|---|---:|---|---|---|
| `GX012647.MP4` | 12:56.9 | 1920x1080, 23.98 fps | motorcycle road POV, hills, traffic, river/valley | opening journey montage, "180 km to Jiri" |
| `GX012652.MP4` | 0:27.9 | 1920x1080, 23.98 fps | road POV beside water / mountain view | scenic bridge shot |
| `GX012653.MP4` | 0:43.9 | 1920x1080, 23.98 fps | road through settlement / hillside | transition from remote road to office |
| `GX012656.MP4` | 0:11.6 | 1920x1080, 23.98 fps | mountain/valley establishing shot | quick "Jiri context" insert |
| `GX012657.MP4` | 0:21.4 | 1920x1080, 23.98 fps | road POV, hills, clear sky | road montage |
| `GX012660.MP4` | 0:25.1 | 1920x1080, 23.98 fps | road junction / sky / mountains | journey montage |
| `GX012668.MP4` | 0:23.9 | 1920x1080, 23.98 fps | approach to public building / signboard | arrival at office |
| `PXL_20260505_023631333.mp4` | 0:05.9 | 1920x1080, 30 fps | mountain/valley phone clip | establishing cutaway |
| `PXL_20260505_032645285.mp4` | 0:05.3 | 1920x1080, 30 fps | mountain/valley phone clip | establishing cutaway |
| `PXL_20260505_011111109.jpg` | photo | 3072x4080 | Pixel photo, likely Jiri/travel context | still insert if needed |

Best use: first 20 seconds and final 10 seconds. Keep the road shots short and
kinetic. They should say "I went there" without becoming a travel vlog.

### B. Public Office Pitch / Meeting

This is the strongest human proof. It shows the idea being pitched in a real
office setting.

| File | Duration | Format | Observed content | Use in edit |
|---|---:|---|---|---|
| `GX012671.MP4` | 35:14.1 | 1920x1080, 23.98 fps | long wide shot of office presentation, multiple officials around table | show mayor/CDO/municipality pitch; pull 3-5 seconds |
| `GX022671.MP4` | 28:34.1 | 1920x1080, 23.98 fps | continuation of meeting/presentation, officials and projected screen | human loop / institutional buy-in |
| `MVI_3829.MOV` | 4:52.2 | 1920x1080, 25 fps | closer presentation shot, presenter silhouetted against projected UI | tech pitch / product explanation |

Best use: 1:45-2:10 human-loop section. Do not overuse. One wide shot, one
close presentation shot, one listening/reaction shot is enough.

Action needed:

- Confirm consent / whether faces and names can be shown.
- Pull cleaner subclips from the long GoPro files. Do not put 35-minute source
  files directly into the edit timeline.

### C. Practical Office / Interview / Desk Demo

These show the real "tacit knowledge" layer: people at desks, laptops, forms,
and in-office explanation.

| File | Duration | Format | Observed content | Use in edit |
|---|---:|---|---|---|
| `PXL_20260505_072818251.mp4` | 0:09.7 | 1920x1080, 30 fps | office desk setup, person with laptop/papers | "we collected office knowledge" |
| `PXL_20260505_072911948.mp4` | 2:39.6 | 1920x1080, 30 fps | office interview / desk demo / people looking at computer | practical source layer, interview evidence |

Best use: after saying "the missing information is often human: which counter,
which document, which time, which person."

Action needed:

- Identify who is visible and what consent level is safe.
- If audio is usable, transcribe key lines and extract one subtitle-worthy quote.

### D. Existing Screen / UI / Speech Stack Captures

These are phone-recorded screen clips. They can support the tech story but should
not replace clean screen recordings.

| File | Duration | Format | Observed content | Use in edit |
|---|---:|---|---|---|
| `20260516_210143.mp4` | 0:07.1 | vertical 2160x3840, 29.62 fps | person at laptop / dark room / screen glow | "late-night build" texture |
| `PXL_20260428_161758368.mp4` | 0:22.0 | vertical 1080x1920, 30 fps | phone video of web page/form-like screen | early speech/data portal proof |
| `PXL_20260503_063332300.mp4` | 0:21.2 | vertical 1080x1920, 30 fps | phone video of TTS/review/admin-like web UI | speech stack portal proof |
| `PXL_20260503_063359779.mp4` | 0:04.0 | vertical 1080x1920, 30 fps | short phone screen clip | quick insert only |
| `PXL_20260503_063637843.mp4` | 1:06.9 | vertical 1080x1920, 30 fps | longer phone screen capture of portal/list UI | backup B-roll for ASR/TTS/data portals |

Best use: only as gritty "we were building" footage. For legibility, capture
fresh screen recordings of the same portals.

Action needed:

- Re-record clean desktop captures for:
  - `https://ampixa.com`
  - `https://tts.ampixa.com`
  - `/speak`
  - `/voices`
  - `/rating`
  - `/g2p`
  - helpdesk chat
  - interview/admin
  - WhatsApp demo

## Missing Footage We Still Need

### Must Capture

1. **Kiosk / live voice v0**
   - user speaks or types;
   - ASR transcript appears;
   - Gemma transcript fixer repairs WER/script noise;
   - resolver/planner shows intent;
   - answer returns with official + practical sources;
   - TTS-ready answer or audio playback appears.

2. **WhatsApp contact-officer loop**
   - known question gets a cited answer;
   - missing room/counter question creates a contact-officer message;
   - do not show a real pairing QR or private number unless intentionally safe.

3. **Clean tech B-roll**
   - TTS epoch log replay;
   - ASR 509.54h training-base doc;
   - NepTTS-Bench screenshots/MOS table;
   - G2P review page;
   - source registry/crawler/RAG docs;
   - `docker ps`/Traefik infra shot.

4. **Onsite deployment shot**
   - Raspberry Pi or low-cost office computer with the kiosk UI;
   - message: each office can run a capable-enough local navigator onsite.

5. **Origin story visual**
   - Reddit post screenshot or recreated text cards:
     - 3 weeks;
     - 4 offices;
     - 4 forms;
     - about 8k to middlemen;
     - "paying for information, not service."

### Nice To Capture

- Your hands using the system.
- A person in an office asking a natural voice question.
- TTS waveform/audio playback.
- Before/after transcript correction.
- Source cards showing gov source plus human practical source.
- Short "Previ lays" egg/infrastructure animation.

## Proposed Timeline Mapping

| Video time | Story beat | Existing footage | New footage needed |
|---|---|---|---|
| 0:00-0:20 | invisible government route | Reddit origin card, office/travel flashes | clean Reddit/text card |
| 0:20-0:45 | privilege confession | road POV, mountain shots, late-night laptop | L40/AWS/training log screen |
| 0:45-1:15 | diagnosis | road-to-office transition, public building arrival | source registry / RAG crawl visuals |
| 1:15-1:45 | infrastructure stack | screen clips as texture | clean portal + code + eval captures |
| 1:45-2:10 | human loop | meeting/pitch, office interview desk | consent-safe quote/subtitle |
| 2:10-2:35 | voice and WhatsApp | sister voice footage from separate source; screen clips | kiosk voice + WhatsApp demo |
| 2:35-3:00 | onsite office deployment | road/mountain return shot, office table | Raspberry Pi/office kiosk shot |

## Edit Notes

- Use the Jiri meeting footage as authority, not as filler.
- Use the road footage as a privilege/travel metaphor: one person could travel
  and decode the system; the product should remove that requirement.
- Use phone-shot UI footage sparingly. The final video needs clean screen
  recordings for credibility.
- Cut the two 30+ minute meeting files into small selects before importing into
  Remotion/Resolve.
- Keep the product claim honest: the current live missing piece is the kiosk
  voice path and complete WhatsApp handoff.
