# PreVillage: public-service knowledge before privilege

> Human-voice pass. Written closer to the `ashish-ways` blog style. Keep under
> 1,500 words before final Kaggle submission.

## draft

Three weeks. Four offices. Four versions of the same form. Almost eight
thousand rupees to middlemen.

That was the start.

The funny part is that the law was public. The form was public. The office
existed. But the route was not public. The route was in someone's head.

Which office first. Which ward. Which recommendation. Which counter. Which
phone number still works. Which paper gets rejected even though the website does
not say it.

That is what people were paying for. Not government service. Information about
how to use their own government.

I could keep pushing. I had technical know-how, GPU access, family support, and
enough stubbornness to travel 180 km to Jiri and ask an office how things
actually work.

Most people do not get that. They get sent to the next queue.

So the question became simple:

> what should privilege lay?

Not another private shortcut. Public infrastructure.

That is PreVillage.

## not a chatbot

PreVillage is not a generic RAG chatbot over government PDFs.

That version sounds attractive because it demos well. Ask a question, get an
answer, show sources. We tried that. It broke in boring and dangerous ways.

It answered the first question and lost the second. It pulled the wrong source.
It said it did not know when the contact was right there. It spoke Hindi to a
Nepali user. It gave confident generic AI text where a person needed a route.

That is not a helpdesk. That is a liability.

The real shape is service navigation.

First understand the case. What service? Which location? Which office? Which
document? First-time or duplicate? Ward or municipality? Adult or minor? Local
office or federal department?

Then route sources by the question. A contact question should prefer contact
pages, staff pages, information officers, and reviewed interviews. A legal
eligibility question should prefer Acts, Rules, and official circulars. A fee or
form question should prefer dated official pages. A "where do i go" question
should prefer local office routing and practical counter notes.

If something is missing, ask. Compactly.

If a source is missing, say so.

If we know who to contact, give that person or desk with the source.

## where Gemma fits

Gemma matters because this cannot just be a cloud chatbot.

Government help should work where the citizen is: at the counter, on a kiosk,
on WhatsApp, and inside the office itself.

Facts should live in sources. Gemma should not memorize Nepal's government.
That path is stale on day one.

In PreVillage, Gemma does the parts where a small open model is actually useful:
repair noisy Nepali and Roman-Nepali text, turn messy user questions into a
case plan, ask follow-ups, preserve language, and compose from cited evidence.

Gemma E2B also gives us an edge lane. On a Raspberry Pi 5, quantized Gemma E2B
ran through `llama.cpp` at roughly 6-8 generated tokens per second in our smoke
test. That does not mean a Pi runs the full national RAG plus ASR plus TTS. It
means a low-cost office machine can have a local intake/composer layer instead
of sending every interaction away.

The heavy work builds the knowledge. The office runs the helpdesk.

## the RAG had to grow up

The current demo corpus has 1,071 sources, 46,051 live documents, and 272,718
searchable chunks after focused MoHA, DAO, embassy, municipality, and transport
office crawling.

But the count is not the point.

The point is maintenance.

Government websites break. PDFs have bad text. Old Nepali fonts show up. Pages
fetch but do not become searchable. The same file appears under two URLs. A
municipality has a contact page but no service checklist. An office has a
procedure page but no room-level practical note.

So "self-healing" in PreVillage is not model magic. It is evidence-path repair.

Source discovery finds missing offices. Crawlers fetch pages and PDFs. Health
audits catch zero-text documents, duplicates, stale sources, and missing
extracts. Planner gaps become crawl tasks, contact tasks, or interview tasks.

The model should not hallucinate the missing room number. The system should
record that the room number is missing.

## people are sources too

Official sources are legal authority.

People are practical authority.

That distinction matters. An officer, staff member, or verified citizen can tell
you which room to visit, what document people forget, which time is less busy,
and which number still works. That does not make the interview law. It makes it
useful evidence.

We built the human loop for this.

There is an interview form for collecting practical notes. There is an admin
review screen. Approved claims reload into retrieval with provenance, role,
confidence, and source type.

The Jiri work is the clearest field proof. We have official-source handling for
roles like mayor, chief administrative officer, and information officer. If Man
Bahadur Jirel appears in the system, it should be because an official source or
consent-cleared interview supports it. Not because a model remembered a name.

That is the contract.

## voice is not garnish

Nepal was never voice-poor. The internet UX was not built for us.

People ask clerks. They call relatives. They send WhatsApp voice notes. They do
not start by reading a 38-page PDF.

So PreVillage has a speech path:

```text
citizen speaks
  -> ASR transcript
  -> Gemma transcript repair
  -> service resolver
  -> source router
  -> official + practical retrieval
  -> grounded answer
  -> Nepali TTS if useful
```

This work had its own scars.

Scratch FastConformer ASR collapsed on our low-resource setup, even though the
pipeline could overfit a tiny diagnostic set. That pushed us toward
Hindi/Indic-pretrained ASR plus Gemma repair and confirmation.

TTS had the opposite trap. Validation loss looked like progress. Listening said
otherwise. Punctuation failed. Rhythm failed. Intonation failed. Some words were
unstable. That is why we built NepTTS-Bench with human Nepali ratings instead
of trusting curves.

The public voice artifacts are part of the proof: Real Nepali TTS checkpoints,
the TTS Space, NepTTS-Bench, and the Nepali FastConformer demo Space.

## training was useful because it failed

We did CPT and SFT passes because it was tempting to believe a better adapter
would fix the helpdesk.

It did not.

CPT on instruction-tuned Gemma damaged chat behavior. Narrow SFT improved some
examples but still failed as a factual service bot. It invented. It refused. It
looped. It overfit refusal shape. It did not become a good multi-turn
government navigator just because we showed it answers.

That failure was useful.

It told us the model should not be the database. SFT should teach planner and
composer behavior around provided evidence. Ask. Cite. Preserve language.
Refuse when unsupported. Remember chat details. Do not turn Nepali into Hindi.

The durable architecture became planner-first RAG.

## what is real today

PreVillage has a FastAPI backend, resolver-first retrieval path, web chat,
kiosk surface, Baileys WhatsApp bridge, local ASR/TTS workers, crawler/source
registry tooling, corpus health audits, and interview/admin review path.

The video material is real too: Jiri road footage, office pitch, Man Bahadur
Jirel UX quote, desk/interview footage, source crawling tmux, training logs,
TTS/G2P evaluation, kiosk, WhatsApp, and Pi local Gemma E2B.

It is not finished.

Coverage is uneven. Some offices have terrible websites. Some answers still
need better local practical notes. ASR still needs confirmation when it is
uncertain. SFT is not the hero yet.

But the shape is right now.

Not "ask AI about government."

Ask a service navigator that knows when to ask, where to look, who to contact,
and when to say it does not know.

I used privilege to find the path. PreVillage exists so the next person does
not need privilege to use their own government.
