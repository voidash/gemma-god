# Agent instructions for gemma-god

Before changing the helpdesk behavior, RAG, source ranking, SFT data, evals, or
frontend chat UX, read:

- `SERVICE_NAVIGATOR_MODUS_OPERANDI.md`
- `CLAUDE.md`
- `RAG_HARDENING_STATUS.md`
- `SFT_V5_POSTMORTEM_AND_NEXT_PASS.md`

The most important current product rule is:

> SpeakGov is a government-service navigator, not a generic RAG Q&A bot. Do
> resolver/intake first, ask compact follow-ups when the case is ambiguous,
> remember chat details, route sources by the user's question, include contacts
> and uncertainty, and use named human practical sources when available.

Do not implement one-off service patches when a resolver/planner/source-router
change would solve the class of problem.

Current SFT warning:

> The 2026-05-13 v5 E4B adapter trained successfully but failed smoke testing.
> Do not deploy it. Future SFT should train planner/composer behavior over
> provided source context, not government fact memorization.
