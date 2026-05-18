# PreVillage SFT/RAG Evolution Cards

Use this as the compact visual ladder in the 3-minute video. The purpose is to
show real iteration without spending the whole video on model training.

## One-Line Ladder

```text
v1: grounded answers, but no refusal discipline
v2: added refusals + Roman-Nepali repair
v3: anti-template + terse answers, regressions surfaced
v4: cleaned corpus + real chunks + better trainer discipline
v5: trained successfully, failed smoke, do not deploy
v6: planner/composer split; v6.4 works behind RAG
```

## Slightly Longer Cards

### v1 - Grounded But Too Trusting

- E4B SFT taught source-backed answer style.
- URL recall was strong around 0.89.
- Major failure: refusal correctness was 0/91.
- Lesson: a public-service model must know when not to answer.

### v2 - Refusal And Roman-Nepali Repair

- Moved faster on E2B for iteration.
- Added refusal examples, translation, MC short-answer, and brief Roman-Nepali
  Q&A.
- Roman-Nepali degeneration improved to 0/10.
- Refusal improved but only to 12/91.
- Lesson: slices work, but refusal cannot be solved by examples alone.

### v3 - Anti-Template And Terse Answers

- Expanded refusal and added anti-template examples.
- Grounded chrF recovered from 13.42 to 18.03.
- Refusal improved to about 18%.
- Regression: Roman-Nepali degeneration returned, GSM8K dropped.
- Lesson: every new behavior can contaminate another behavior.

### v4 - Corpus And Training Discipline

- Cleaned mojibake-contaminated government chunks.
- Rebuilt anti-template rows using real retrieved chunks instead of fake URLs.
- Dropped suspect open-ended terse rows.
- Fixed trainer checkpoint handling and environment pinning.
- Lesson: model quality depends on source quality and eval discipline.

### v5 - Beautiful Loss, Bad Product

- E4B adapter trained on L40S and reached very low validation loss.
- Smoke tests still showed hallucinated contacts, generic procedures, wrong
  routing, and missing follow-ups.
- Decision: do not deploy v5.
- Lesson: loss can reward surface form while product behavior fails.

### v6 - Planner/Composer Split

- Changed target from answer-only SFT to planner/composer behavior over source
  context.
- Added answerability, source routing, citations, compact follow-ups, and gap
  handling.
- v6.3 failed by mixing too much refusal/follow-up into the final composer.
- v6.4 split tasks: planner JSON, answerability JSON, final composer.
- Quick48 result: URL recall 0.94, wrong refusals 4.2%, Roman-Nepali loops 0/10.
- Real pipeline smokes passed behind RAG, but the adapter is not trustworthy as
  a naked factual chatbot.

## Video Caption

```text
The model should not memorize the government.
It should plan, ask, retrieve, cite, and stop.
```

## Honest Caveat

Do not claim the SFT adapter is the deployed public answer path unless we
explicitly switch it. The current safe story is stronger:

```text
PreVillage is the system.
Gemma is the open model inside the system.
RAG, resolver, source routing, evals, and human review keep it honest.
```
