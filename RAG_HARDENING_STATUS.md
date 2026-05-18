# RAG hardening status - 2026-05-11

## Latest progress since the last handoff

Goal for this pass: stop treating every observed RAG failure as a unique bug,
and move toward a source-covered, resolver-first government-service navigator.
The working product contract now lives in
`SERVICE_NAVIGATOR_MODUS_OPERANDI.md`: resolver/intake before RAG, compact
follow-ups for ambiguity, chat memory, question-dependent source ranking,
named human practical sources, and contact handoff when useful.

### 2026-05-18 WhatsApp follow-up history fix

Observed failure:

- WhatsApp user asked for birth-registration process, the bot asked for
  municipality, and the user replied with Dharmadevi Municipality.
- The planner recognized `vital_registration` + Dharmadevi correctly, but the
  answer path sometimes still returned a flat no-source refusal.

Root cause:

- `whatsapp/src/server.mjs` pushed the current incoming user message into
  in-memory history before calling `/query`.
- The API therefore received the same text both as `question` and as the last
  `history` user turn. `_prompt_question` treated that duplicate current turn as
  the previous user question, so the original "birth registration" subject was
  dropped before the event-registration fallback.

Fix:

- `whatsapp/src/server.mjs` now calls `/query` with prior history only, then
  appends the current user/assistant turns after the reply.
- `server/main.py` defensively strips a duplicate current user turn from
  history before resolver, retrieval, prompt-question, and prompt-history
  handling. This protects other clients that accidentally include the current
  turn in history.
- Added regression case
  `whatsapp_current_turn_history_birth_dharmadevi` to
  `eval/service_navigator_pipeline_smoke.jsonl`.

Verification:

```text
python3 scripts/service_navigator_pipeline_audit.py --planner-only \
  --questions eval/service_navigator_pipeline_smoke.jsonl
pass: 19/19
report: eval/reports/service_navigator_pipeline_20260518_163135.jsonl

live k2:
python3 scripts/service_navigator_pipeline_audit.py \
  --base-url http://127.0.0.1:8000 \
  --questions eval/service_navigator_pipeline_smoke.jsonl
pass: 19/19
report: eval/reports/service_navigator_pipeline_20260518_163438.jsonl
```

Direct live WhatsApp-shaped payload with duplicated current history now returns
a source-backed Dharmadevi/DONIDCR birth-registration answer instead of
`मलाई यो प्रश्नको आधिकारिक स्रोत भेटिनँ।`.

### 2026-05-16 planner-first pipeline gate

After the v6.3 SFT failure, the deployable path moved back to deterministic
pipeline control instead of another blind adapter run.

Implemented:

- `server/navigator.py` now exposes a `service_navigator_planner_v1` contract:
  service, action, case type, normalized location, missing slots,
  follow-up questions, source classes, expected domains, retrieval query, and
  coverage gaps.
- Complaint intent is separated from generic contact intent, so manpower fraud
  routes as `foreign_employment` + `complaint` instead of a vague contact query.
- `server/main.py` now returns the planner contract from `/retrieve`,
  `/query`, and `/query/stream` metadata/final responses.
- `scripts/service_navigator_pipeline_audit.py` checks planner, retrieval,
  answer, language/script, citations, generation latency, and loop/refusal-tail
  behavior in one gate.
- `eval/service_navigator_pipeline_smoke.jsonl` covers the known critical
  product failures: ambiguous Sankhuwasabha citizenship, chat memory, Jiri
  birth/contact/helpdesk/mayor, manpower fraud, and harmless off-domain math.

k2 deployment:

```text
server: http://<k2-tailnet-ip>:8000
model: google/gemma-4-E2B-it
adapter: none
backup timestamp before deploy: 20260516185352
```

Verification after deploy:

```text
python3 scripts/service_navigator_pipeline_audit.py \
  --base-url http://<k2-tailnet-ip>:8000 \
  --questions eval/service_navigator_pipeline_smoke.jsonl

pass: 8/8
report: eval/reports/service_navigator_pipeline_k2_20260516_185517.jsonl

python3 scripts/navigator_smoke_audit.py --base-url http://<k2-tailnet-ip>:8000
pass: 7/7
report: eval/reports/navigator_smoke_k2_planner_20260516_185800.jsonl

python3 scripts/rag_query_audit.py --base-url http://<k2-tailnet-ip>:8000
pass: 15/15
refused: 1/15
bad citations: 0/15
loops: 0/15
slow generation: 0/15
report: eval/reports/rag_query_audit_k2_planner_20260516_185800.jsonl
```

Streaming smoke also passed for the manpower fraud case:

```text
events: meta=1, token=82, final=1, error=0
```

Important limitation: this is a pipeline hardening step, not proof that the
E2B model is a good free-form composer. Exact/common workflows are still being
handled by resolver, retrieval routing, and deterministic fallback/extraction
paths wherever possible.

### Source coverage

Added a district/source coverage base:

- `corpora/nepal_districts.jsonl`: 77 Nepal district records with ASCII aliases
  and DAO domain candidates.
- `scripts/seed_dao_sources.py`: seeds DAO/CDO source overrides from the
  district registry, optionally verifying HTTP reachability before appending to
  `corpora/tier_overrides.jsonl`.
- `scripts/run_crawl_batch.py`: batch crawler helper fixed for long source
  lists and faster FTS sync via a temp indexed table.

Verified and registered 11 reachable DAO domains under the current
`dao{district}.moha.gov.np` pattern:

- `daobhaktapur.moha.gov.np`
- `daokailali.moha.gov.np`
- `daonuwakot.moha.gov.np`
- `daookhaldhunga.moha.gov.np`
- `daoparsa.moha.gov.np`
- `daorasuwa.moha.gov.np`
- `daorautahat.moha.gov.np`
- `daosankhuwasabha.moha.gov.np`
- `daosaptari.moha.gov.np`
- `daosiraha.moha.gov.np`
- `daotanahu.moha.gov.np`

On k2, initialized those sources into SQLite and crawled/indexed them. Batch log:
`/Users/k2/gemma-god/eval/reports/dao_crawl_batch_20260511.jsonl`.

Approximate DAO crawl result:

- active DAO docs: 410 new docs across the 11 sources;
- chunks: 293 new chunks;
- FTS count after sync: 270,820 chunks.

Important caveat: only 11 candidates were reachable with the simple DAO domain
pattern. Next source-discovery step should find the official MoHA/district-office
directory and seed from that, not assume the URL pattern covers Nepal.

Follow-up completed from the official MoHA pages:

- `scripts/seed_moha_office_sources.py` parses `https://moha.gov.np/en/offices`
  and `https://moha.gov.np/en/contact`, including Leaflet popup links.
- The parser found 172 official office-directory links: 75 DAO, 81 Area
  Administration Office, 7 Border Administration Office, 7 MoHA subordinate
  offices, and 2 federal links.
- After normalizing malformed MoHA directory URLs and accepting MoHA shared-host
  `429` rate limits as reachable evidence, 160 new official office sources were
  added to the registry.
- The local source registry now has 1,065 rows; k2 SQLite has 1,069 source rows
  after sync and existing runtime sources.

Priority crawl on k2:

```text
eval/reports/moha_priority_crawl_batch_20260511.jsonl
processed sources: 31
docs added: 1,023
chunks added: 1,540
zero-chunk source: aaohedanga_moha_gov_np
final chunks_fts: 272,360
```

Current k2 corpus snapshot after that crawl:

```text
sources: 1,069
live documents: 45,951
chunks: 272,360
chunks_fts: 272,360
```

Some official-directory domains are still low-confidence for useful content:
they are official links, but if repeat crawls produce zero chunks they should be
demoted or marked as directory-only sources instead of being treated as service
evidence.

### Source-ranking fixes after v5 pilot

The first 25-record v5 pilot exposed two source-selection bugs:

- local tacit claims from Jiri were still appearing in a Khandbari/Sankhuwasabha
  citizenship follow-up;
- labor-permit questions were using Foreign Employment Board sources even when
  Department of Foreign Employment/FEIMS was the right authority class.

Fixes deployed to k2:

- `filter_tacit_results_for_frame` now removes local/DAO tacit claims that do
  not match the resolved municipality or district DAO.
- Retrieval adds authority-domain supplements, so expected official domains can
  enter the candidate pool even when a large neighboring corpus dominates BM25.
- Foreign-employment routing is now question-dependent: labor permit/श्रम
  स्वीकृति prefers `dofe.gov.np`/`feims.dofe.gov.np`; welfare/death/compensation
  prefers `feb.gov.np` with DOFE as secondary.
- Local-domain root pages are pulled into the candidate pool for resolved
  local/district cases, which lets DAO homepage/contact evidence appear for
  district-specific follow-ups.

Public verification after deployment:

```text
eval/reports/service_matrix_public_rerank_20260511.jsonl
pass: 13/13

eval/reports/rag_query_audit_public_rerank_20260511.jsonl
pass: 14/14
bad citations: 0/14
loops: 0/14
slow generation: 0/14
```

### Embassy and province transport coverage

The clean v5 pilot still showed two coverage gaps: passport-abroad questions
needed the relevant Nepali mission source, and Pokhara driving-license questions
needed the provincial transport office source.

Added sources:

- `qa_nepalembassy_gov_np` - Embassy of Nepal, Doha, from MoFA's diplomatic
  mission directory.
- `tmolkaski_gandaki_gov_np` - Transport Management Office, Driving License,
  Kaski/Pokhara.

Focused k2 crawl:

```text
eval/reports/mission_transport_crawl_batch_20260511.jsonl
qa_nepalembassy_gov_np: +28 docs / +26 chunks
tmolkaski_gandaki_gov_np: +72 docs / +332 chunks
final chunks_fts: 272,718
```

Current k2 corpus snapshot after this focused crawl:

```text
sources: 1,071
live documents: 46,051
chunks: 272,718
chunks_fts: 272,718
```

Additional deployed routing:

- passport questions mentioning Qatar/Doha/embassy/abroad include
  `qa.nepalembassy.gov.np`, `mofa.gov.np`, and `nepalpassport.gov.np`;
- Pokhara/Kaski/Gandaki driving-license questions include
  `tmolkaski.gandaki.gov.np`, `dotm.gov.np`, and transport-management domains;
- `consular` is now an explicit retrieval topic so Jiri/local tacit snippets do
  not leak into consular-attestation prompts.

Final public verification after these changes:

```text
eval/reports/service_matrix_public_coverage_20260511.jsonl
pass: 13/13

eval/reports/rag_query_audit_public_coverage_20260511.jsonl
pass: 14/14
bad citations: 0/14
loops: 0/14
slow generation: 0/14
```

### Resolver and retrieval changes

`server/navigator.py`:

- loads `corpora/nepal_districts.jsonl`;
- recognizes all districts from data instead of a tiny hard-coded list;
- fixes Latin substring false positives like `Rupandehi` matching `Rupa` and
  `Dhangadhi` matching `Gadhi`.

`server/main.py`:

- detects explicit `.gov.np` / `.org.np` domains in resolver-expanded queries;
- adds a generic deterministic contact fallback for local/DAO contact questions;
- adds a direct local-contact retrieval path for contact/person/phone intent so
  the app does not scan the whole FTS corpus for a known office domain;
- adds contact-person/topic boosts for mayor, deputy mayor, information officer,
  chief administrative officer, contact page, office phone, and local domains;
- keeps exact contact answers generation-free when confidence is high.

Example that worked after DAO crawl and generic contact fallback:

```text
Question: Sankhuwasabha DAO phone/contact
Answer shape: जिल्ला प्रशासन कार्यालय, संखुवासभा lists phone 9858391356 [S1].
Generation: 0 ms
```

### Eval and smoke status

Broad service matrix:

```text
eval/service_matrix_smoke.jsonl
latest passing report before the final contact-rank patch:
eval/reports/service_matrix_public_contact_rank_20260511.jsonl
pass: 13/13
```

RAG smoke:

```text
eval/reports/rag_query_audit_public_final_20260511.jsonl
pass: 14/14 before the final contact-rank patch
```

Regression introduced by the first contact-rank patch:

```text
eval/reports/rag_query_audit_public_contact_rank_20260511.jsonl
pass: 12/14
failures:
- jiri_helpdesk_fused_ne: returned information-officer phone instead of office Contact No.
- jiri_mayor_ne: returned information officer instead of Mayor.
```

Fix prepared after that regression:

- phone/helpdesk queries now strongly prefer `/content/contact` and `Contact No`;
- role-specific queries now boost the requested role and penalize unrelated
  information-officer chunks;
- Jiri official extraction now separates glued strings like
  `gmail.comPhone`;
- role-specific fallback refuses to answer from a candidate set that does not
  contain the requested role.

This latest fix has been copied to k2 in `/Users/k2/gemma-god/server/main.py`.
There was one deployment false start: restarting without the production env made
uvicorn try to load the server default `mlx-community/gemma-4-e4b-it-bf16`,
which failed with mismatched/missing weights. The process was restarted with the
intended env:

```text
MODEL_ID=google/gemma-4-E2B-it
ADAPTER_PATH unset
DB_PATH=/Volumes/T9/gemma-god/corpus_v2/index.db
```

Added and copied this helper to k2:

```bash
scripts/start_k2_helpdesk.sh
```

Use it for future restarts from `/Users/k2/gemma-god`; it unsets
`ADAPTER_PATH`, pins E2B, points at the 2.5G RAG DB, and writes
`server/uvicorn.pid` / `server/uvicorn.log`.

Public health after restart:

```json
{"status":"ok","model_id":"google/gemma-4-E2B-it","adapter":null,"model_loaded":true,"db_loaded":true}
```

Fixed verification:

```bash
python3 scripts/navigator_smoke_audit.py \
  --base-url https://helpdesk.ampixa.com \
  --questions eval/service_matrix_smoke.jsonl \
  --out eval/reports/service_matrix_public_fixed_20260511.jsonl \
  --timeout 120

python3 scripts/rag_query_audit.py \
  --base-url https://helpdesk.ampixa.com \
  --questions eval/rag_query_smoke.jsonl \
  --out eval/reports/rag_query_audit_public_fixed_20260511.jsonl \
  --timeout 120 \
  --max-new-tokens 300
```

Results:

```text
eval/reports/service_matrix_public_fixed_20260511.jsonl
pass: 13/13

eval/reports/rag_query_audit_public_fixed_20260511.jsonl
pass: 14/14
bad citations: 0/14
loops: 0/14
slow generation: 0/14
```

### Current operating view

RAG/source coverage is now the load-bearing path. The current SFT/E2B behavior
was too brittle for a public helpdesk, so the deployed path should prefer base
instruct plus deterministic extraction and resolver controls. SFT v5 should
train the RAG contract later: follow-up questions, partial answers, source
selection, multi-turn memory, and refusal/uncertainty only when source evidence
actually fails.

### Immediate next steps

1. Continue source discovery beyond the 11 reachable DAO pattern domains.
2. Consider turning `scripts/start_k2_helpdesk.sh` into a launchd/systemd-style
   service if the demo machine needs unattended restart.
3. If future smokes fail, classify the failure as coverage, chunking, normalization,
   rank, extraction, citation mapping, generation loop, or frontend behavior.
   Avoid adding another query-specific patch unless it clearly fixes a class.

### 2026-05-11 v5 pilot routing hardening

The 100-record v5 SFT pilot exposed two real routing classes and both are fixed
in the deployed public server:

- Foreign-employment complaint queries that say "manpower agency" now route to
  DOFE/FEB authority domains. Previously this wording could drift to NHRC or
  unrelated sources because it lacked the explicit `foreign employment` phrase.
- Mixed driving-license questions that mention `citizenship number` now keep
  the driving-license frame. The navigator now scores service aliases instead
  of returning the first service that matched, so the phrase `driving license`
  beats incidental identity-document words.

Deployed public health after restart:

```text
https://helpdesk.ampixa.com/health
model_id: google/gemma-4-E2B-it
adapter: null
db_loaded: true
```

Post-change audits:

```text
eval/reports/rag_query_audit_public_v5pilot_20260511.jsonl
pass: 14/14

eval/reports/navigator_smoke_public_v5pilot_recheck_20260511.jsonl
pass: 7/7
```

One navigator smoke expectation was updated because the corpus now has the
Sankhuwasabha DAO source. The correct behavior is to return
`daosankhuwasabha.moha.gov.np` and phone `9858391356`, not to say the source is
missing.

### 2026-05-11 manpower complaint language drift

Observed live failure:

```text
who to contact when i got cheated by manpower agency
```

Retrieval was correct: the query routed to `foreign_employment` and surfaced
FEB/DOFE-related sources. The failure was generation: the base model detected
the question as English but answered in Devanagari Nepali. This is a
composer/language-control failure, not a source-recall failure.

Production fix:

- added `_foreign_employment_complaint_fallback_answer`;
- complaint/cheated/manpower/agency questions now answer extractively from the
  retrieved foreign-employment sources;
- English stays English, Roman Nepali stays Latin script, and generation is
  skipped for this high-value contact path.
- added a runtime script guard for generated answers: if an English or
  Roman-Nepali question produces a Devanagari-heavy answer, the server blocks
  that generated text and returns a safe source-cited fallback instead;
- streaming now buffers free-form model generation until the script guard has
  passed, so wrong-script generated text cannot leak token-by-token.

Regression:

```text
eval/reports/rag_query_audit_public_manpower_fix_20260511.jsonl
pass: 15/15
foreign_employment_manpower_cheated_en: OK
bad citations: 0
loops: 0
slow generation: 0

eval/reports/rag_query_audit_public_language_guard_checked_20260511.jsonl
foreign_employment_manpower_cheated_en: OK
devanagari_answer_chars: 0
```

---

# RAG hardening status - 2026-05-07

## Current read

The Jiri failures were not one isolated bug. They exposed a wider pattern: the
RAG stack currently depends too much on BM25 token overlap and prompt behavior.
One-off patches can rescue a demo query, but they do not scale to new spellings,
municipalities, service names, or page layouts.

The durable target is: source coverage is measurable, query understanding is
data-driven, retrieval recall is high before generation, and the composer only
answers from source IDs it was given.

## Live result after today's Jiri pass

Live API: `http://<k2-tailnet-ip>:8000`

Smoke audit:

```text
eval/reports/rag_query_audit_20260507_222402.jsonl
pass: 14/14
```

Fixed/currently passing:

- Jiri birth registration: retrieves the Jiri birth-registration page and DONIDCR FAQ.
- Jiri phone number: returns `+977 071 5555556` from `https://jirimun.gov.np/en/content/contact`.
- Fused/misspelled Nepali helpdesk query: `जिरिहेल्पडेष्क फोन नम्बर` now retrieves the contact page.
- Jiri contact person/officers/mayor: returns current officials from Jiri pages.

Resolved in this pass:

- Police clearance: added the official Nepal Police CID clearance page and ranked it above the homepage; exact procedure answers now use the cited source directly.
- Lost citizenship certificate: added an official DAO/MoHA duplicate-citizenship FAQ source and ranked it above generic MOHA PDFs; exact duplicate-citizenship answers now use the cited source directly.
- Driving license: no longer slow in the current smoke audit.

## What changed

- Raised the Jiri crawl recipe budget and added service/contact entry points.
- Re-crawled Jiri partially, stopped a stuck fetch, then indexed 241 Jiri docs into 496 new chunks.
- Rebuilt FTS to 141,167 chunks.
- Added regression cases for Jiri phone/contact/fused Nepali helpdesk queries.
- Tightened source-ID citation mapping and `www`/non-`www` URL dedupe.
- Added a generic municipality contact-page retrieval boost for local phone/contact intent.

## Why this is still not enough

Reasoning is not the primary missing layer for the Jiri helpdesk typo case. A
reasoning-capable model cannot use a source that retrieval did not surface.
The missing pieces are mostly before generation:

- query normalization for fused Devanagari, spelling variants, Roman Nepali, and English aliases;
- source coverage checks that catch active documents with no chunks;
- semantic retrieval/reranking, not only BM25;
- source/domain registry and service aliases as data, not hard-coded conditionals;
- answerability checks before the small model composes;
- extractive paths for exact facts like phone numbers, fees, office holders, and URLs.

SFT matters, but only after this is stable. The current SFT appears to have
learned a strong refusal habit; v5 should train on retrieval-realistic prompts,
multi-source partial answers, and multi-turn continuity. It should not be asked
to compensate for missing retrieval recall.

### 2026-05-14 SFT v5 postmortem

The 2026-05-13 v5 E4B adapter trained on
`corpora/sft_v5_recipe_round1_train.jsonl` completed on `g6e.xlarge`, uploaded
to `voidash/gemma-helpdesk-seed42`, and self-stopped. It is not deployable.

Training metrics looked good but were misleading:

```text
initial val loss: 3.3477
step 100 val loss: 0.3832
best/final step: 183
best val loss: 0.2522
```

Manual smoke comparison of base, step100, best, and final is uploaded at:

```text
voidash/gemma-helpdesk-seed42/smoke/v5_adapter_smoke_all.json
```

Smoke findings:

- base leaked `thought` text and stray foreign tokens;
- step100 invented a fake Jiri phone number and failed harmless math;
- best/final were cleaner, but still gave generic citizenship checklists,
  misrouted manpower complaints, failed Jiri exact facts, and made unsupported
  Jiri birth-registration claims.

Decision: keep production/demo on RAG plus a strong API composer and
deterministic exact-fact extractors. Future SFT must target planner/composer
behavior over provided source context, not government fact memorization. Full
details are in `SFT_V5_POSTMORTEM_AND_NEXT_PASS.md`.

## Next durable work

1. Ingestion guardrail:
   Add a corpus health command that reports active docs without chunks, duplicate canonical URLs, PDF no-text counts, and latest poll/index time per source. This would have caught the active Jiri contact page having zero chunks.

2. Coverage audit:
   Build a per-service source checklist for the critical workflows: police clearance, citizenship duplicate/lost, driving license, passport, PAN, birth registration, marriage/death registration, company registration. Each checklist needs at least one expected authoritative URL/domain and one smoke question.

3. Query understanding:
   Move aliases into data: municipality names, common misspellings, service aliases, Roman-Nepali variants, Devanagari spelling variants. Keep code generic and make aliases reviewable.

4. Retrieval upgrade:
   Add hybrid retrieval: BM25 candidates plus multilingual dense embeddings, then RRF/cross-encoder or lightweight rerank. Use domain/topic filters as soft constraints, not brittle query-specific rules.

5. Composer control:
   Keep source IDs only, forbid raw URL citations in the prompt, cap loops with decode settings, and add deterministic extractors for exact facts. For small models, exact contact/fee/person answers should not require free-form generation.

6. Eval loop:
   Every observed failure becomes a regression case, but the fix should be bucketed by failure class: coverage, chunking, normalization, retrieval rank, citation mapping, generation loop, or UI streaming/history.
