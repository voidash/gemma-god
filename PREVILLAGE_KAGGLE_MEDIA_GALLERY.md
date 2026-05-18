# PreVillage Kaggle Media Gallery

Snapshot: 2026-05-18.

Purpose: selected public images and consent-check images for the Gemma 4 Good
writeup. The main writeup should stay tight; this file carries the visual proof,
captions, and Gemini timestamp notes.

Asset folder:

```text
assets/previllage-writeup-gallery/
```

## Upload Order

Use the technical evidence first. The story images can support the origin, but
the Kaggle writeup should prove the engineering reality: failed training passes,
eval gates, RAG operations, cost, and command-level details.

### 0. Technical Proof Set

![Technical evidence contact sheet](assets/previllage-writeup-gallery/tech_contact_sheet.jpg)

Use these individual cards when the gallery needs a stronger technical beat:

- `assets/previllage-writeup-gallery/tech/aws_cost_reality_20260518.png`
- `assets/previllage-writeup-gallery/tech/sft_iteration_reality.png`
- `assets/previllage-writeup-gallery/tech/v6_progression_metrics.png`
- `assets/previllage-writeup-gallery/tech/v6_4_training_command.png`
- `assets/previllage-writeup-gallery/tech/rag_service_eval_gates.png`
- `assets/previllage-writeup-gallery/tech/failure_modes_smoke_tests.png`

Caption draft:

> The core work was not a clean one-shot model train. It was a sequence of
> failed checkpoints, smoke tests, source-routing fixes, RAG gates, and cost
> lessons that pushed PreVillage toward resolver-first retrieval and
> source-backed composition.

Detailed evidence doc:

- `PREVILLAGE_TECH_WRITEUP_EVIDENCE.md`

### 1. The Problem: Public Routes Became Private Routes

![Middlemen problem headline](assets/previllage-writeup-gallery/middlemen_nepalnews_brokers_headline.png)

Caption draft:

> Public-service information has become a market. The same forms and laws are
> public, but the route through offices is often held by middlemen.

Why this image:

- Establishes the pain point before showing the product.
- Stronger than the earlier `middlemen_news_contact_sheet-0.jpg`, which had too
  much whitespace and did not read well in a gallery.
- Keep this as contextual evidence, not as the main proof of our engineering.

### 2. System Architecture

![PreVillage architecture](assets/previllage-writeup-gallery/architecture.png)

Caption draft:

> PreVillage is not a generic RAG chatbot. It resolves the service case first,
> routes the right source types, uses official and reviewed practical evidence,
> and lets Gemma repair, ask, and compose from sources.

Why this image:

- Communicates the central technical claim in one still.
- Anchors the writeup line: "facts should live in sources; Gemma should plan
  and compose."

### 3. Engineering Arc: SFT Was Not The Whole Answer

![SFT evolution](assets/previllage-writeup-gallery/evolution_v1_v6.png)

Caption draft:

> The training arc moved from answer memorization toward planner/composer
> behavior. The durable path was resolver-first RAG plus evaluated source
> routing, not asking an adapter to memorize government.

Why this image:

- Shows honest iteration without overclaiming SFT.
- Useful next to the writeup section "training was useful because it failed."

### 4. Source Coverage

![Government source coverage](assets/previllage-writeup-gallery/gov_homepage_contact_sheet.jpg)

Caption draft:

> Coverage grew from a few local pages to a maintained source registry spanning
> federal departments, DAOs, embassies, municipalities, and service offices.

Why this image:

- Visual proof that this is not a single-site demo.
- Supports the corpus and coverage claims without dumping tables into the
  writeup.

### 5. Source Registry And Crawl Proof

![RAG source registry](assets/previllage-writeup-gallery/rag_source_registry_0005.jpg)

![RAG crawl terminal](assets/previllage-writeup-gallery/rag_crawl_terminal_0009.jpg)

Caption draft:

> The RAG layer is operational: sources are registered, crawled, extracted,
> audited, and repaired when coverage gaps appear.

Why these images:

- The registry still is better for "source discovery exists."
- The terminal still is better for "the crawler actually ran."
- Both came from the Gemini pass over the source-crawling clip.

### 6. Navigator Chat With Sources

![Helpdesk chat with sources](assets/previllage-writeup-gallery/helpdesk_chat_sources_0009.jpg)

Caption draft:

> The chat surface asks when the request is ambiguous and answers from sources
> when the route is clear.

Why this image:

- Shows the user-facing product, not just backend machinery.
- Good proof for "not a chatbot, a navigator."

### 7. Human Practical Knowledge Loop

![Interview intake form](assets/previllage-writeup-gallery/interview_form_ne.png)

![Admin interview review](assets/previllage-writeup-gallery/admin_interview_review_0011.jpg)

Caption draft:

> Official websites give legal facts. Reviewed officers, staff, and verified
> citizens give practical facts: room, counter, timing, missing documents, and
> working contacts.

Why these images:

- The interview form proves practical knowledge collection.
- The admin screen proves review before claims enter retrieval.
- Use this to explain the human loop without showing private interview audio.

### 8. Voice And Kiosk Flow

![Kiosk ASR with Pi](assets/previllage-writeup-gallery/kiosk_asr_pi_0004.jpg)

Caption draft:

> Voice is an access surface. The kiosk captures speech, transcribes it, lets
> Gemma repair the question, routes sources, and speaks back when useful.

Why this image:

- Strongest single still for ASR + kiosk + office hardware.
- Came from the Gemini timestamp around immediate Nepali transcription.

### 9. TTS And Human Evaluation

![Real Nepali TTS Hugging Face](assets/previllage-writeup-gallery/tts_huggingface_kala_0003.jpg)

![NepTTS rating registration](assets/previllage-writeup-gallery/01_rating_registration.png)

Caption draft:

> Nepali speech quality was evaluated by listeners, not just validation loss.
> The public TTS checkpoints and NepTTS-Bench are part of the access layer.

Why these images:

- HF Space/card proves public voice artifact.
- NepTTS-Bench proves the evaluation philosophy.

### 10. Local Gemma On Office Hardware

![Gemma E2B llama.cpp on Pi](assets/previllage-writeup-gallery/pi_gemma_llamacpp_0002.jpg)

Caption draft:

> Quantized Gemma E2B ran locally on Raspberry Pi 5 through llama.cpp. The Pi is
> not the whole national RAG stack; it proves an office-local intake/composer
> lane is plausible.

Why this image:

- Important for Gemma 4 Good: open model, local deployment, office setting.
- Keep the caption careful. Do not claim the Pi runs all services end to end.

### 11. WhatsApp Channel

![WhatsApp bridge](assets/previllage-writeup-gallery/whatsapp_bridge_local.png)

Caption draft:

> The same navigator can answer where people already ask: WhatsApp. The bridge
> is real Baileys infrastructure, not a mock screen.

Why this image:

- Proves channel breadth.
- Do not include private phone numbers, QR codes, or officer auto-messaging in
  the public submission.

## Contact Sheets

Use these for internal review and quick visual selection.

![Public gallery contact sheet](assets/previllage-writeup-gallery/public_gallery_contact_sheet.jpg)

![Consent/internal contact sheet](assets/previllage-writeup-gallery/consent_internal_contact_sheet.jpg)

## Consent Check Before Public Use

These images are useful but should not be public until consent/privacy is
confirmed or faces/private details are blurred.

![Jiri office desk and form](assets/previllage-writeup-gallery/jiri_office_form_laptop_0002_CONSENT_CHECK.jpg)

Potential caption after clearance:

> Fieldwork at Jiri Municipality turned website facts into practical service
> notes: counters, forgotten documents, timing, and contacts.

![Man Bahadur phone UX quote](assets/previllage-writeup-gallery/man_bahadur_phone_ux_quote_CONSENT_CHECK.jpg)

Potential caption after clearance:

> A local official explained the practical UX problem: citizens already ask for
> help through phones and messages; public service systems must meet that habit.

![Voice collection](assets/previllage-writeup-gallery/voice_collection_sister_0005_CONSENT_CHECK.jpg)

Potential caption after clearance:

> Voice data collection for Nepali ASR/TTS work.

Do not use this publicly without additional review:

![Officer outreach internal review](assets/previllage-writeup-gallery/whatsapp_officer_outreach_sheet_INTERNAL_REVIEW.jpg)

Reason:

- The proactive officer outreach demo is no longer the public story.
- It may reveal private contact flow.
- The public story should be reviewed human sources and contacts, not automatic
  outbound officer messaging.

## Gemini Timestamp Notes Used

These are the most useful clip notes from the Gemini pass and manual checks.

| Clip | Timestamp | Image extracted | Use |
|---|---:|---|---|
| `helpdesk_chat_ask_first_sources.mp4` | `00:09` | `helpdesk_chat_sources_0009.jpg` | Chat answer with sources |
| `helpdesk_admin_interview_review.mp4` | `00:11` | `admin_interview_review_0011.jpg` | Human review/admin flow |
| `kiosk.mp4` | `00:04` | `kiosk_asr_pi_0004.jpg` | ASR/kiosk/Pi proof |
| `pi_llama_request_where_i_want_you_to_show_our_smoke_test_results.mp4` | `00:02` | `pi_gemma_llamacpp_0002.jpg` | Local Gemma smoke proof |
| `digo_bikash_with_gov_scraping_tmux_main.mp4` | `00:05` | `rag_source_registry_0005.jpg` | Source registry proof |
| `digo_bikash_with_gov_scraping_tmux_main.mp4` | `00:09` | `rag_crawl_terminal_0009.jpg` | Crawl/processing proof |
| `tts_hugging_face_card.mp4` | `00:03` | `tts_huggingface_kala_0003.jpg` | Public TTS artifact |
| `timeline1_cut_11_PXL_20260505_072911948.mp4` | `00:02` | `jiri_office_form_laptop_0002_CONSENT_CHECK.jpg` | Field/interview proof |
| `sister_training_voices.mp4` | `00:05` | `voice_collection_sister_0005_CONSENT_CHECK.jpg` | Voice collection proof |

Note: `timeline1_cut_08_GX022671.mp4` failed local ffmpeg decode because of a
container/projection issue. The Man Bahadur still currently comes from the
existing thumbnail cache instead:

```text
tmp/previllage_footage_thumbs/GX022671_0034.3s.jpg
```

## Main Writeup Placement

Suggested pairing:

- Opening pain: `middlemen_nepalnews_brokers_headline.png`
- "Not a chatbot": `architecture.png`
- "RAG had to grow up": `gov_homepage_contact_sheet.jpg`,
  `rag_source_registry_0005.jpg`, `rag_crawl_terminal_0009.jpg`
- "People are sources too": `interview_form_ne.png`,
  `admin_interview_review_0011.jpg`
- "Voice is not garnish": `kiosk_asr_pi_0004.jpg`,
  `tts_huggingface_kala_0003.jpg`, `01_rating_registration.png`
- "Where Gemma fits": `pi_gemma_llamacpp_0002.jpg`,
  `evolution_v1_v6.png`
- Channels: `helpdesk_chat_sources_0009.jpg`,
  `whatsapp_bridge_local.png`

## Public Safety Notes

- Strip metadata before upload.
- Blur private phone numbers, QR codes, tokens, private admin URLs, and raw
  interview audio controls if needed.
- Consent-check every image with a face, office screen, document, or private
  chat.
- Do not imply fully autonomous officer messaging. The public story is reviewed
  human practical sources and contacts.
- Do not imply the Pi runs the full cloud backend. The Pi proof is local Gemma
  intake/composition feasibility.
