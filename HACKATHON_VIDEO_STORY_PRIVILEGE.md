# Gemma for Good video story: privilege as responsibility

Deadline: 2026-05-19 05:44 NPT.

Working constraint: three-minute video. The story has to carry the human reason,
the technical work, and the deployment vision without becoming a feature list.

## Working name

Public/video name: **PreVillage**.

Internal/repo product-contract name: SpeakGov. Use SpeakGov only when referring
to the existing codebase and service-navigator contract. For the hackathon
story, PreVillage is stronger because it holds the "privilege" idea without
sounding like a generic government chatbot.

Why PreVillage works:

- It sounds like privilege when spoken quickly.
- It suggests "before the village was served by digital UX."
- It points toward rural and municipal deployment, not only federal websites.
- It carries the idea that the system should arrive before middlemen become the
  only route.

Possible tagline:

> PreVillage: public-service knowledge before privilege.

## One-line thesis

PreVillage exists because Nepal's public-service knowledge is public in theory but
privileged in practice. The goal is to turn that privilege into a shared map:
official sources, practical office knowledge, voice access, and a local Gemma
helpdesk that can run inside the office itself.

## The word: privilege

Use privilege as the spine, but not as guilt theater.

Meaning:

- Privilege is having enough money to lose Rs. 7-8k and still keep pushing.
- Privilege is having AWS access, an L40S GPU, and the technical literacy to
  train and test models instead of giving up.
- Privilege is being able to travel 180 km to Jiri, pitch a municipality, speak
  to a mayor/CDO/information officer, and ask for the unwritten process.
- Privilege is having family support: sisters helping create voice data for a
  Nepali TTS model.
- Privilege is curiosity plus hunger plus enough safety to keep going after a
  bad office experience.

Video position:

> I cannot pretend I am the average citizen in that queue. I had the privilege
> to fight the system, study it, scrape it, train on it, and travel to ask
> questions. The work is to make that privilege useless: so the next person does
> not need it.

## Wordplay bank

Use these sparingly. They are hooks, not the whole story.

### Privilege

The real word. The unfair starting advantage.

Line:

> Privilege is when you can lose three weeks and Rs. 8,000 and still call it
> research.

### Pre-village

Before the village gets digital infrastructure. Before a rural office has a
usable service layer. Also the idea that Nepal's internet UX was not designed
for the village first.

Line:

> Nepal was online before the village was actually served.

### Pre-will-age

Before public will becomes public infrastructure. The will exists: people want
to help, officers know the answers, citizens share stories. The system has not
aged into a usable public memory.

Line:

> The will is there. The public memory is not.

### "Previ lays"

Chicken-laying-egg pun. This is playful but risky. It can work as a visual
transition: privilege lays the first egg, but the product should hatch into a
common-good system.

Line:

> If privilege laid the first egg, the question is what hatches from it.

Stronger infrastructure version:

> PreVillage is what privilege should lay: public infrastructure.

Visual version:

- A chicken lays an egg.
- The egg is labeled "privilege": GPU access, travel, technical knowledge,
  family voice help, time to keep fighting.
- It cracks into a simple infrastructure stack: crawler, RAG, ASR, TTS,
  WhatsApp, kiosk, human contact officer.
- The joke lands quickly, then the video moves back to the serious point.

Recommendation: do not use this in voiceover unless the tone becomes too heavy.
It may work as a notebook scribble or quick visual in the edit.

## Origin scene

Source: Reddit post supplied by Ashish, r/Nepal, 28 days before 2026-05-17:
"3 weeks 4 office and 4 times i filled the same form then 8k to middlemen.
Sarkari office sucks so share your stories"

Linked source:
https://www.reddit.com/r/Nepal/comments/1soq72i/comment/oguwteb/

Note: Reddit blocked unauthenticated tool access from this environment. The
story below is based on the pasted Reddit content in this working session.

Compact origin summary:

- Company registration looked digital and user-friendly at first.
- Real completion still required knowing lawyers, signatures, office behavior,
  and middlemen.
- PAN registration became worse: OCR gave a PAN reference, IRD allowed selecting
  any office, but Tripureshwor said the OCR submission was invalid and Kirtipur
  was outside its jurisdiction.
- Kalimati then said it no longer handled Kirtipur.
- Kalanki finally accepted the PAN registration after the fourth form.
- The missing information was not the law; it was the route.

Anchor quote from the post:

> "You're not paying for a service, you're paying for information and processes
> they have carefully designed to be hard for individuals to carry out."

Another anchor:

> "Nepal runs on tribal tacit knowledge."

Impact line:

> This was not a hard government process. It was an invisible flowchart.

## The real gap

The gap is not "Nepal needs a chatbot."

The gap is:

- Which office handles my exact case?
- Which room do I go to first?
- What documents are officially required?
- What documents are actually asked for?
- What changed recently but is not on the website yet?
- Who can I contact when the website is silent?
- What should the system do when it does not know?

PreVillage should be described as a service navigator:

- intake before answer;
- compact follow-up questions;
- memory of what the citizen already said;
- source routing by question type;
- official sources plus named practical/human sources;
- contacts and uncertainty;
- honest refusal instead of confident guesses.

## What has been built

Use concrete work, not vague AI language.

- Scraped and organized a Nepal government source registry.
- Built a Rust crawler and self-healing crawl/repair architecture.
- Handles broken government websites, PDFs, old Nepali fonts like Preeti, and
  scanned documents.
- Built a RAG backend over official sources.
- Added resolver/planner behavior so the system asks before answering when a
  case is ambiguous.
- Added eval gates and smoke tests because an unsafe helpdesk is worse than no
  helpdesk.
- Trained and rejected unsafe SFT runs instead of pretending they worked.
- Built a promising v6.4 RAG-backed composer candidate, with the caveat that it
  must stay behind resolver/RAG.
- Built an interview capture/admin path for human practical knowledge.
- Traveled 180 km to Jiri, pitched the idea, and collected interviews.
- Trained Nepali speech pieces: ASR and TTS, including sister voice help for TTS.
- Built public Nepali TTS artifacts and a Nepali TTS benchmark under Ampixa.

## What still needs v0 for the video

Build only the demoable thread:

1. Web speaking/listening interface.
2. User speaks Nepali/Roman-Nepali/code-mixed.
3. ASR transcribes.
4. Gemma fixer repairs likely WER/script issues without changing intent.
5. Service resolver/planner extracts service, action, location, and missing
   slots.
6. RAG retrieves official and tacit sources.
7. Composer answers with citations, contacts, and uncertainty.
8. Gemma/TTS preprocessor makes the answer speakable.
9. TTS replies in a natural Nepali voice.
10. If sources are missing, the system logs a gap and can route a WhatsApp
    message to the relevant contact officer.

This does not need to be fully autonomous for the video. It needs to be honest:
live kiosk voice path plus mocked or semi-working WhatsApp outreach is better
than pretending the Hermes/Baileys agent is complete.

## WhatsApp, kiosk, web: one interface family

Why this matters in Nepal:

- WhatsApp is already a citizen/officer communication layer.
- Reels and short video already shape political understanding; the internet UX
  people actually use is speech, video, and chat, not government portals.
- Voice has always been the interface in Nepal: ask someone, call someone, go to
  a room, ask again.

Product framing:

> PreVillage does not ask Nepal to become a form-first internet country. It brings
> the helpdesk to the interfaces people already use: voice, WhatsApp, kiosk, and
> web.

Deployment framing:

- Web for anyone with a browser.
- Kiosk for office visitors.
- WhatsApp for citizens and contact officers.
- Local model path for offices that want low recurring cost and data control.

## Three-minute video shape

### 0:00-0:20 - Cold open: invisible flowchart

Visuals:

- Government office exterior or road footage.
- Quick flashes: same form, office doors, counters/rooms.
- Reddit screenshot or reconstructed text fragments.

Voiceover:

> Three weeks. Four offices. Four versions of the same form. Almost eight
> thousand rupees to middlemen. Not because the process was impossible, but
> because the real route was never written down.

### 0:20-0:45 - Privilege confession

Visuals:

- You at laptop/training screen.
- AWS/L40S/training logs.
- Travel footage.

Voiceover:

> I had the privilege to keep going. I could pay, read, code, scrape, train
> models, and travel 180 kilometers to ask a municipality how the office really
> works. Most people only get one thing: another queue.

### 0:45-1:15 - The diagnosis

Visuals:

- Map/registry/crawler screens.
- Old PDF/Preeti/scanned document examples.
- Source cards/citations.

Voiceover:

> The websites exist. The PDFs exist. The phone numbers exist. But the path does
> not. Nepal's service layer is scattered across official documents, broken
> pages, old fonts, and human memory.

### 1:15-1:45 - What PreVillage is

Visuals:

- Chat demo with a vague question.
- Follow-up checklist appears.
- Answer with contacts/sources.

Voiceover:

> PreVillage is not an answering machine. It is a service navigator. It asks what
> matters first: which office, which ward, which case. Then it answers from
> official sources and practical interviews, or says exactly what is missing.

### 1:45-2:10 - Human loop

Visuals:

- Jiri mayor/CDO/presentation shot.
- Information officer interview.
- Admin approval/interview audio UI.

Voiceover:

> In Jiri, I pitched this to the municipality and interviewed the people who know
> the real process. Their answers become practical sources: room numbers, busy
> times, documents people forget, who to call when the website is silent.

### 2:10-2:35 - Voice and WhatsApp

Visuals:

- Sister recording voice/TTS training.
- Speak into kiosk.
- WhatsApp message flow, contact officer message if source missing.

Voiceover:

> Nepal was never voice-poor. Our internet was just not built for us. So the next
> interface is voice and WhatsApp: speak the question, fix the transcript, retrieve
> the source, and hear the answer back in Nepali.

### 2:35-3:00 - The ask / ending

Visuals:

- Citizen using kiosk.
- Office PC/Raspberry Pi.
- Mountain/Jiri return shot.

Voiceover:

> The goal is simple: every office can run a low-cost local helpdesk trained on
> its own public sources and practical knowledge. I used privilege to cross the
> barrier. PreVillage is the attempt to remove it.

End card:

> PreVillage
> Government service navigation in Nepal's own interfaces.
> Gemma for Good

## Alternate compact voiceover

This is a tighter version if the edit has a lot of strong visuals:

> I built this because a simple company and PAN registration took me three
> weeks, four offices, four forms, and almost eight thousand rupees to
> middlemen. The process was not hard. The map was hidden.
>
> That is privilege. I could pay. I could keep searching. I had the technical
> knowledge, the GPU access, and the stubbornness to turn frustration into a
> system. Most people only get sent to another room.
>
> PreVillage is a government-service navigator for Nepal. It scrapes official
> `.gov.np` sources, reads PDFs and old Nepali fonts, remembers the user's case,
> asks follow-up questions before guessing, and answers with citations,
> contacts, and uncertainty.
>
> But websites are not enough. I traveled 180 kilometers to Jiri, pitched the
> municipality, and interviewed officers because the most useful knowledge is
> often human: which counter, which document, which time, which person.
>
> Now we are adding the interface Nepal already understands: voice and WhatsApp.
> A citizen speaks, Nepali ASR transcribes, Gemma fixes the noisy text, RAG finds
> the source, and Nepali TTS speaks the answer back. When the system does not
> know, it can ask the relevant contact officer instead of hallucinating.
>
> The goal is not another chatbot. It is a low-cost helpdesk each office can run
> onsite. I used privilege to find the path. PreVillage exists so the next person
> does not need privilege to use their own government.

## Shot inventory mapped to story

Existing/planned shots from Ashish:

- Jiri travel/mountain footage: use for the personal journey and remoteness.
- Presenting to mayor/CDO: use as proof this was not a toy demo.
- Interviewing information officer: use for human-source layer.
- Training screens: use for privilege/technical grind.
- Sister voice/TTS recording: use for voice layer and family/personal stake.
- Real people using system: use for final impact.
- WhatsApp outreach to contact person: use for missing-source loop.
- Kiosk demo: use as office deployment proof.

Needed additional shots:

- Close-up of speaking into browser/kiosk.
- Transcript before/after "Gemma fixer" correction.
- Source cards showing official source plus human practical source.
- TTS playback with waveform or visible audio output.
- A "missing source -> ask contact officer" screen.
- Raspberry Pi or small office PC physically next to monitor.

## Tone rules

Use:

- personal, but not self-congratulatory;
- technically credible, but not a benchmark dump;
- emotionally sharp, but not anti-government rage;
- respectful to officers: many know the answers, the system fails to preserve
  and share their knowledge;
- clear about uncertainty and unfinished parts.

Avoid:

- "AI will fix government";
- "we solved Nepal";
- pretending WhatsApp/Hermes agent is complete before v0 exists;
- saying the local adapter is safe as a naked factual chatbot;
- drowning the video in architecture diagrams.

## The strongest product claim

> A government office does not need a giant AI budget to answer the same citizen
> questions all day. It needs a local navigator that knows its sources, asks the
> right follow-up, and admits when it has to ask a human.

## Questions for Ashish

1. What exact ASR model name/artifact should we cite? Is it public, private, or
   local-only right now?
2. For the TTS story, which voice should be the demo default: one sister's
   voice, a blended speaker, or the best public `real-nepali-v0.4` speaker?
3. Do we show your face/name directly as the founder, or keep the video more
   product-first with you as narrator?
4. Can we use the Jiri mayor/CDO footage publicly, or should faces/names be
   minimized?
5. What exact question should the kiosk demo answer live?
6. What exact missing-source question should trigger WhatsApp outreach?
7. Should the video say "Rs. 7,000" from the post body or "Rs. 8,000" from the
   title/TL;DR? Pick one number for consistency.
8. Do you want the ending to ask for offices to partner, citizens to share
   stories, or judges to understand the hackathon impact?
9. Which language should the main voiceover be: English, Nepali, or mixed?
10. Do we have consent to use sister voice-recording footage/audio in the
    hackathon video?
11. Is the target deployment phrase "Raspberry Pi", "office computer", or
    "low-cost onsite box"? Raspberry Pi is memorable, but only use it if the
    demo path is credible.
12. What is the one line you want people to remember after the video?
