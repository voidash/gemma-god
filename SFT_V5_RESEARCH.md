# SFT v5 research note - RAG composer pass

Snapshot: 2026-05-08.

This note is deliberately about the composer SFT, not retrieval coverage. The
current read is: retrieval is becoming acceptable, but the adapter is still
cheap behavior training. It mostly learned surface habits: cite, refuse phrase,
same-language answer. It has not reliably learned the RAG decision process:
which sources matter, whether the question is answerable, which claims are
supported, what is missing, and how to continue a multi-turn service workflow.

## Honest critique

1. The current SFT is still too final-answer-shaped.
   v4b has some retrieval-realistic grounded records, but most supervision is
   still "question plus snippets -> final answer." The hard internal labels are
   hidden. When the model fails, we cannot tell if it missed source selection,
   answerability, citation mapping, language control, or the final wording.

2. The refusal data teaches phrasing more than the boundary.
   `refusal_distilled` examples often have no candidate sources. That teaches a
   refusal sentence, but it does not teach the real production case: sources are
   present but only partially relevant, misleading, stale, same agency but wrong
   service, or answer one clause of a multi-clause question.

3. The training target still uses raw URLs too much.
   Production should cite stable source IDs and let the UI map IDs to URLs. Raw
   URL citation in the generated text makes the model responsible for a UI/data
   problem and encourages ugly, brittle citation behavior.

4. We have too little multi-turn supervision.
   The product is a helpdesk. Users ask a bad first query, clarify, switch
   language/script, ask "what about Jiri", then ask "who do I call". The SFT
   mostly sees single-turn prompts. So the model has no trained habit of using
   conversation context without hallucinating.

5. The adapter is being asked to do deterministic work.
   Exact phone numbers, mayor names, fees, office holders, URLs, and dates should
   be extractive or template-assisted where confidence is high. SFT can polish
   the answer, but should not be the source of truth for exact values.

6. The eval set is too small and too constructed for the product.
   We have useful gold checks, but the next pass needs query-demand eval:
   real-looking citizen phrasing, spelling variants, fused Devanagari, Roman
   Nepali, ambiguous local-service questions, and multi-turn clarifications.

7. E2B is probably enough for the task if the task is made explicit.
   The failures do not prove "small model cannot do RAG." They show we trained a
   small model on a compressed target that hides the decisions. Smaller models
   need clearer intermediate supervision, not just more final answers.

## Research-backed implications

- RAFT trains for open-book domain QA with retrieved documents, including
  distractor documents the model must ignore, and emphasizes evidence from the
  right document. That maps directly to our "same municipality but wrong page"
  and "sources contain A but user asks A+B" failures.
  Source: https://arxiv.org/abs/2403.10131

- Self-RAG's useful lesson is not that we must copy its special tokens. The
  lesson is that retrieval use, passage relevance, and generation critique are
  explicit training targets. Our v5 contract should expose answerability,
  relevant source IDs, atomic facts, and missing details.
  Source: https://arxiv.org/abs/2310.11511

- RAGAS separates retrieval quality from generation faithfulness and answer
  quality. That is the right eval shape for us: do not judge the adapter as one
  opaque score. Track context recall, context precision, faithfulness, answer
  correctness, and refusal boundary separately.
  Source: https://arxiv.org/abs/2309.15217

- ALCE evaluates citation-backed generation on correctness, fluency, and
  citation quality. The main implication for us is sentence/claim-level
  attribution, not just "some correct URL appears somewhere."
  Source: https://arxiv.org/abs/2305.14627

- LIMA is a useful warning: quality and diversity can beat scale for alignment.
  Our next pass should not be "generate 50k cheap refusals." It should be a
  smaller, audited set of high-information RAG cases.
  Source: https://arxiv.org/abs/2305.11206

## v5 data design

Use the existing `scripts/distill_rag_contract_v5.py` direction, but scale it
properly and tighten validation.

Target first serious pass: 8k to 12k teacher-approved records, not 50k.

Recommended mix:

| Slice | Count | Purpose |
|---|---:|---|
| live retrieval answer | 3,000 | normal answerable service questions with real retrieved sources |
| live retrieval partial | 1,500 | multi-clause or underspecified questions where only part is supported |
| live retrieval refuse | 1,500 | realistic negative cases with distractor sources present |
| local government exact facts | 1,000 | phone, mayor/chair, ward office, contact person, notice dates, fees |
| multi-turn service flows | 1,000 | clarify, follow-up, language switch, location carryover |
| Roman/code-mixed variants | 1,000 | same workflows in Roman Nepali and mixed English/Nepali |
| general replay | 1,000 to 1,500 | English/Nepali instruction, MC, math/reasoning anchors |

Important: generate from live `/retrieve`, not from random chunks alone. Include
the actual ranked source list, retrieval quality metadata, source labels, and
distractors. Keep source IDs as `S1`, `S2`, etc. Do not train final answers to
emit raw URLs.

Each distilled record should store:

- `answerability`: `answer`, `partial`, `refuse`, or `off_domain`
- `relevant_source_ids`
- `facts`: atomic claim plus supporting source IDs
- `missing`: unsupported details the user asked for
- `answer`: final user-facing answer with `[S#]` citations
- `failure_bucket` when teacher refuses or marks partial
- `question_lang` and `service_topic`

Training format should include two task types:

- Answer task: production prompt -> final concise answer.
- Contract task: explicit JSON prompt -> answerability/source/fact contract.

This is already started in `scripts/format_sft_v5.py`. Keep the JSON task
separate so production chat does not start emitting JSON unless asked.

## Teacher and filtering

Use Claude/Sonnet through Meridian for the first 500 to 1,000 examples because
we need high-quality labels while designing the rubric. Use DeepSeek only after
the validator and reviewer show the same failure distribution.

Filtering rules before a record enters train:

- all answer citations must reference valid `S#` IDs;
- every nontrivial factual claim must map to at least one fact entry;
- answer language must match the user language/script;
- no raw URL citations in the answer text;
- no answer if `answerability=refuse`, except a concise refusal plus next step;
- if `answerability=off_domain`, the answer may be an uncited brief answer plus
  a scope note that SpeakGov is primarily for Nepal government services;
- if `answerability=partial`, answer must include both supported facts and the
  specific missing item;
- reject loops, generic identity text, and agency identity drift.

Add a small human review gate: 200 records per slice, then sample 5 percent from
each batch. If more than 3 percent are bad, fix the teacher prompt/validator
before scaling.

## Evaluation gates

Do not select a checkpoint by val loss alone. Select by behavior:

1. Retrieval-aware full gold:
   - answerable wrongly refused <= 5 percent
   - refusal correct >= 80 percent when distractor sources are present
   - partial-answer correct >= 70 percent

2. Citation and faithfulness:
   - source-ID citation precision >= 95 percent
   - unsupported claim rate <= 5 percent by judge/sample audit
   - no raw URL citation in generated text

3. Product smoke:
   - Jiri phone/contact/mayor/birth registration
   - police clearance
   - passport renewal and fees
   - driving license
   - lost citizenship duplicate
   - PAN/VAT
   - vital registration

4. Multi-turn:
   - location carryover works
   - clarification answer does not ignore previous user intent
   - language switch does not erase the task

5. Regression:
   - Roman Nepali loops <= 1/20
   - GSM8K/English replay does not collapse
   - Belebele/Nepali MC does not fall below current baseline by more than 2 pts

## Next implementation steps

1. Finish the current government-site crawl and rebuild FTS.
2. Build a query-demand seed set from common citizen intents, not from chunk
   availability. Include local-government examples from the expanded source
   registry.
3. Run v5 contract distillation on 500 records with Claude/Sonnet.
4. Review and bucket failures. Patch validator, not individual answer examples.
5. Scale to 8k to 12k only after the 500-record audit is clean.
6. Train short checkpoint sweep on E2B first: step 200, 400, 600, 800, 1000.
7. Select by the behavior gates above, then only try E4B if E2B cannot meet the
   gates with clean data.

## Bottom line

The next pass should not be a bigger v4. It should be a different supervision
shape. Train the model to perform the RAG contract explicitly, with realistic
distractors and partial-answer cases, and keep exact facts and citations as
source-ID-grounded operations. The problem is not "more SFT"; it is "more
visible decisions per SFT example."

## 2026-05-11 execution note

The first v5 seed artifacts now exist:

- `eval/service_coverage_matrix.md` - service-by-service coverage and risk
  matrix.
- `eval/service_eval_expanded_v5_seed.jsonl` - query-demand seed set for
  expanded evals and v5 Meridian/Anthropic distillation.

The v5 distiller now passes `history` through `/retrieve` and includes recent
conversation turns in the teacher prompt, so records with real back-and-forth
can produce source-selection and answerability labels instead of being flattened
into single-turn prompts.

The distiller validator also checks expected-domain drift for seeded examples.
This matters because the first 5-record Meridian pilot produced valid JSON but
used Jiri sources in a Sankhuwasabha citizenship answer when retrieval surfaced
them. That kind of record must be flagged as bad supervision before scaling.

Use this first-pass command for a small teacher audit, not full-scale training:

```bash
python3 scripts/distill_rag_contract_v5.py \
  --base-url https://helpdesk.ampixa.com \
  --questions eval/service_eval_expanded_v5_seed.jsonl \
  --provider meridian \
  --model claude-sonnet-4-6 \
  --limit 25 \
  --out corpora/sft_v5_rag_contract_seed25_meridian.jsonl
```

Review those 25 records manually before scaling. If more than a couple of
records have bad source selection, wrong answerability, missing follow-up
questions, or raw URL citation behavior, patch the teacher prompt/validator
before generating more.

Initial 5-record Meridian smoke:

```text
corpora/sft_v5_rag_contract_pilot5_meridian.jsonl
errors: 0/5
validation issues: 0/5
```

Manual read found a bad-but-valid record: the teacher used Jiri sources for a
Sankhuwasabha citizenship question because retrieval surfaced them. After adding
expected-domain validation and location-strict teacher instructions:

```text
corpora/sft_v5_rag_contract_pilot5_meridian_v2.jsonl
errors: 0/5
validation issues: 1/5
flagged: foreign_employment_labor_permit_en
reason: retrieval surfaced FEB sources when the seed expected DoFE/FEIMS for a
labor-permit procedure.
```

This is the desired behavior for the pipeline: valid JSON is not enough; records
with wrong source class or wrong locality must be rejected before SFT. Formatting
the v2 pilot produced 8 trainer rows from the 4 valid contracts:

```text
corpora/sft_v5_pilot5_train.jsonl
corpora/sft_v5_pilot5_val.jsonl
```

## 2026-05-11 MoHA crawl + pilot25 result

After parsing the official MoHA office directory and crawling 31 priority
DAO/Area/Border Administration Office sources, the 25-record v5 pilot was run
twice with Haiku through Meridian.

Before the ranker fixes:

```text
corpora/sft_v5_rag_contract_pilot25_haiku_20260511.jsonl
errors: 0/25
validation issues: 3/25
```

Important warning types:

- `citizenship_khandbari_first_time_history`: wrong locality/source class; Jiri
  tacit claims and Khandbari municipality evidence appeared where DAO/MoHA
  evidence was expected.
- `foreign_employment_labor_permit_en`: labor permit routed to FEB instead of
  DOFE/FEIMS.
- `driving_license_province_followup_en`: answer made a missing-office claim
  without a source reference.

After deploying the source-ranking fixes:

```text
corpora/sft_v5_rag_contract_pilot25_haiku_rerank_20260511.jsonl
errors: 0/25
validation issues: 3/25
answerability: answer=6, partial=11, refuse=8

corpora/sft_v5_pilot25_haiku_rerank_train.jsonl
corpora/sft_v5_pilot25_haiku_rerank_val.jsonl
formatted records: 44
```

The original source-drift failures are fixed:

- `citizenship_khandbari_first_time_history` now passes and retrieves DAO
  Sankhuwasabha as the top official source.
- `foreign_employment_labor_permit_en` now passes and retrieves DOFE sources.
- `foreign_employment_welfare_claim_ne` remains on FEB/DOFE and no longer gets
  misclassified as vital registration just because the query mentions death.

The remaining 3 warnings are acceptable blockers before scaling, not reasons to
throw away the v5 design:

- passport lost abroad needs embassy/MoFA mission sources;
- police-clearance wrong-agency needs a cleaner source-backed negative answer;
- Pokhara driving-license location needs province/transport-office source
  coverage.

Next v5 step: do not scale directly to 8k yet. Add the missing source coverage
for embassy/mission contacts and provincial transport offices, tighten the
teacher rule for citing unsupported/missing details, then run a 100-record pilot.
If warning rate stays under 5 percent and no wrong-domain records pass the
validator, scale to 500 for human sampling.

### Coverage follow-up

The immediate coverage gaps were addressed:

- added and crawled `qa_nepalembassy_gov_np` for Embassy of Nepal, Doha:
  +28 docs / +26 chunks;
- added and crawled `tmolkaski_gandaki_gov_np` for the Kaski/Pokhara driving
  license office: +72 docs / +332 chunks;
- added query-dependent authority routing for Qatar/passport-abroad and
  Pokhara/Kaski driving-license questions;
- added an explicit `consular` retrieval topic so local municipality tacit
  snippets do not leak into consular-attestation prompts.

The best pilot artifact after this pass is:

```text
corpora/sft_v5_rag_contract_pilot25_haiku_coverage_revalidated_20260511.jsonl
errors: 0/25
validation issues: 0/25
answerability: answer=6, partial=9, refuse=10

corpora/sft_v5_pilot25_haiku_coverage_train.jsonl
corpora/sft_v5_pilot25_haiku_coverage_val.jsonl
formatted records: 50
```

Use this as the current clean v5 pilot. A later rerun produced fresh
`answer_missing_source_ref` warnings from teacher variability, so the practical
rule is: keep the deterministic validator, prefer the clean validated artifact,
and use a larger pilot only after the source set is stable.

## 2026-05-11 pilot100 result

Built a 100-record v5 pilot seed:

- `eval/service_eval_expanded_v5_seed.jsonl`: 70 hand-authored coverage rows;
- `eval/citizen_query_demand_seed.jsonl`: normalized demand-derived top-up;
- `scripts/build_v5_pilot100.py`: builds
  `eval/service_eval_v5_pilot100.jsonl` with 30 top-up rows across passport,
  citizenship/NID, driving license, land, PAN/VAT, police, birth registration,
  company registration, and foreign employment.

Important seed rule: raw social snippets are kept as metadata only. The actual
SFT questions are normalized service questions, because the raw demand file
contains comments, rants, and article excerpts that are useful for demand mining
but too noisy for training inputs.

Initial 100-record Haiku run:

```text
corpora/sft_v5_rag_contract_pilot100_haiku_20260511.jsonl
errors: 0/100
validation issues: 11/100
```

The warnings were useful:

- embassy/passport expected-domain validation was too narrow;
- combined citations like `[S1, S5]` needed validator support or teacher
  repair;
- Roman-Nepali rows sometimes came back in Devanagari;
- "manpower agency cheated me" did not route to foreign-employment sources;
- the navigator picked citizenship for a mixed "driving license form ...
  citizenship number" query because service detection returned the first alias
  match rather than the strongest match.

Fixes made before accepting the pilot:

- `scripts/distill_rag_contract_v5.py`
  - accepts source refs inside combined citations;
  - gives explicit Latin-script instructions for `roman_nepali`;
  - relaxes English language validation enough to allow Nepali names/titles in
    otherwise English answers.
- `server/main.py`
  - added `manpower` / recruitment-agency aliases for foreign employment;
  - added foreign-employment strong markers for complaint routing.
- `server/navigator.py`
  - changed service detection from first-match to scored match so
    `driving license` beats incidental `citizenship number`.
- `eval/service_eval_expanded_v5_seed.jsonl`
  - widened embassy/consular/passport expected domains;
  - rewrote the foreign-employment complaint seed to include the service.
- `scripts/build_v5_pilot100.py`
  - added demand-specific normalized questions and mixed identity-document
    expected domains.

After revalidation and a 6-row repair pass:

```text
corpora/sft_v5_rag_contract_pilot100_haiku_20260511_clean.jsonl
rows: 100
errors: 0
validation issues: 0
answerability: partial=51, refuse=33, answer=15, off_domain=1

corpora/sft_v5_pilot100_haiku_train.jsonl
corpora/sft_v5_pilot100_haiku_val.jsonl
formatted records: 200
train: 190
val: 10
```

Public deployment checks after the routing changes:

```text
eval/reports/rag_query_audit_public_v5pilot_20260511.jsonl
pass: 14/14
bad citations: 0/14
loops: 0/14
slow generation: 0/14

eval/reports/navigator_smoke_public_v5pilot_recheck_20260511.jsonl
pass: 7/7
```

Current decision: this pilot100 is clean enough to use as the v5 pilot training
slice and as the template for a 500-record expansion. Do not jump straight to a
large full SFT run without sampling the 500-record expansion; the pilot showed
that retrieval/router and teacher language issues are still the main failure
classes, and both are fixable only if the validator stays in the loop.

### Language-control lesson from production

The live query `who to contact when i got cheated by manpower agency` retrieved
the right foreign-employment/FEB source but the base model answered in
Devanagari Nepali despite `detected_lang=english`. That is exactly the class of
behavior v5 must train against:

- the contract must carry `question_lang`;
- English questions must produce English answers even when source excerpts are
  Nepali;
- Roman-Nepali questions must stay Latin-script Roman Nepali;
- complaint/contact flows should cite the responsible office and contact path,
  not translate into the source language.

For production, this path is now deterministic via
`_foreign_employment_complaint_fallback_answer`. For v5 expansion, include
foreign-employment complaint/contact examples where the evidence is Nepali but
the user question is English or Roman Nepali, so the model learns the language
contract when deterministic extraction does not cover the case.

Runtime safety note: the public server now also blocks wrong-script generated
answers. If `detected_lang` is English or Roman Nepali and the generated answer
is Devanagari-heavy, that generated text is not returned. Streaming buffers
free-form model output until this guard passes. V5 should still train the model
to obey the language contract, but production does not rely on SFT alone for
this failure mode.

## 2026-05-12 dialogue-planner pilot

The next v5 slice is now separated from final-answer RAG distillation:

- `eval/service_dialogue_v5_seed.jsonl` contains 12 multi-turn/intake seed
  cases: ambiguous citizenship, memory carryover, Jiri birth/contact routing,
  manpower-agency complaint, passport-minor follow-up, land-tax location
  follow-up, consular passport contact, and harmless off-domain math.
- `scripts/build_v5_dialogue_contracts.py` turns those seeds into deterministic
  planner contracts using `server.navigator.resolve_case`.
- `scripts/format_sft_v5_dialogue.py` formats those contracts into SFT rows.

Current local build:

```text
corpora/sft_v5_dialogue_contract_seed.jsonl
seed rows: 12
validation issues: 0
decisions:
  ack_memory: 1
  contact_handoff_or_retrieve: 4
  off_domain_light_answer: 1
  partial_answer_plus_followup: 5
  retrieve_then_answer: 1

corpora/sft_v5_dialogue_seed_train.jsonl
corpora/sft_v5_dialogue_seed_val.jsonl
formatted records: 19
  v5_dialogue_contract_json: 12
  v5_dialogue_response: 7
```

This is not enough data to train a checkpoint. It is the schema and validator
for the next 500-record dialogue expansion. The training mix should combine:

- existing clean RAG-contract rows for source-grounded answering;
- dialogue-contract rows for intake/follow-up/memory/source-class routing;
- replay/general rows so the model does not collapse on harmless simple
  questions.

Do not treat deterministic fallbacks as the product advantage. They are runtime
guards. The v5 advantage should come from the model learning the planner
contract: ask the compact next question, preserve chat memory, route source
classes by question type, and keep the user's language/script.

## 2026-05-12 dialogue500 expansion

The dialogue-planner pilot has been expanded into a first usable training mix.

New generator and artifacts:

- `scripts/build_v5_dialogue_seed500.py`
- `eval/service_dialogue_v5_seed500.jsonl`
- `corpora/sft_v5_dialogue_contract_seed500.jsonl`
- `corpora/sft_v5_dialogue_seed500_train.jsonl`
- `corpora/sft_v5_dialogue_seed500_val.jsonl`

Strict contract validation result:

```text
seed rows: 500
contracts: 500
validation issues: 0
decisions:
  ack_memory: 14
  contact_handoff_or_retrieve: 84
  off_domain_light_answer: 2
  partial_answer_plus_followup: 183
  retrieve_then_answer: 217
```

The first validation pass found useful resolver bugs before they became SFT
data:

- Nepali district aliases from `DISTRICT_ALIASES` were overwritten by rows from
  `corpora/nepal_districts.jsonl`.
- Known municipalities such as Jiri and Khandbari were not carrying their
  district into citizenship DAO routing.
- `land tax` was being misclassified as PAN/tax.
- `police clearance report` was accidentally treated as contact intent because
  `report` was too broad as a contact alias.
- Roman `rastriya parichayapatra` was missing from national ID aliases.

Those are now fixed in `server/navigator.py`.

Post-build sample review also found and fixed language-quality issues in the
dialogue response templates: Devanagari follow-ups no longer use English
service/district labels, and Roman-Nepali fallback lines stay in Roman Nepali.

Training mix prepared:

- `scripts/build_v5_training_mix.py`
- `corpora/sft_v5_mix_dialogue500_train.jsonl`
- `corpora/sft_v5_mix_dialogue500_val.jsonl`

Current mix:

```text
train rows: 1339
val rows: 110
train v5_dialogue_seed500: 629
train v5_rag_clean_pilot100: 570
train v5_replay_math: 60
train v5_replay_english: 40
train v5_replay_roman: 40
```

This is now ready for a short E2B checkpoint sweep. Select checkpoints by
behavior evals, not val loss alone.

Latest local check:

```text
contract JSON rows: 500 bad: 0
train rows: 1339 bad message rows: 0
val rows: 110 bad message rows: 0
wrong-script dialogue responses: 0
latin-heavy Devanagari responses: 0
```

## 2026-05-13 Sonnet source-grounded distillation

The next data pass followed the research direction: generate structured
RAG-contract supervision and preference pairs, not just more final answers.

Round 1 used the 100-item v5 pilot seed:

```text
contracts: corpora/sft_v5_rag_contract_round1_100_sonnet_clean_20260513.jsonl
clean contracts: 100
answerability: partial 75, refuse 18, answer 6, off_domain 1
formatted train/val:
  corpora/sft_v5_round1_100_sonnet_train.jsonl      190 rows
  corpora/sft_v5_round1_100_sonnet_val.jsonl         10 rows
preference pairs:
  corpora/sft_v5_preference_pairs_round1_100_sonnet_20260513.jsonl
  rows: 100
```

Round 2 used real citizen-demand questions that were not already in the pilot
seed:

```text
seed: eval/round2_sonnet_demand85_20260513.jsonl
raw contracts: corpora/sft_v5_rag_contract_round2_demand85_sonnet_20260513.jsonl
repair seed: eval/round2_sonnet_repair25_20260513.jsonl
repair contracts: corpora/sft_v5_rag_contract_round2_repair25_sonnet_20260513.jsonl
clean contracts: corpora/sft_v5_rag_contract_round2_demand81_sonnet_clean_20260513.jsonl
excluded rows: corpora/sft_v5_rag_contract_round2_demand_bad4_sonnet_20260513.jsonl
answerability: partial 48, refuse 33
formatted train/val:
  corpora/sft_v5_round2_demand81_sonnet_train.jsonl  154 rows
  corpora/sft_v5_round2_demand81_sonnet_val.jsonl      8 rows
preference pairs:
  corpora/sft_v5_preference_pairs_round2_demand81_sonnet_20260513.jsonl
  rows: 81
```

Combined Sonnet artifacts for the next training/eval pass:

```text
corpora/sft_v5_sonnet_rag_round1_round2_train.jsonl  344 rows
corpora/sft_v5_sonnet_rag_round1_round2_val.jsonl     18 rows
corpora/sft_v5_preference_pairs_round1_round2_sonnet_20260513.jsonl 181 rows
```

Quality lesson from this pass: Sonnet repeatedly drifted into Hindi-like Roman
phrases on Roman-Nepali answers (`hamare`, `hamarasanga`, `abhi`, `nahi`,
`sakta hai`, etc.). `scripts/distill_rag_contract_v5.py` now has a
Hindi-artifact validator and stronger Roman-Nepali teacher instructions. Keep
that gate for every future SFT data pass; otherwise wrong-language behavior can
enter the training set unnoticed.

The Round 2 answerability skew is also a product signal: many real citizen
questions are valid but not well covered by the current corpus. Use those
`refuse` and `partial` rows to drive source coverage and gap logging; do not
let refusal-heavy rows dominate the final SFT mix.

## 2026-05-13 Opus source-discovery pilot

Added an Opus/Claude Code source-discovery path for rows where current RAG is
insufficient:

```text
scripts/claude_source_discovery_v5.py
scripts/extract_source_candidates_v5.py
```

The discovery worker sends each question plus the current SpeakGov `/retrieve`
source pack to Claude Code Opus. The requested output is not a final training
answer alone; it is a structured source-discovery record:

- whether current RAG sources are useful or distractors;
- official source URLs to crawl;
- source class: law/rule, service page, citizen charter, notice/fee, contact,
  office directory, etc.;
- whether the URL was fetched/relevant or only an official candidate;
- source-backed facts, missing fields, compact follow-ups, and crawl notes.

Pilot files:

```text
eval/opus_source_discovery_pilot5_20260513.jsonl
eval/opus_source_discovery_pilot4_with_rag_20260513.jsonl
eval/opus_source_candidates_pilot4_20260513.jsonl
eval/opus_source_tier_overrides_pilot4_20260513.jsonl
```

Pilot result:

```text
rows: 4
total Opus/Claude Code cost: about $3.00
candidate domains: 15
new source override candidates: 5
```

High-signal candidate domains from the pilot:

- `lawcommission.gov.np` and `repository.lawcommission.gov.np` for election and
  education-law gaps;
- `traffic.nepalpolice.gov.np`, `metro.nepalpolice.gov.np`, and
  `ktmvalley.nepalpolice.gov.np` for traffic fine/class/contact gaps;
- `cehrd.gov.np`, `moecdc.gov.np`, `moest.gov.np`, and `neb.gov.np` for school
  education and textbook/homeschooling gaps;
- `nrb.org.np` and `ird.gov.np` for bank/PAN/minor-account gaps.

Important: many Opus-discovered URLs were marked
`official_candidate_not_fetched`. Treat those as crawl targets, not final
ground truth. The correct loop is:

1. Opus audits current RAG and proposes official source candidates.
2. Add/patch source registry and crawl/index those sources.
3. Rerun retrieval and regenerate RAG contracts from our own corpus.
4. Only then include the regenerated clean contracts in SFT.

For future web-search-agent capability in the local model, do not jump directly
to free-form browsing. First train the planner behavior:

- detect when current RAG is insufficient;
- name the missing source class/domain;
- ask for/search official sources;
- distinguish fetched evidence from candidate URLs;
- hand back crawl/gap tasks when evidence is not verified.

Runtime can use a backend source-discovery agent for the demo, while the local
model learns when and how to escalate to that agent.

## 2026-05-14 v5 E4B run postmortem

The first full v5 recipe run is complete and should be treated as a negative
result, not a deployable adapter.

Run:

```text
base: google/gemma-4-E4B-it
train: corpora/sft_v5_recipe_round1_train.jsonl
val: corpora/sft_v5_recipe_round1_val.jsonl
instance: g6e.xlarge / NVIDIA L40S 46 GB
HF repo: voidash/gemma-helpdesk-seed42
```

Artifacts:

```text
ckpt/step100/
ckpt/best/
ckpt/final/
eval/sft_v5_recipe_e4b_seed42/
smoke/v5_adapter_smoke_all.json
```

Training loss looked good:

```text
initial val loss: 3.3477
step100 val loss: 0.3832
best/final step: 183
best val loss: 0.2522
```

Behavior did not.

Manual smoke showed:

- base leaked chain-of-thought-like `thought` text and stray CJK/Thai tokens;
- step100 invented contact data and failed a harmless math redirect;
- best/final were cleaner but still invented/misrouted government-service facts
  and did not reliably ask follow-ups.

Important conclusion: validation loss on this mixture selected for surface-form
imitation, not service-navigator behavior.

The next SFT pass should be planner/composer-first:

- train resolver/intake and missing-slot decisions;
- train source-selection and answerability contracts;
- train final answers only over provided source IDs/snippets;
- keep exact contacts, fees, names, dates, and URLs deterministic/extractive;
- select checkpoints by smoke/eval gates, not val loss.

Full operational handoff: `SFT_V5_POSTMORTEM_AND_NEXT_PASS.md`.
