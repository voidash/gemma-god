# SpeakGov SFT v5 Recipe

Snapshot: 2026-05-13.

This is the current training recipe for SpeakGov as a government-service
navigator. It is based on the product contract in
`SERVICE_NAVIGATOR_MODUS_OPERANDI.md` and the latest SFT research pass.

## 2026-05-14 Status Update

This recipe was executed on 2026-05-13 and should not be repeated as-is.

The E4B run completed on `g6e.xlarge` and uploaded checkpoints to
`voidash/gemma-helpdesk-seed42`, but the adapter failed behavioral smoke tests.
It learned cleaner style in places, but still invented facts, gave generic
procedures when follow-up was required, and misrouted some services.

Read `SFT_V5_POSTMORTEM_AND_NEXT_PASS.md` before generating more data or
training another v5 adapter.

New direction:

- do not train the adapter to memorize government facts;
- train resolver/intake, answerability, source-selection, and composer behavior
  over provided source context;
- select checkpoints by product smoke/eval gates, not validation loss alone;
- keep exact contacts, fees, office holders, dates, and URLs on deterministic
  extraction/source-grounded paths.

## Research Anchors

Use these as the guardrails, not as branding:

- LIMA: small, diverse, carefully curated instruction data can teach response
  style and alignment; do not chase volume at the expense of quality.
  Source: https://arxiv.org/abs/2305.11206
- InstructGPT: use SFT demonstrations first, then preference data. The model
  needs examples of desired behavior before preference optimization.
  Source: https://huggingface.co/papers/2203.02155
- RAFT: for domain RAG, train on retrieved documents plus distractors, and
  teach the model to identify/use the relevant evidence rather than memorize.
  Source: https://openreview.net/pdf?id=6bptQJp2i9
- Self-RAG: train explicit decisions around whether retrieval is needed, whether
  retrieved passages are relevant, and whether the answer is supported.
  Source: https://arxiv.org/abs/2310.11511
- Tulu 3 / modern post-training: iterate through data mixture ablations and
  targeted evaluations, not val loss alone.
  Source: https://allenai.org/blog/tulu-3-technical
- TRL SFTTrainer guidance: train assistant/completion tokens only for
  conversational SFT. Our local trainer already masks system/user tokens.
  Source: https://huggingface.co/docs/trl/v0.21.0/en/sft_trainer

## Current Artifacts

Primary train/val for the next v5 run:

```text
corpora/sft_v5_recipe_round1_train.jsonl  1471 rows
corpora/sft_v5_recipe_round1_val.jsonl     120 rows
```

Composition:

```text
v5_rag_clean_pilot100      688
v5_dialogue_seed500        629
v5_replay_math              60
v5_replay_roman             40
v5_replay_english           40
v5_source_discovery_plan    14
```

Separate preference data:

```text
corpora/sft_v5_preference_pairs_round1_round2_sonnet_20260513.jsonl  181 rows
```

Do not fold preference pairs into SFT blindly. Use them for DPO/ORPO or for
eval negatives after the SFT checkpoint is selected.

## Data Types We Want

### 1. Dialogue Planner

Purpose: teach the assistant to behave like a helpdesk worker, not a generic
RAG Q&A model.

Includes:

- intake/resolver;
- compact follow-ups;
- memory reuse;
- partial answer plus follow-up;
- contact handoff;
- harmless off-domain answer and redirect.

Existing source:

```text
corpora/sft_v5_dialogue_seed500_train.jsonl
corpora/sft_v5_dialogue_seed500_val.jsonl
```

### 2. RAG Answer + RAG Contract

Purpose: teach source-grounded answering and visible answerability decisions.

Each clean RAG contract emits two SFT rows:

- final user answer with `[S#]` citations;
- JSON contract with answerability, relevant source IDs, facts, missing fields,
  and answer.

Existing combined source:

```text
corpora/sft_v5_sonnet_rag_round1_round2_train.jsonl
corpora/sft_v5_sonnet_rag_round1_round2_val.jsonl
```

Quality gate:

- no raw URLs in final answer;
- no unknown source IDs;
- no `answer` rows with non-empty `missing`;
- no wrong-script output;
- no Hindi artifacts in Roman Nepali.

### 3. Source-Discovery Planner

Purpose: teach the model when RAG is insufficient and how to escalate to a
source-discovery/crawl task.

This is the first step toward web-search-agent capability. It does not train the
local model to browse directly yet.

Existing pilot:

```text
eval/opus_source_discovery_pilot4_with_rag_20260513.jsonl
corpora/sft_v5_source_discovery_pilot4_train.jsonl
corpora/sft_v5_source_discovery_pilot4_val.jsonl
```

Desired assistant behavior:

- inspect current RAG source pack;
- mark irrelevant RAG sources as distractors;
- name missing official source classes/domains;
- propose source/crawl targets;
- separate fetched evidence from candidate URLs;
- give only supported partial guidance.

### 4. Replay Anchors

Purpose: prevent the small adapter from making the model worse at harmless
general tasks or Roman Nepali phrasing.

Keep these small. They are regularizers, not product data.

Existing current counts:

```text
math replay:     60
English replay:  40
Roman replay:    40
```

## Current Gaps To Fill

### Gap A: Source-Discovery Planner Is Too Small

Current: 14 train rows.

Target before serious v5 training: at least 150-250 clean planner rows.

Generate from:

- Round 2 `partial` and `refuse` rows;
- RAG audit failures;
- user-reported failures from helpdesk.ampixa.com;
- source coverage matrix gaps.

Use:

```text
scripts/claude_source_discovery_v5.py
scripts/extract_source_candidates_v5.py
scripts/format_source_discovery_sft_v5.py
```

### Gap B: Corpus Must Be Updated Before More RAG SFT

Do not train many refusal rows when Opus has found official candidates. Crawl
and index the candidate sources first, then regenerate RAG contracts.

Pilot candidate domains:

```text
repository.lawcommission.gov.np
cehrd.gov.np
moecdc.gov.np
metro.nepalpolice.gov.np
ktmvalley.nepalpolice.gov.np
```

Also prioritize already-registered domains that retrieval failed to surface:

```text
lawcommission.gov.np
traffic.nepalpolice.gov.np
election.gov.np
nrb.org.np
ird.gov.np
moest.gov.np
neb.gov.np
```

### Gap C: Preference Data Exists But Is Not Used Yet

Current: 181 clean preference pairs.

Target: 500-1000 pairs after more clean contracts.

Failure types to maintain:

- wrong language / Hindi drift;
- wrong source;
- wrong locality;
- unsupported claim;
- hallucinated contact;
- over-refusal;
- generic answer;
- raw URL citation;
- ignored history.

### Gap D: Need Behavioral Evals Before Training More

Select checkpoints by behavior, not val loss alone.

Minimum eval slices:

- source relevance and citation validity;
- follow-up behavior for ambiguous cases;
- memory reuse;
- Roman Nepali no-Hindi check;
- contact/person lookup;
- refusal vs partial answer boundary;
- source-discovery escalation when RAG is bad;
- harmless off-domain light answer.

## Training Recommendation

Historical note: this recommendation produced the failed 2026-05-13 adapter and
is retained for traceability only. Do not use it as the next recipe.

For the 2026-05-13 E4B run:

```text
train: corpora/sft_v5_recipe_round1_train.jsonl
val:   corpora/sft_v5_recipe_round1_val.jsonl
```

Trainer settings used:

```text
assistant-only loss
rsLoRA r=64 alpha=128
target q,k,v,o,gate,up,down
LR 1e-4
max_seq_length 2048
checkpoint sweep every 200 steps
```

Observed result:

```text
initial val loss: 3.3477
step 100 val loss: 0.3832
best/final step: 183
best val loss: 0.2522
smoke verdict: do not deploy
```

The next recipe should follow `SFT_V5_POSTMORTEM_AND_NEXT_PASS.md`: lower LR,
lower rank, one epoch max, checkpoint every 25-50 steps, and behavior-gated
selection.

## Next Data Loop

1. Run Opus+RAG discovery for 30-50 high-value partial/refuse rows.
2. Extract source candidates and add verified source overrides.
3. Crawl/index the source candidates.
4. Rerun retrieval audits.
5. Regenerate clean RAG contracts from our own corpus.
6. Generate preference pairs.
7. Rebuild the recipe mix.
8. Train one short checkpoint sweep.
9. Select by behavior evals.
