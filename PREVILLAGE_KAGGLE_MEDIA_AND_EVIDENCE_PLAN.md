# PreVillage Kaggle Media and Evidence Plan

Snapshot: 2026-05-18.

Purpose: keep the Gemma 4 Good writeup and media gallery grounded in visible
proof. The writeup should stay under 1,500 words; images, captions, and video
shots carry the extra engineering detail.

Selected image/caption gallery:

- `PREVILLAGE_KAGGLE_MEDIA_GALLERY.md`
- `PREVILLAGE_TECH_WRITEUP_EVIDENCE.md`

## Kaggle Media Use

Kaggle submissions require a cover image and media gallery. Use the gallery for
screenshots, diagrams, and demo clips that prove the claims in the writeup. The
writeup can reference these artifacts, but should not depend on readers parsing
large screenshots to understand the product.

Safe media rule:

- Use consent-cleared field footage only.
- Blur phone numbers, QR codes, tokens, private chats, and private admin URLs.
- Do not show raw officer/citizen interview audio or identities unless the
  person consented to public use.
- Do not show officer auto-messaging in the public demo. Human contact can be
  shown as a reviewed source/contact, not an automated outbound message.

## Must-Have Proof Images

| Media | What it proves | Source / capture target | Notes |
|---|---|---|---|
| Cover image | PreVillage is public-service knowledge before privilege | Designed still or product composite | Should show citizen/service navigation, not a generic chatbot |
| Architecture diagram | Resolver-first RAG, source routing, human loop, ASR/TTS | `PREVILLAGE_PUBLIC_ARCHITECTURE.md` | Keep one screen, readable in gallery |
| Source registry / corpus audit | The RAG is maintained, not a pile of PDFs | crawler/source registry/audit terminal or admin screen | Include 1,071 sources, 46,051 docs, 272,718 chunks if still current |
| Self-healing loop | Missing sources become crawl/review/interview tasks | gap log, health audit, or admin review screenshot | Caption: evidence-path repair, not model magic |
| Jiri contact answer | Local factual routing works | `helpdesk.ampixa.com/chat` | Example: mayor/helpdesk/information officer from `jirimun.gov.np` |
| Interview intake form | Practical knowledge collection exists | `interview-ne-final.png` or live `/interview` | Show Nepali form if readable |
| Admin review screen | Human claims are reviewed before retrieval | `admin-expanded.png` or live `/admin` | Caption: official sources stay legal authority; interviews are practical evidence |
| WhatsApp bridge | The channel is real Baileys, not a fake screen | `whatsapp-demo-local.png` or live `/whatsapp` | Hide QR and private phone numbers |
| Kiosk voice flow | Raw ASR -> fixed question -> answer -> TTS | live `/kiosk` | Best proof of voice access |
| ASR training evidence | Scratch ASR failed; pretrained path was deliberate | `~/github/llm/g2p/ASR/docs/asr-sota-and-base-model-choice-2026-05-12.md` | Show collapse and Hindi/Indic-pretrained lesson |
| TTS evaluation evidence | Voice quality was judged by humans, not loss alone | NepTTS-Bench / HF dataset / rating UI | Public claim: 164+ speakers, 5,760+ ratings unless public card is updated |
| Pi / edge lane | Local Gemma is plausible in offices | Pi llama.cpp terminal or benchmark doc | Claim only 6-8 tok/s for E2B Q4; do not claim full national RAG on Pi |

## Remote Video Workspace

Use the remote video project as the source of truth for footage selection and
Gemini clip descriptions:

```text
cdjk@<video-workstation-tailnet-ip>:/Volumes/TRANSCEND/video-creation/previllage-gemma-for-good-2026
```

Important files:

- `analysis/gemini/govspeak-2/clip_index.md` - Gemini-generated clip summaries
  and suggested story sections.
- `footage/raw/PreVillageSpeaks2_manifest.tsv` - raw footage manifest.
- `footage/selects/govspeak-2/` - current selected clips.
- `footage/selects/human_loop_interview/` - office/interview select.
- `footage/selects/whatsapp_bihe_darta/` - WhatsApp workflow select.
- `footage/selects/gov_homepage_montage/` - government homepage montage.
- `spec/rough_spec_v1.md` - current rough video plan.
- `spec/narration_text.txt` - current teleprompter/narration text.
- `notes/PREVILLAGE_EXISTING_FOOTAGE_MAP.md` - human footage map.
- `notes/PREVILLAGE_NEXT_CAPTURE_PLAN.md` - remaining capture plan.

Do not treat Gemini clip descriptions as authoritative facts. Use them for
triage, then verify the clip visually/audio-wise before final edit.

## Remote Clip Candidates

| Clip | Use | Why it matters |
|---|---|---|
| `footage/selects/govspeak-2/timeline1_cut_01_GX012647.mp4` through `timeline1_cut_07_GX012668.mp4` | Journey / privilege / Jiri arrival | Shows the 180 km fieldwork and move from laptop to real municipality |
| `footage/selects/govspeak-2/timeline1_cut_08_GX022671.mp4` | Ground-truth UX quote | Meeting-room footage where Man Bahadur Jirel discusses what people actually use phones for |
| `footage/selects/govspeak-2/timeline1_cut_09_MVI_3829.mp4` and `timeline1_cut_10_MVI_3829.mp4` | Office pitch / Gemma + sources explanation | Shows the project being presented in a real official setting |
| `footage/selects/govspeak-2/timeline1_cut_11_PXL_20260505_072911948.mp4` | Practical office/interview layer | Desk/form/laptop footage for tacit knowledge collection |
| `footage/selects/human_loop_interview/PXL_20260505_072911948_human_loop_interview_full.mp4` | Human-source loop | Longer interview/desk context; use only consent-safe excerpts |
| `footage/selects/govspeak-2/digo_bikash_with_gov_scraping_tmux_main.mp4` | RAG/source crawling | Government website plus scraping/processing terminal |
| `footage/selects/govspeak-2/tmux training.mp4` | Engineering arc | Training logs, audits, ASR/TTS/local worker status |
| `footage/selects/govspeak-2/supervised_finetuning_v2_checking questions_from_deepseek.mp4` | SFT iteration proof | Shows SFT/eval work, but frame it as a learning arc, not the final product |
| `footage/selects/govspeak-2/sister_training_voices.mp4` | Voice data collection | Human voice work behind ASR/TTS |
| `footage/selects/govspeak-2/comparing_different_epoch_tts.mp4` | TTS pain/evaluation | Good visual for listening-based checkpoint comparison |
| `footage/selects/govspeak-2/tts_g2p_newari_dialect_fix.mp4` | G2P / dialect repair | Shows language-specific voice engineering, not generic TTS |
| `footage/selects/govspeak-2/tts_hugging_face_card.mp4` | Public TTS artifact | Hugging Face proof shot |
| `footage/selects/govspeak-2/kiosk.mp4` | Kiosk/ASR/local deployment | Tablet voice flow with Raspberry Pi visible |
| `footage/selects/govspeak-2/pi_llama_request_where_i_want_you_to_show_our_smoke_test_results.mp4` | Local Gemma E2B | Pi plus terminal inference output |
| `footage/selects/govspeak-2/ampixa_live_chat_usage.mp4` | Product chat/RAG | Live PreVillage chat interaction |
| `footage/selects/govspeak-2/bihe_darta_question_whatsapp_kala.mp4` | WhatsApp question | Citizen-style WhatsApp service query |
| `footage/selects/whatsapp_bihe_darta/bihe_darta_compact_workflow_01s20_08s50.mp4` | WhatsApp workflow | Better short select for showing a compact interaction |
| `footage/selects/gov_homepage_montage/gov_homepage_montage_20sites.mp4` | Coverage breadth | Quick proof that source coverage spans many government sites |

## Video-To-Writeup Mapping

| Writeup claim | Best video proof |
|---|---|
| "I could travel 180 km to ask an office" | Jiri road/arrival clips |
| "The route was privileged" | Origin cards + road + office meeting |
| "Gemma is local enough for offices" | Pi llama.cpp clip + kiosk clip |
| "Not a chatbot, a navigator" | chat/kiosk follow-up + source-backed answer |
| "RAG heals at evidence layer" | source registry/crawler/self-healing tmux clips |
| "Human sources are practical authority" | Jiri meeting/interview + admin review screen |
| "Voice is access, not garnish" | sister voice capture + ASR kiosk + TTS comparison |
| "WhatsApp matters because people already use it" | Man Bahadur UX quote + WhatsApp clips |

## ASR Pain Points to Cover

The writeup should not present ASR as a solved checkbox. It should say why the
voice layer exists and what we learned.

Evidence to draw from:

- `~/github/llm/g2p/ASR/docs/asr-sota-and-base-model-choice-2026-05-12.md`
- `https://huggingface.co/spaces/voidash/nepali-fastconformer-demo`

Concrete lessons:

- Scratch FastConformer CTC was the wrong main path for our clean Nepali data
  scale.
- Full mixed training collapsed to a dominant token pattern; SLR54 controls
  also collapsed.
- A small overfit diagnostic did learn, so tokenizer/plumbing were not the sole
  cause.
- Hindi/Indic-pretrained ASR was the more defensible route; the official Hindi
  CTC smoke improved materially over early epochs.
- In PreVillage, Gemma repairs noisy transcripts and asks confirmation when
  ASR uncertainty matters.

Writeup framing:

> Voice is not a garnish. It is where government help already happens. The
> ASR work taught us not to hide speech errors: show the raw transcript, repair
> it with Gemma, and route only after the question is understood.

## TTS Pain Points to Cover

The TTS story should be honest: the public models exist, but the important
engineering lesson is that listening beat metrics.

Evidence to draw from:

- `~/github/llm/g2p/CLAUDE.md`
- `~/github/llm/g2p/docs/tts-review-20260504-results.md`
- `https://huggingface.co/ampixa/real-nepali-v0.2-kala`
- `https://huggingface.co/ampixa/real-nepali-v0.4`
- `https://huggingface.co/spaces/ampixa/real-nepali-tts`
- `https://huggingface.co/datasets/ampixa/neptts-bench`

Concrete lessons:

- Validation loss was not enough to select a usable Nepali voice.
- Early listening review found systemic punctuation, pronunciation, rhythm, and
  intonation issues.
- Known failure words included `chhora` and `ramro`, and punctuation did not
  reliably change intonation.
- Algenib was a strong recording/support voice but a weak TTS speaker.
- NepTTS-Bench was built because human Nepali listeners were needed for real
  evaluation.

Writeup framing:

> We did not train voice models so the demo could talk. We trained and evaluated
> them because a public-service system in Nepal has to survive spoken Nepali,
> messy pronunciation, and answers that people can listen to at a counter.

## Human Practical Knowledge

The writeup should explicitly show that interviews are part of the retrieval
system, not decoration.

Evidence to draw from:

- `frontend/src/routes/Interview.tsx`
- `frontend/src/routes/Admin.tsx`
- `scripts/process_interview.py`
- `server/main.py`
- `interview-ne-final.png`
- `admin-expanded.png`
- `PREVILLAGE_RAG_ARCHITECTURE_FOR_VIDEO.md`

Concrete implementation:

- `/interview/submit` collects practical office/citizen knowledge.
- `/admin/submissions` lets a reviewer inspect submissions.
- `/admin/submission/{sid}/approve` moves approved practical claims into the
  usable corpus.
- `/admin/tacit/reload` reloads approved claims into retrieval.
- Tacit/practical sources are labeled with role, confidence, provenance, and
  source type.
- Jiri contact extraction recognizes officials such as mayor Mitra Bahadur
  Jirel, deputy mayor Krishnamaya Budhathoki, CAO Raj Kumari Khatri, and
  information officer Man Bahadur Jirel from official Jiri sources.

Writeup framing:

> Websites give legal facts. Reviewed people give practical facts: which room,
> which counter, which document people forget, which number still works. Those
> claims are named, dated, reviewed, and treated as practical evidence, not law.

## Self-Healing Coverage

Self-healing must not sound like autonomous hallucination repair. It is an
operations loop around evidence.

What to show:

- source discovery adding missing offices;
- crawler fetching HTML/PDF sources;
- extraction/chunking making pages searchable;
- health audits finding empty, duplicate, stale, or broken sources;
- planner gaps turning bad answers into source/contact/interview tasks;
- admin review turning approved practical knowledge into retrieval records.

Writeup framing:

> The RAG heals at the evidence layer. If a page is fetched but not searchable,
> if a local office source is missing, or if practical room-level knowledge is
> absent, the system records the gap and routes it back into crawl, review, or
> human collection.

## What Still Needs Capturing

- Clean `/chat` shot answering one Jiri official/contact question with cited
  source.
- Clean `/kiosk` shot with Nepali/Roman-Nepali voice input, raw ASR, fixed
  query, answer, and TTS playback.
- Clean `/whatsapp` shot with a real inbound message and reply, with private
  phone numbers hidden.
- Clean source-health or gap-log shot showing the self-healing loop.
- Consent-safe field/interview still or subtitle if Man Bahadur Jirel or any
  named officer appears in public media.
