# PreVillage writeup working draft

Snapshot: 2026-05-18.

This document turns the video narration into a written submission. The video
can be emotional and compressed; the writeup needs to show that the product was
earned through iteration, not a thin demo wrapped around a chatbot.

## Thesis

PreVillage is public-service knowledge infrastructure for Nepal.

The core problem is not only that government information is missing online. The
deeper problem is that the usable route through government services is often
tacit: which office owns the case, which room handles it, which document gets
rejected, which phone number still works, and what to do when the website is
silent.

The story should stay anchored on this line:

> I used privilege to find the path. PreVillage exists so the next person does
> not need privilege to use their own government.

## Lessons from prior Gemma winners

Source research:

- `PREVILLAGE_GEMMA4GOOD_WRITEUP_RESEARCH.md`
- `PREVILLAGE_GEMMA4GOOD_SUBMISSION_PLAN.md`

The current Gemma 4 Good writeup is capped at 1,500 words and is explicitly a
proof-of-work report. The video is the star of the submission; the writeup
should verify that the video is backed by real engineering.

Patterns from previous Gemma 3n winners:

- Gemma Vision won by combining a human tester, a practical accessibility
  workflow, and very specific engineering tradeoffs: on-device inference,
  streaming, camera latency, controller UX, TalkBack/VoiceOver, and deterministic
  OCR when the model alone was not reliable.
- Vite Vere was easy to scan: what it does, key features, architecture, how
  Gemma is used, challenges overcome, and why the choices fit the user.
- 3VA made the system real by naming the person, explaining the training data,
  and adding a clear "what is real" validation section.
- Sixth Sense used an explicit prompt/contract, scenario tests, performance
  numbers, hardware details, and caveats.
- LENTERA is the closest precedent for PreVillage: an offline/local knowledge
  appliance for last-mile access, with honest hardware and latency tradeoffs.

Implication for our final writeup:

PreVillage should not try to include the whole build diary. It should prove four
things quickly: the hidden-route problem is real; the product is a service
navigator rather than a chatbot; Gemma 4 is load-bearing for planner/composer,
voice repair, and local deployment; and the engineering is real through crawler,
RAG, audits, rejected checkpoints, WhatsApp, kiosk, voice, and edge evidence.

ASR and TTS belong in the writeup, but only as the access layer. The voice story
is: citizen speaks; ASR transcribes; Gemma repairs noisy transcript and performs
intake; RAG retrieves sources; TTS speaks back a compact answer. Keep this to one
paragraph in the Kaggle writeup. Public evidence exists through
`ampixa/real-nepali-v0.2-kala`, `ampixa/real-nepali-v0.4`,
`ampixa/real-nepali-tts`, and `ampixa/neptts-bench`. The ASR demo Space exists.
The ASR checkpoint is now intended to be public for the submission; use
provisional wording until the cleaned HF artifact URL is live, then cite it
directly.

## What the current narration already does well

- It opens with a concrete harm: three weeks, four offices, four versions of
  the same form, about NPR 8,000 to middlemen.
- It makes the moral point cleanly: the law was public, the route was
  privileged.
- It gives Gemma a meaningful role: open, local, small enough for office/edge
  deployment, capable enough for intake and grounded composition.
- It distinguishes PreVillage from a normal chatbot: intake first, retrieval
  second, answer with sources, admit gaps.
- It includes the access layer: kiosk, WhatsApp, voice, and onsite deployment.

## What the narration currently underplays

The written version should include these because they prove seriousness:

1. We first tried the training-first path and it failed.
2. CPT on an instruction-tuned model regressed because raw Nepali text swamped
   chat behavior.
3. SFT improved narrow behaviors but was not enough as a factual helpdesk.
4. Research changed the plan: SFT should teach planner/composer behavior, not
   memorize government facts.
5. RAG became load-bearing, but only after resolver-first routing, source
   ranking, evals, and deterministic guardrails.
6. The crawler/source registry matters as much as the model.
7. Human practical sources are part of the knowledge base, not decoration.
8. Gemma matters because it makes local deployment plausible, not because it
   magically knows Nepal government services.
9. The Pi/llama.cpp work proves the edge story in hardware terms.
10. ASR/TTS matter because Nepal's public-service UX should be spoken, not only
    typed.

## Safe evidence to use

### Origin and product

Source docs:

- `STORY.md`
- `HACKATHON_VIDEO_STORY_PRIVILEGE.md`
- `HACKATHON_VIDEO_SCRIPT_PREVILLAGE_V1_GEMMA.md`
- `SERVICE_NAVIGATOR_MODUS_OPERANDI.md`

Claims:

- The project started from company registration/PAN pain: weeks lost, multiple
  offices, changing instructions, middleman cost.
- Product identity is government-service navigator, not generic RAG Q&A.
- Required behavior: resolver/intake first, compact follow-ups, chat memory,
  question-dependent source routing, contacts, uncertainty, named human
  practical sources when reviewed.

### Corpus and crawler

Source docs:

- `PIPELINE.md`
- `CRAWLER.md`
- `RAG_HARDENING_STATUS.md`
- `PREVILLAGE_RAG_ARCHITECTURE_FOR_VIDEO.md`
- `HACKATHON_DEMO_RUNBOOK.md`

Claims:

- The stack includes a data-driven source registry, crawler, extraction,
  chunking, FTS retrieval, health audit, and source discovery scripts.
- Early corpus work had to handle broken TLS, dead portals, Preeti/legacy font
  PDFs, scanned PDFs, OCR, PDF extraction crashes, and link rot.
- RAG self-healing means evidence-path repair: detect pages fetched but not
  searchable, duplicate URLs, zero-text documents, stale sources, and missing
  practical knowledge.
- Do not overclaim a fully autonomous production crawler unless timer proof is
  shown. Say scheduled/cron-capable maintenance loop and health audit.

Numbers we can safely cite from docs:

- May 10 demo runbook: 899/899 sources crawled, 270,509 searchable chunks.
- May 11/16 hardening snapshot: 1,071 sources, 46,051 live documents, 272,718
  chunks after MoHA, DAO, embassy, and transport focused crawls.
- Public smoke after planner/reranking/coverage work passed service/RAG audits
  with no bad citations or loops in the tested set.

### RAG and planner

Source docs:

- `SERVICE_NAVIGATOR_MODUS_OPERANDI.md`
- `RAG_HARDENING_STATUS.md`
- `scripts/service_navigator_pipeline_audit.py`
- `server/navigator.py`
- `server/main.py`

Claims:

- The live answer path is planner-first.
- Planner emits service, action, case type, office, district, municipality,
  ward, missing slots, source classes, expected domains, retrieval query, and
  gaps.
- Different question types route to different evidence: contacts, legal
  eligibility, fees, forms, complaint handoff, local office routing, practical
  counter knowledge.
- Recent live smoke passed 14/14 after adding noisy Nepali/Dharmadevi
  normalization. This is useful as an internal confidence claim, not the main
  public headline.

### CPT/SFT iteration

Source docs:

- `BENCHMARKS.md`
- `SFT_V2_RESULTS.md`
- `SFT_V5_POSTMORTEM_AND_NEXT_PASS.md`
- `SFT_V6_PLANNER_COMPOSER.md`
- `FINETUNE_RESEARCH.md`

Claims:

- CPT v1 regressed: Belebele 63% baseline to 52% fast eval, FLORES en->ne
  chrF 38.15 to 33.46, Roman-Nepali loops appeared.
- Diagnosis: CPT on an instruction-tuned model with mostly raw text caused
  catastrophic forgetting of chat behavior.
- SFT v2 fixed Roman-Nepali degeneration in its small test and showed refusal
  examples teach behavior, but quality/helpfulness remained insufficient.
- v5 E4B adapter trained successfully but was rejected because it invented
  facts, over-answered ambiguous cases, and misrouted services.
- v6 reframed SFT as planner/composer distillation over provided sources.
- v6.2 fixed citation format, but still refused too many answerable cases.
- v6.3 mixed hard negatives into final-answer training and regressed badly,
  especially Roman-Nepali loops.
- v6.4 split planner/answerability/composer tasks and became the first serious
  RAG-backed composer candidate:
  - quick48 wrong refusals 2/48 = 4.2%;
  - url_recall 0.94;
  - source-ID citations 45/48;
  - Roman-Nepali degen/loops/mojibake 0/10;
  - still not safe as a naked factual chatbot.

Public framing:

> We did not pretend every checkpoint worked. The training failures were the
> product research. They showed that facts belong in the source layer, decisions
> belong in the planner, and SFT should teach behavior around evidence.

### Research pass

Source doc:

- `FINETUNE_RESEARCH.md`

Claims:

- A literature pass changed the recipe.
- Key conclusion: SFT alone often regresses knowledge QA; SFT + RAG is the
  right shape for knowledge-intensive tasks.
- For low-resource adaptation, mixed native + translated/synthetic data beats a
  single-source dataset, but synthetic alone is risky.
- Eval must include open-generation and groundedness, not only multiple-choice
  or translation.
- Gemma 4 details mattered: Apache 2 license, Gemma 4 chat template,
  MatFormer/E2B subset inside E4B, and local deployment implications.

### Gemma and local deployment

Source docs:

- `SFT_V2_RESULTS.md`
- `SFT_V6_PLANNER_COMPOSER.md`
- `PI_E2B_LLAMA_CPP_RUNBOOK.md`
- `PREVILLAGE_PI_VOICE_BENCHMARK_2026_05_17.md`

Claims:

- E2B is the realistic edge/Pi target; E4B is the stronger training/helpdesk-PC
  candidate.
- E4B SFT training needed L40S/g6e.xlarge; L4/g6.xlarge was not viable for the
  E4B recipe due to memory.
- Gemma E2B Q4_K_M runs locally on Raspberry Pi 5 through llama.cpp.
- Measured Pi generation was roughly 6-8 tok/s on short prompts.
- Do not claim the Pi runs the full national RAG stack. Correct framing:
  Pi proves a low-cost local edge lane; an office computer can host the fuller
  kiosk/RAG/admin loop.

### Voice, WhatsApp, kiosk

Source docs:

- `HACKATHON_DEMO_RUNBOOK.md`
- `PREVILLAGE_PI_VOICE_BENCHMARK_2026_05_17.md`
- `PREVILLAGE_WRITEUP_AND_VIDEO_RESOURCE_BRIEF.md`

Claims:

- Real Baileys WhatsApp bridge exists.
- WhatsApp text and audio path works: media download -> local FastConformer ASR
  worker -> `/query` -> local real Nepali Kala TTS worker -> compact voice
  reply.
- Local k2 voice workers are far faster than old HF Space path:
  - ASR warm about 498-532 ms server-side on tested sample;
  - TTS warm about 290-310 ms server-side.
- Pi voice benchmark:
  - Piper/VITS-style Nepali TTS warm around 1.1-1.4s;
  - FastConformer ASR warm around 2.9-3.0s for a short Nepali WAV;
  - the transcript still showed errors, proving why Gemma fixer/intake matters.
- `/kiosk` exists with browser microphone, rolling ASR snapshots, streamed
  answer, latency display, and TTS playback.

Important safety:

- Do not present proactive WhatsApp officer messaging as automatic production
  behavior. It must be operator-reviewed; current demo auto-send is disabled.

## Proposed writeup structure

### 1. The hidden map

Open with the story from the narration. Keep it short and concrete.

Goal: make the reader understand that the problem is public knowledge trapped
behind tacit routing.

Possible opening:

> Three weeks. Four offices. Four versions of the same form. Almost eight
> thousand rupees to middlemen.
>
> The law was public. The route was privileged.

Then define the core unfairness:

> I could keep asking. I had time, technical knowledge, GPU access, family
> support, and the ability to travel 180 kilometers to ask an office how things
> really work. Most people only get sent to the next queue.

### 2. What PreVillage is

Do not jump to models. Define product:

> PreVillage is a government-service navigator for Nepal. It helps a citizen
> turn a messy question into an actionable case: what service, which office,
> what location, what documents, what fee, who to contact, and what evidence is
> missing.

Key phrase:

> A normal chatbot guesses. PreVillage does intake.

### 3. Why RAG had to become infrastructure

Explain that a pile of PDFs is not enough:

- sources are scattered;
- PDFs are old encodings or scans;
- websites change or break;
- local pages hide contacts inside inconsistent structures;
- official facts and practical facts are different evidence classes.

Introduce registry/crawler/health:

> PreVillage watches the evidence base, not just the user question.

### 4. The human loop

This is where Jiri matters.

Official websites say the formal rule. Human practical sources explain the
counter path.

Write clearly that human claims are reviewed, named, dated, confidence-labelled
practical evidence, not anonymous rumors.

### 5. Why Gemma mattered

This should be central but honest.

Gemma mattered because:

- open weights make local/on-prem deployment plausible;
- E2B can run on Pi/office edge hardware;
- E4B can be trained/tested as a stronger composer;
- Gemma can repair noisy transcripts, normalize intent, ask follow-ups, and
  compose from sources when placed inside the RAG/planner loop;
- local inference matters for privacy and unreliable connectivity.

Avoid:

- "Gemma knows all government services";
- "fine-tuning solved the product";
- "the Pi runs the entire national stack."

### 6. The training failures that shaped the product

This is important for the written submission because it proves the engineering
journey.

Suggested narrative:

> The first instinct was to train the model harder. That failed.
>
> CPT made the model more exposed to Nepali text but less able to behave like a
> chat assistant. SFT fixed narrow issues, then broke others. v5 was clean
> stylistically but unsafe factually. v6 only became promising after we stopped
> asking one adapter to do every decision and split the work into planner,
> answerability, and composer tasks.

Then state the learning:

> The lesson was not "fine-tuning is useless." The lesson was that public
> service help is a systems problem. Facts live in the corpus. Routing lives in
> the planner. Style and grounded composition can be taught to the model.

### 7. Voice and WhatsApp

Explain why this is not a website-only product:

> Nepal was never voice-poor. The internet UX was not built for us.

Then give the pipeline:

> A citizen speaks. ASR transcribes. Gemma repairs the messy text and plans the
> case. Retrieval finds official and practical sources. TTS speaks back. On
> WhatsApp, the same help starts where people already talk.

### 8. Local deployment

Write:

> The point is not that every office needs an L40 GPU. The heavy work builds and
> refreshes the knowledge. The office runs a local helpdesk over its own source
> cache, common services, and intake flows.

Mention Pi/Gemma E2B as proof of local edge possibility.

### 9. What works now and what remains

Be clear:

Works:

- planner-first RAG path;
- source-backed answers for tested flows;
- noisy Nepali normalization cases;
- contact extraction for known offices;
- WhatsApp text/audio path;
- kiosk voice path;
- Pi E2B local proof;
- reviewed-human-source pipeline concept and UI.

Still not fully solved:

- full source coverage and freshness;
- production supervision and observability;
- more human practical sources;
- ASR confirmation for names/wards/municipalities;
- v6.4 adapter needs more real pipeline testing before public composer
  replacement;
- safety around outreach/contacting officers.

### 10. Close

Return to privilege:

> I used privilege to find the path. PreVillage exists so the next person does
> not need privilege to use their own government.

## First long-form draft

Three weeks. Four offices. Four versions of the same form. Almost eight
thousand rupees to middlemen.

The law was public. The route was privileged.

That was the contradiction that started PreVillage. The information I needed
was not a secret in the legal sense. The forms, acts, notices, and offices were
public. But the usable path was not public: which office first, which counter
next, which document would be rejected, which phone number still worked, and
which person could explain the thing the website never said.

I could keep pushing. I had time, technical knowledge, GPU access, family
support, and enough mobility to travel 180 kilometers to ask an office how the
process really worked. Most people do not get that many attempts. They get sent
to another queue, another office, or another middleman.

So the question became: what should privilege lay?

Not another private shortcut. Public infrastructure.

That is PreVillage: a government-service navigator for Nepal. It is designed
for citizens who ask messy, incomplete, code-mixed, spoken, or Roman-Nepali
questions and need an actionable path through government services. A normal
chatbot tries to answer immediately. PreVillage first tries to understand the
case: what service is this, what action is needed, which office owns it, what
location matters, what documents or fees are being asked about, and what facts
are still missing.

If the case is ambiguous, it asks a compact follow-up. If it knows the office,
contact, document, fee, or procedure, it answers with sources. If the source is
missing, it says so and records the gap.

This became more than a RAG demo because the evidence base itself is the hard
part. Nepal government information is spread across ministries, departments,
district offices, municipalities, PDFs, notices, contact pages, and scanned
documents. Some PDFs are in old Nepali font encodings like Preeti. Some are
scans that need OCR. Some sites have broken certificates or inconsistent
routes. Some pages are fetched but not searchable unless extraction and
chunking work correctly.

So PreVillage has a source registry, crawler, extraction pipeline, chunk index,
and health audit. It tracks official sources, crawls and indexes them, checks
for zero-text documents and duplicate URLs, and exposes when the evidence path
is broken. Self-healing here does not mean the model guesses better. It means
the system notices that the source layer is stale, empty, duplicated, or
missing, and routes that problem back to crawl, repair, or human collection.

The human layer matters because official websites do not always contain the
most useful answer. A law can say what is allowed. A local officer can tell you
which room checks the document. A citizen who completed the process can tell
you what people forget. PreVillage treats those as different kinds of evidence.
Official sources remain legal authority. Reviewed officer, staff, and citizen
interviews become named, dated, confidence-labelled practical sources.

Gemma was pivotal because this could not just be a cloud chatbot. Government
help should work where the citizen is: at a counter, on a kiosk, on WhatsApp,
and inside the office itself. Gemma gives us an open model small enough for
local deployment and capable enough, inside the system, to repair noisy speech,
normalize intent, ask follow-up questions, and compose from retrieved sources.

We learned that the hard way. The first instinct was to train harder. Continued
pretraining on Nepali text made the model worse at the actual task: it regressed
on Nepali reading, weakened translation, and produced Roman-Nepali repetition
loops. The diagnosis was catastrophic forgetting: raw Nepali text had swamped
chat behavior in an instruction-tuned model.

Then we tried SFT. It helped narrow behaviors. Roman-Nepali degeneration could
be fixed. Refusal examples could teach the model to refuse unsupported claims.
But each version exposed a new failure. Some adapters invented contacts. Some
answered when they should ask follow-ups. Some learned to cite but then added
a refusal tail. One v6 pass got source recall high while completely regressing
Roman-Nepali into loops.

The research pass changed the architecture. For public-service knowledge, the
model should not memorize facts. Facts belong in the corpus. Routing belongs in
the planner. Fine-tuning should teach evidence behavior: resolve the case, ask
when ambiguous, decide whether sources are sufficient, cite source IDs, avoid
Hindi drift, and stop cleanly.

That led to the current split: deterministic resolver and source router in
front, RAG over official and practical sources, and Gemma as a grounded planner
or composer behind that evidence. The best v6.4 adapter became a serious
RAG-backed candidate only after we split planner, answerability, and composer
tasks. It is still not treated as a naked factual chatbot. That is the point:
the product is the loop, not one checkpoint.

The access layer follows the same principle. Nepal was never voice-poor. The
internet UX was not built for us. A citizen should be able to speak. ASR
transcribes. Gemma repairs the messy text and plans the question. Retrieval
finds official and practical sources. TTS speaks back. On WhatsApp, the same
help can start where people already talk.

For offices, the point is not that every local government needs an L40 GPU. The
heavy work builds the knowledge. The office runs the helpdesk. Gemma E2B can run
locally through llama.cpp on a Raspberry Pi 5 at roughly 6-8 generated tokens
per second for short prompts. That does not replace the full national RAG stack,
but it proves the edge lane: common intake, local fallback, privacy-sensitive
questions, and office-side service navigation do not have to begin in the
cloud.

PreVillage is still unfinished. Source coverage must keep expanding. More
officer and citizen interviews need review. WhatsApp and kiosk need production
supervision and observability. ASR needs confirmation loops for names, wards,
and municipalities. The SFT model must keep improving inside the planner/RAG
contract.

But the direction is clear. The problem was never that citizens lacked
intelligence. The problem was that the usable map of government services was
distributed across websites, PDFs, counters, and people with time to ask.

I used privilege to find the path. PreVillage exists so the next person does
not need privilege to use their own government.

## Shorter writeup version

Use this if the submission has a tight word limit.

Three weeks, four offices, four versions of the same form, and almost eight
thousand rupees to middlemen taught me the real problem: Nepal's government
information is public in theory but privileged in practice. The forms and laws
exist, but the usable path lives in scattered PDFs, broken websites, counters,
and people's heads.

PreVillage is my attempt to turn that tacit route into public infrastructure.
It is not a generic chatbot. It is a government-service navigator. It resolves
the user's case first: service, action, office, location, ward, document, fee,
contact, and missing information. If the case is ambiguous, it asks a compact
follow-up. If it knows, it answers with sources. If it does not have evidence,
it says so.

The system combines official `.gov.np` crawling, a source registry, health
checks, RAG, reviewed human practical sources, WhatsApp, kiosk voice, ASR, TTS,
and local Gemma deployment. Official websites provide legal facts. Officers and
citizens provide reviewed practical facts: which room, what time, which document
people forget, and who to contact.

Gemma mattered because this could not remain a cloud-only demo. Government help
should work at the counter, on a kiosk, on WhatsApp, and inside the office
itself. Gemma E2B can run locally on low-cost hardware through llama.cpp, while
larger Gemma variants can serve as stronger planner/composer models behind the
RAG stack.

The hardest lesson was that fine-tuning alone was not enough. Continued
pretraining on raw Nepali text regressed chat behavior. Several SFT passes
improved one behavior while breaking another: refusals, citations, Roman-Nepali,
follow-ups, or factual reliability. That forced the right architecture: facts
live in the source layer, routing lives in the planner, and Gemma composes only
from evidence.

A citizen speaks. ASR transcribes. Gemma repairs the noisy text and plans the
case. Retrieval finds official and practical sources. TTS speaks back. The
office can run the helpdesk locally over its own evidence.

I used privilege to find the path. PreVillage exists so the next person does
not need privilege to use their own government.

## Claims to avoid

- Do not say the SFT adapter alone powers the public demo.
- Do not claim all Nepal government workflows are solved.
- Do not claim the Pi runs the full national RAG stack.
- Do not present proactive officer WhatsApp outreach as automatic production
  behavior.
- Do not imply human practical sources are unreviewed authority. They are
  practical evidence after review.
- Do not imply every source is fresh and complete. The point is that the system
  exposes freshness and gaps.

## Strong lines to reuse

- The law was public. The route was privileged.
- A normal chatbot guesses. PreVillage does intake.
- Facts live in the corpus. Routing lives in the planner. Gemma composes from
  evidence.
- Self-healing does not mean the model guesses better. It means the evidence
  path gets repaired.
- Nepal was never voice-poor. The internet UX was not built for us.
- The heavy work builds the knowledge. The office runs the helpdesk.
- I used privilege to find the path. PreVillage exists so the next person does
  not need privilege to use their own government.
