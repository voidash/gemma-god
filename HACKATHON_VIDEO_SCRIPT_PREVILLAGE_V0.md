# PreVillage three-minute video script v0

Deadline: 2026-05-19 05:44 NPT.

Target length: 180 seconds.

Working rule: the video cannot explain every subsystem. It should make one
viewer feel the gap, trust that the team did real work, and understand the
deployment shape: voice + WhatsApp + kiosk + web over official and human
sources.

## Core memory line

> I used privilege to find the path. PreVillage exists so the next person does
> not need privilege to use their own government.

## Structure

### 0:00-0:12 - Cold open: the hidden map

Visuals:

- Fast cuts: government-office hallway, forms, Google Maps/route, office doors,
  the Reddit title, empty phone-call screen.
- No architecture yet.

Voiceover:

> Three weeks. Four offices. Four versions of the same form. Almost eight
> thousand rupees to middlemen.
>
> The process was not impossible. The map was hidden.

On-screen text:

```text
The law was public.
The route was privileged.
```

### 0:12-0:30 - The birth of the idea

Visuals:

- Reddit post excerpt, blurred enough to avoid visual clutter.
- Highlight: "paying for information", "tribal tacit knowledge",
  Tripureshwor -> Kalimati -> Kalanki.

Voiceover:

> I wrote about it because I needed to know if it was just me. It was not.
> People were not paying for a service. They were paying for information:
> which office, which room, which form, which exception.

On-screen text:

```text
Tripureshwor -> Kalimati -> Kalanki
4 forms for one task
```

### 0:30-0:48 - Privilege confession

Visuals:

- Training logs / AWS screen / local machine / notebooks.
- Cut to road toward Jiri.

Voiceover:

> And here is the uncomfortable part: I had privilege. I could lose money and
> keep going. I could read the rules, scrape the sites, rent an L40S GPU, train
> models, and travel 180 kilometers to ask an office how it really works.
>
> Most people only get sent to another queue.

On-screen text:

```text
Privilege = the ability to keep pushing
```

### 0:48-1:05 - Previ lays / PreVillage

Visuals:

- Quick playful sketch/animation: chicken lays an egg labeled `privilege`.
- Egg cracks into boxes: `crawler`, `RAG`, `ASR`, `TTS`, `kiosk`, `WhatsApp`,
  `human source`.
- Then cut immediately to real product footage.

Voiceover:

> So the question became: what should privilege lay?
>
> Not another private shortcut. Public infrastructure.
>
> That is PreVillage.

On-screen text:

```text
PreVillage
public-service knowledge before privilege
```

### 1:05-1:27 - What we built

Visuals:

- Crawler/source registry.
- Preeti/old PDF example.
- RAG source cards.
- Eval/report screen.

Voiceover:

> PreVillage scrapes and organizes Nepal government sources. It reads PDFs,
> broken pages, old Nepali fonts, scanned documents, and local municipality
> pages.
>
> But it is not just search. It is a service navigator. It asks first, answers
> second, and refuses when the source is missing.

On-screen text:

```text
official sources + resolver + honest RAG
```

### 1:27-1:48 - Live navigator behavior

Visuals:

- Web chat/kiosk demo.
- Ask an ambiguous question like: "Sankhuwasabha ma nagarikta banauna?"
- Show compact follow-up: municipality/ward, first-time or duplicate, adult or
  minor.
- Then show a contact/source answer for a known Jiri/DAO case.

Voiceover:

> A normal chatbot guesses. PreVillage does intake. If the case is ambiguous,
> it asks the missing questions. If it knows the office or contact, it gives
> that too, with sources.

On-screen text:

```text
not an answering machine
a government-service navigator
```

### 1:48-2:10 - Human source layer from Jiri

Visuals:

- Jiri mountain/travel shot.
- Presenting to mayor/CDO.
- Interviewing information officer.
- Admin interview review screen.

Voiceover:

> Websites still miss the most useful knowledge. So I went to Jiri. I pitched
> the municipality and interviewed the people who know the real route: room
> numbers, busy times, documents people forget, and who to ask when the website
> is silent.

On-screen text:

```text
official source + human practical source
```

### 2:10-2:36 - Voice, TTS, WhatsApp, kiosk

Visuals:

- Sister voice recording / TTS training.
- User speaks into kiosk.
- Transcript appears, then "fixed" transcript.
- Answer is spoken back with TTS.
- WhatsApp demo screen from the other agent: missing info -> contact officer.

Voiceover:

> Nepal was never voice-poor. The internet UX just was not built for us.
>
> So PreVillage works where people already are: web, kiosk, and WhatsApp. A
> citizen speaks. Nepali ASR transcribes. Gemma fixes the noisy text. RAG finds
> sources. Nepali TTS speaks the answer back.
>
> If the system does not know, it can ask the relevant contact officer instead
> of hallucinating.

On-screen text:

```text
speak -> fix -> retrieve -> answer -> ask a human if missing
```

### 2:36-2:55 - Office deployment

Visuals:

- Raspberry Pi or office computer beside monitor.
- Kiosk near desk/counter.
- Citizen using system.
- WhatsApp reply on phone.

Voiceover:

> The goal is not a central chatbot that every office depends on. The goal is a
> low-cost helpdesk each office can run onsite, trained on its own sources and
> its own practical knowledge.

On-screen text:

```text
low-cost onsite helpdesk
for every office
```

### 2:55-3:00 - End card

Visuals:

- PreVillage mark/title.
- Short mountain/road shot or clean product shot.

Voiceover:

> I used privilege to find the path. PreVillage exists so the next person does
> not need it.

On-screen text:

```text
PreVillage
Gemma for Good
```

## Demo shots we need to make this credible

Must have:

- One live voice query in browser/kiosk.
- One transcript correction moment: raw ASR -> fixed user question.
- One answer with official sources.
- One answer with human practical source, if we can ingest Jiri interview data
  in time.
- One TTS playback moment.
- One WhatsApp missing-source/contact-officer demo from the other agent.
- One low-cost onsite hardware shot: Raspberry Pi if credible, otherwise
  office laptop/mini PC.

Nice to have:

- Chicken/egg Previ lays animation.
- Brief eval/report screen to prove discipline.
- Crawler/source registry screen.
- Old Nepali font/PDF conversion visual.

## Lines to keep out unless there is time

- Detailed SFT version history.
- Too many benchmark numbers.
- Full architecture diagram.
- "Self-healing crawler" details beyond one visual.
- Full Hermes/Baileys implementation claim unless it works.

## Truth and caveat lines

Use these if a judge asks or if the video needs a credibility caption:

- "The local model is used behind resolver/RAG, not as a naked factual chatbot."
- "When sources are missing, the system logs the gap and routes to a human
  contact path instead of inventing."
- "The WhatsApp outreach shown is the demo path under active implementation."
- "The voice pipeline v0 is built to prove the interaction loop first; quality
  improves as ASR/TTS are wired to the trained local models."
