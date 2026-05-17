# SpeakGov service navigator modus operandi

Snapshot: 2026-05-11. This is the product contract for future sessions. Read
this before changing RAG, SFT, frontend chat behavior, evals, or source
ranking.

## Product identity

SpeakGov is not a generic RAG Q&A bot. It is a public-facing Nepal government
service navigator: case intake, routing, source-backed guidance, and contact
handoff.

The assistant must behave like a helpful human at a government helpdesk:

- understand what the person is actually trying to do;
- remember details already given in the chat;
- ask follow-up questions until the case is actionable;
- give relevant contacts and official source links even while asking follow-up;
- say what is known, what is uncertain, and what source supports each claim;
- use named human practical sources when available;
- avoid generic AI filler and avoid over-answering an ambiguous case.

## Core conversation rule

Every user query first goes through intake. Do not feed the raw user query
directly into RAG as the only interpretation.

Use a resolver pass to extract and normalize:

- service: citizenship, passport, national ID, vital registration, PAN/tax,
  driving license, police clearance, land, foreign employment, municipality
  service, embassy/consular service, etc.;
- action: apply, renew, replace/lost, correct, check status, find office,
  fee, required documents, complaint, deadline, contact person;
- location: country, province, district, municipality/rural municipality, ward,
  embassy/mission when relevant;
- person/case type when relevant: first-time, duplicate/lost, correction,
  minor/adult, through parent/mother, married migration, business vs
  individual, urgent vs normal;
- known slots from chat memory;
- missing slots that block a safe answer.

If the case is ambiguous, ask a compact checklist in plain chat. Keep asking
until the ambiguity that matters for the task is resolved. Do not turn the UI
into a form; plain chat remains the primary mode, including future ASR/TTS.

Example for a vague citizenship question:

> I can guide you, but citizenship depends on your exact case. Tell me:
> 1. Which municipality/rural municipality and ward in Sankhuwasabha?
> 2. Is this first-time citizenship, duplicate/lost, correction, or another
>    case?
> 3. Adult or minor?
>
> Meanwhile, the district-level office to check is District Administration
> Office Sankhuwasabha. I found the DAO source, but not your ward-level
> checklist yet.

## Partial answers while asking follow-up

When follow-up is needed, still provide useful non-speculative help:

- the likely office level, if known;
- relevant contacts: information officer, helpdesk/general phone, office chief,
  section officer, ward/municipality contact if relevant;
- authoritative source links already found;
- uncertainty and missing information;
- named practical notes if available and fresh enough.

Do not dump a generic procedure just because the service category is detected.
For example, "How to get citizenship in Sankhuwasabha?" should not answer with
a generic national citizenship checklist until municipality/ward and case type
are known enough.

## Missing-source escalation

When retrieval cannot support a factual answer, the assistant should not stop
at a flat refusal if a responsible office can be identified. It should:

- admit the exact source gap;
- find the likely office/contact from official sources;
- offer to route the question without sharing private citizen details;
- use the operator-reviewed WhatsApp outreach flow in
  `PROACTIVE_WHATSAPP_OUTREACH.md` for real messages;
- store any official reply as named practical guidance only after verification.

Do not auto-message officials directly from a public query failure. That path
needs user/operator consent, rate limits, and an audit trail.

## Source routing is question-dependent

Never use one fixed source hierarchy for every question. Rank source classes by
what the user is asking.

- Contact/person/phone: office contact pages, information officer pages,
  named staff pages, helpdesk/general phone, verified officer/staff interviews.
- Legal eligibility: Acts, Rules, MoHA/department circulars, official gazette or
  regulation sources.
- Documents required: service-specific citizen charter, service page, form
  instruction page, latest circular, then named practical notes for local
  variation.
- Local routing: DAO/Area Administration Office, municipality/ward pages,
  office list, embassy/mission pages when abroad.
- Current fee/deadline/notice: latest dated notice or fee table first; sort
  documents by date/freshness where the question asks about current values.
- Practical "what actually happens at counter": named officer/staff/citizen
  interviews, with role and interview date.
- Forms/downloads: provide official source links only; do not invent or
  recreate documents.

Official documents and human sources can both be authoritative for different
claims. If they conflict, say so explicitly:

> Official source says X. Officer Y, Ward Secretary, interviewed on
> 2026-04-12, reported that this office currently also asks for Z.

## Human practical sources

Human sources are first-class practical evidence when collected and reviewed.
Show names for accountability.

Display format:

> Ramesh Shrestha, Ward Secretary, interviewed 2026-04-12, verified officer
> source, 2 months old.

Confidence levels:

- `verified_officer`
- `verified_staff`
- `verified_citizen`
- `unverified_report`

Default freshness for human/practical notes: 6 months. Older notes should be
lower confidence or explicitly marked stale unless reconfirmed.

Source age/confidence should be visible, especially for human sources and
current office-practice claims.

Ingestion/publishing note: the product wants names displayed. The data pipeline
should only publish interview records approved for public use.

## Memory

The assistant must remember details from the current chat and use them in later
turns, like Codex does with context. If the user says "Khandbari-3" and later
asks "passport?", reuse the known location unless contradicted.

Implementation can use frontend session storage, backend session state, or the
frontend sending recent chat history. The product requirement is: extracted
slots from prior turns are available to the resolver.

Support "forget my details" eventually. It can clear extracted slots and/or
the visible chat; exact UX is not urgent.

## Geography and alias resolution

Build a Nepal geography resolver.

It should map and disambiguate:

- district, municipality/rural municipality, ward;
- common place names and informal local names;
- English, Nepali, and Roman Nepali;
- informal office/service terms such as CDO office, DAO, jilla prashasan,
  nagarikta banaune, ward ko sifaris, nagarik app, helpdesk, sifaris.

If the user gives only a district and the municipality/ward matters, give
district-level contact/source and ask for municipality/ward.

If the user gives a place name that could map to multiple locations, ask for
confirmation.

## Off-domain behavior

Do not hard-refuse harmless off-domain questions.

Example:

> 2 + 2 = 4. I am mainly built to help with Nepal government services,
> documents, offices, procedures, and contacts.

The assistant was not built for general chat, but it should be polite and light,
then steer back to its domain.

## Uncertainty and gaps

Say uncertainty plainly:

- "I found the district DAO source, but not a current ward-level checklist for
  your municipality."
- "The official source lists the general rule, but I do not have a fresh
  practical note from that office."
- "I can answer the contact part now; the document checklist depends on your
  case type."

Unresolved questions should become data tasks. Store sanitized structured data,
not raw private user text, unless explicitly needed for debugging.

Gap examples:

- `need_source`: Sankhuwasabha DAO citizenship first-time checklist
- `need_interview`: Sankhuwasabha DAO citizenship practical officer interview
- `need_contact`: Khandbari municipality ward recommendation contact
- `need_alias`: Roman-Nepali spelling variant for a service

## Universal with mini-flows

The chatbot is universal, but each service can have a mini-flow. Build a
universal schema first, then fill service-specific rules.

Recommended components:

- `query_resolver`: rewrites messy input into structured intent and normalized
  RAG query candidates.
- `case_memory`: merges current query with prior chat slots.
- `service_schema`: service/action slots, required follow-ups, source classes,
  and answer sections.
- `dialogue_planner`: decides whether to answer, ask follow-up, or answer
  partially plus ask follow-up.
- `source_router`: chooses source classes and date/freshness sorting based on
  the question.
- `response_contract`: structured answer, follow-up checklist, contacts,
  official sources, named human notes, uncertainty, gaps.
- `gap_logger`: records unresolved source/interview/alias coverage tasks.

Initial service coverage should include, at minimum:

- citizenship;
- passport;
- national ID;
- birth/death/marriage/divorce/vital registration;
- PAN/tax/VAT;
- driving license;
- police clearance;
- foreign employment/labor permit;
- land/malpot;
- municipality/ward services;
- embassy/consular services for people abroad.

## SFT policy

Do not rely on SFT alone to make these decisions. The planner, resolver,
memory, source routing, freshness handling, and gap logging must be
deterministic and inspectable.

SFT should teach style and behavior:

- ask compact follow-up checklists;
- use prior chat context;
- avoid generic unsupported answers;
- surface contacts and uncertainty;
- cite official and named practical sources correctly;
- answer harmless off-domain questions lightly and steer back.

## Session Q&A decisions captured

- Follow-up: there is always intake; keep asking until relevant ambiguity is
  resolved.
- Follow-up style: compact checklist, plain chat. This supports later ASR/TTS.
- Scope: all government procedures, not only citizenship; include embassy and
  consular services.
- Personal data: avoid sensitive identifiers. Ask municipality/ward/case type
  freely; ask sensitive details only when necessary.
- Contacts: include who to contact when available.
- Human sources: named officer/staff/verified citizen sources are important.
- Human source freshness: default 6 months.
- Source ranking: depends on the question, not a fixed hierarchy.
- UI: plain chat, not a form or button-first flow.
- Memory: must remember details from chat context.
- Resolver: refine/normalize the user question before RAG.
- Forms: provide source links, not recreated documents.
- Angry/confused users: simplify, step down to clearer checklist, and provide
  contacts.
- Feedback/testing: collect corrected office experience and use it as reviewed
  human-source data.
- Gap handling: every missing source/unclear local practice should create a
  structured backlog item.
