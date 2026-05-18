# PreVillage: Public-Service Knowledge Before Privilege

**Subtitle:** A Gemma 4 government-service navigator for Nepal: intake,
grounded sources, voice, WhatsApp, kiosk, and local deployment.

> Draft status: v0 for Kaggle. Keep final body under 1,500 words. Replace the
> ASR/public-demo placeholders before submission.

## Submission Draft

Three weeks. Four offices. Four versions of the same form. Almost eight
thousand rupees to middlemen.

That was the origin of PreVillage. The law was public, but the route was
privileged: which office had jurisdiction, which counter came first, which
document was actually rejected, which phone number still worked, and what to do
when the official website was silent.

I could keep pushing. I had time, technical knowledge, GPU access, family
support, and the ability to travel 180 kilometers to ask an office how things
really work. Most people only get sent to the next queue. PreVillage is an
attempt to turn that privilege into public infrastructure.

## What It Does

PreVillage is not a generic RAG chatbot. It is a government-service navigator
for Nepal.

A normal chatbot tries to answer. PreVillage first tries to understand the
case. It resolves the service, action, location, office, case type, and missing
details. If the case is ambiguous, it asks compact follow-up questions. If it
knows the likely office, contact person, document source, or complaint channel,
it gives that while clearly saying what is still missing.

The same service loop works across plain web chat, kiosk, WhatsApp, and voice:

```text
citizen question
  -> ASR if audio
  -> Gemma transcript repair and intake
  -> service resolver and source router
  -> official and reviewed practical retrieval
  -> Gemma grounded composer
  -> answer, contacts, citations, follow-up, uncertainty
  -> TTS if the answer should be spoken
```

The product goal is simple: a citizen should not need an inside contact to know
where to go, what to carry, who to call, and what remains uncertain.

## Why Gemma 4

Gemma 4 matters because public help should not depend only on a distant cloud
chatbot. Government-service support needs to run where citizens are: at a
counter, on a kiosk, on WhatsApp, and inside the office itself.

In PreVillage, Gemma is not asked to memorize Nepal's government. Facts live in
sources. Gemma is used where a small open model is valuable: repairing noisy
Nepali or Roman-Nepali transcripts, planning the user's case, deciding when to
ask follow-up, composing from retrieved evidence, and turning the final answer
into something a person can hear.

Gemma 4 E2B is the edge target. On a Raspberry Pi 5, a quantized Gemma E2B runs
through llama.cpp at roughly 6-8 generated tokens per second in our smoke test.
That does not mean a Pi runs the full national RAG stack. It means an office
does not need an L40 GPU to have a local intelligence layer. A helpdesk PC can
host the fuller RAG, voice, WhatsApp, and admin loop; the Pi proves the
low-cost edge lane.

## Architecture

The evidence layer starts with a source registry of Nepal government websites.
The crawler fetches HTML and PDFs, handles broken government websites and legacy
Nepali text where possible, extracts readable text, chunks documents, and syncs
SQLite/FTS retrieval. Health audits look for pages that were fetched but not
searchable, duplicate URLs, zero-text documents, missing extracted files, and
stale sources.

The current indexed corpus snapshot used for the demo path is 1,071 sources,
46,051 live documents, and 272,718 searchable chunks after focused MoHA, DAO,
embassy, and transport-office crawling.

This is also where "self-healing" lives. The model does not magically repair
knowledge gaps. The system repairs evidence paths: source discovery finds new
official offices, crawls add missing pages, health audits catch empty or
duplicate documents, and planner gaps become source/interview tasks. If a
website has a contact page but no service checklist, that is a different gap
than a missing local room number, and the system should record it differently.

Retrieval is question-dependent. Contact questions prefer office contact pages,
staff pages, information officers, and verified interviews. Legal eligibility
prefers Acts, Rules, and official circulars. Local routing prefers DAO,
municipality, ward, and practical counter notes. Forms and current fees prefer
dated official pages.

Official sources remain legal authority. Human sources are practical authority:
interviewed officers, staff, and verified citizens can explain which room,
which counter, which document people forget, and what changed before the website
did. Those notes are reviewed, named, dated, and treated as practical evidence,
not law.

In the Jiri path, that means the system can use official contact pages for
roles such as mayor, chief administrative officer, and information officer,
while keeping reviewed interview notes as practical source material. A named
officer such as Man Bahadur Jirel should appear only through an official source
or consent-cleared interview record, not as model memory.

## Engineering Arc

We did not get here by assuming a model would fix the problem.

The first instinct was training-first. That failed. CPT on an instruction-tuned
model regressed because raw Nepali text swamped chat behavior. It hurt
benchmark scores and introduced Roman-Nepali loops. Narrow SFT improved some
behaviors, but it was still too weak as a factual helpdesk: it invented facts,
over-answered ambiguous cases, refused answerable questions, or spoke the wrong
language.

That failure changed the architecture. SFT should teach behavior around
evidence, not memorize government facts. The durable system became
resolver-first RAG: plan the case, route the source class, retrieve evidence,
then compose from source IDs only.

The deployed public path moved back to deterministic pipeline control after
unsafe adapters. The service navigator planner emits service, action, case
type, location, missing slots, source classes, expected domains, retrieval
query, and gaps. On the hardened demo path, our planner/service/RAG audits
passed the critical smoke set with no bad citations or looping in the tested
cases.

We still keep SFT, but with a narrower job. The promising direction is not a
naked factual chatbot; it is planner/composer distillation over provided
sources. The model should learn how to ask, cite, refuse, and preserve language,
while the crawler and retrieval layer keep the facts fresh.

This matters because a government helpdesk that guesses is worse than no
helpdesk. PreVillage must say "I found this source," "I need your ward," or "I
do not have a current practical note from that office" instead of pretending.

## Voice and Access

Nepal was never voice-poor. The internet UX was not built for us.

PreVillage includes a Nepali speech path because public-service help often
starts by asking someone, calling someone, or sending a WhatsApp voice note.
The voice layer uses Nepali ASR, Gemma transcript repair, grounded retrieval,
and Nepali TTS. The raw ASR transcript stays visible in kiosk/debug mode so
mistakes are not hidden; Gemma repairs spacing, script noise, and common WER
artifacts before service routing.

The speech work came from failure, not polish. Scratch FastConformer ASR
collapsed on our low-resource setup even when the pipeline could overfit a tiny
diagnostic set, so the more defensible path became Hindi/Indic-pretrained ASR
plus Gemma repair and confirmation. TTS had the opposite trap: validation loss
looked useful, but listening exposed punctuation, rhythm, intonation, and
pronunciation failures. That is why NepTTS-Bench uses human Nepali ratings, not
only training curves.

The TTS work is public through Ampixa's Real Nepali Piper/VITS checkpoints and
Space, including `ampixa/real-nepali-v0.2-kala`,
`ampixa/real-nepali-v0.4`, and `ampixa/real-nepali-tts`. We also built
NepTTS-Bench, a public Nepali TTS benchmark with human MOS ratings from 164+
native Nepali speakers and 5,760+ ratings. The ASR checkpoint is being released
publicly for this submission, with a demo Space at
`voidash/nepali-fastconformer-demo`.

## What Is Real Today

PreVillage has a working FastAPI backend, planner-first retrieval path,
frontend chat/kiosk surfaces, a real Baileys WhatsApp bridge, local ASR/TTS
workers, crawler/source registry tooling, corpus health audits, and an
interview/admin path for reviewed practical knowledge.

The Jiri Municipality work is the clearest field proof. We tested questions
about local contacts, mayor/helpdesk information, vital registration, and
citizenship routing, then hardened the resolver when English, Nepali, and
Roman-Nepali behaved differently.

The human-source loop is also real product surface: an interview form collects
practical knowledge, an admin review screen approves it, and the retrieval
server reloads approved tacit claims with provenance, role, confidence, and
source type.

The WhatsApp and kiosk paths are not mock chat screens. The WhatsApp bridge uses
Baileys. The kiosk path shows microphone input, raw transcript, fixed question,
streamed answer, source cards, and optional TTS playback. These interfaces are
important because a real public-service tool should meet people where they
already ask for help, not force every citizen into a perfect browser form.

The system is not finished. It does not cover every service in Nepal. Some
offices have poor websites. Some practical counter knowledge still requires
interviews. Some ASR errors still need confirmation. But the shape is real: a
source-maintained, voice-capable, local-deployable service navigator that asks
before answering and cites before advising.

I used privilege to find the path. PreVillage exists so the next person does
not need privilege to use their own government.

## Final Submission Placeholders

- Replace ASR wording with final public HF model URL.
- Add public GitHub repo link.
- Add live demo link.
- Add YouTube video link.
- Decide whether to update NepTTS-Bench public card to 207/7,003 before using
  newer numbers.
