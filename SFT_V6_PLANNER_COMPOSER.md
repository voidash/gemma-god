# SFT v6 Planner/Composer Pass

v5 showed that answer-only or shallow contract SFT is not enough. The next pass
must train the model as a government-service navigator:

- resolve the case from chat history first;
- ask compact follow-ups when the case is ambiguous;
- route source classes/domains by question, office, location, and service;
- compose only from provided source context;
- cite source-backed facts with `[S#]`;
- include contacts only when sources support names/phones/emails;
- state uncertainty and gaps instead of inventing.

## New Artifacts

- `scripts/distill_planner_composer_v6.py`
  - calls live `/retrieve`;
  - adds deterministic navigator hints from `server/navigator.py`;
  - asks the teacher for one JSON contract containing planner, source routing,
    facts, contacts, gaps, follow-ups, and final answer;
  - validates schema, source IDs, answerability, language/script, raw URLs,
    domain routing, contact grounding, and phone hallucination.

- `scripts/format_sft_v6_planner_composer.py`
  - emits one JSON contract task and one final-answer task per clean contract;
  - skips invalid contracts unless `--include-invalid` is passed.

## Pilot Command

Run a small pass first:

```bash
python3 scripts/distill_planner_composer_v6.py \
  --base-url http://<k2-tailnet-ip>:8000 \
  --questions eval/service_eval_expanded_v5_seed.jsonl \
  --provider meridian \
  --model claude-sonnet-4-6 \
  --limit 20 \
  --out corpora/sft_v6_planner_composer_pilot20.jsonl

python3 scripts/format_sft_v6_planner_composer.py \
  --contracts corpora/sft_v6_planner_composer_pilot20.jsonl \
  --train-out corpora/sft_v6_pilot20_train.jsonl \
  --val-out corpora/sft_v6_pilot20_val.jsonl
```

Review invalid rows before scaling:

```bash
jq -r 'select(.validation_issues|length>0)|[.id, (.validation_issues|join(","))]|@tsv' \
  corpora/sft_v6_planner_composer_pilot20.jsonl
```

## Scale Command

Only scale after the pilot has clean or explainable failures:

```bash
python3 scripts/distill_planner_composer_v6.py \
  --base-url http://<k2-tailnet-ip>:8000 \
  --questions eval/service_eval_expanded_v5_seed.jsonl \
  --provider meridian \
  --model claude-sonnet-4-6 \
  --resume \
  --out corpora/sft_v6_planner_composer_contracts.jsonl

python3 scripts/format_sft_v6_planner_composer.py \
  --contracts corpora/sft_v6_planner_composer_contracts.jsonl \
  --train-out corpora/sft_v6_train.jsonl \
  --val-out corpora/sft_v6_val.jsonl
```

## Trainability Gate

Do not train v6 unless:

- invalid teacher rows are reviewed, not blindly included;
- source-domain failures are either fixed by corpus coverage or excluded;
- follow-up examples exist across many services, not only citizenship;
- contact examples include supported and unsupported cases;
- Roman Nepali rows have no Hindi artifacts;
- exact contact/fee/date rows cite sources and do not contain invented numbers.

The model should learn behavior over provided context. It should not memorize
government facts as weights.

## 2026-05-14 Pilot Result

Two smoke slices were generated:

- `corpora/sft_v6_planner_composer_pilot5.jsonl`
  - first 5 expanded eval seeds;
  - 5/5 passed validation;
  - formatted to 10 train rows.

- `corpora/sft_v6_planner_composer_local_pilot8.jsonl`
  - local/vital/citizenship slice starting at offset 26;
  - 7/8 passed validation;
  - `death_registration_roman` was rejected for `answer_language_mismatch`
    and `followup_language_mismatch` because the teacher mixed script in a
    Roman Nepali answer;
  - formatted output skipped the invalid row and produced 14 train rows.

This is the expected gate behavior: bad teacher rows remain inspectable in the
contract file, but do not enter SFT formatting unless `--include-invalid` is
explicitly passed.

## 2026-05-16 Clean v6 Train Run

Full v6 distillation produced 70 planner/composer contracts in:

```text
corpora/sft_v6_planner_composer_contracts.jsonl
```

The DeepSeek key loader was fixed to read env-style `~/.fmw` files, and five
malformed JSON teacher rows were retried. The final contract file has no hard
`distill_error` rows, but several rows still carry validation warnings such as
raw URL leakage and blocking source gaps. For the training run, only clean rows
were formatted:

```text
corpora/sft_v6_train.jsonl  # 72 rows
corpora/sft_v6_val.jsonl    # 4 rows
```

The invalid-inclusive formatter output exists for inspection only and should
not be used as a default training input.

AWS playground run:

```text
instance: i-08dd7181446403e17
type: g6e.xlarge / L40S
repo: voidash/gemma-helpdesk-v6-e4b-g6e-qlora-seed42
base: google/gemma-4-E4B-it
method: QLoRA, rank 32, alpha 64, max_seq_length 2048
```

Training completed and early-stopped:

```text
initial val loss: 1.1104
step 20 val loss: 0.3130  # best checkpoint
step 40 val loss: 0.3421
step 60 val loss: 0.4147
step 80 val loss: 0.4951
early stop: val rose for 3 evals
```

Interpretation: this run is useful as a behavior-smoke adapter, not as a
production-quality model. The dataset is intentionally small after validation
gating, so fast convergence mostly means the adapter fit a narrow contract
shape. The important question is whether it preserves resolver/follow-up/source
discipline in held-out smoke tests.

Operational note: the full 167-case eval was too slow at batch size 1 on the
L40S, so it was interrupted after 10 cases. A bounded quick eval was launched
instead with 24 gold cases and 8 LLM-judge cases. The script uploaded the
checkpoint, logs, and quick eval report to the HF repo, then shut the instance
down.

Quick eval result:

```text
eval label: sft_v6_e4b_g6e_qlora_seed42_quick24
grounded n: 24
chrF mean: 19.29
url_recall: 0.50
wrongly_refused: 8/24 = 33.3%
LLM judge: 4 correct, 2 partial, 2 incorrect
judge groundedness mean: 3.62/5
judge citation correctness mean: 4.50/5
judge helpfulness mean: 3.38/5
Roman-NE degen: 0/10
```

Decision: do not deploy this adapter as the main composer. It improved the
Roman-Nepali degeneration signal, but still refuses too many answerable
grounded cases and does not reliably use the expected source URLs. For the demo
or product path, keep the API composer / deterministic resolver in front, and
use this adapter only as evidence that the v6 contract direction is trainable
but under-covered.

Observed failure modes in the 24-case smoke:

- refusal-tail contamination: the model sometimes gives a source-backed answer
  and then appends `मलाई यो प्रश्नको आधिकारिक स्रोत भेटिनँ`, which makes the
  answer both confusing and scored as a wrong refusal;
- true one-chunk refusal: several answerable single-source questions were
  answered with only the refusal sentence;
- weak source extraction: some Jiri/tax/local-profile cases cited the right
  document but failed to extract the requested number or date;
- script mismatch remains possible: at least one Roman-Nepali question was
  answered in Devanagari.

Next data pass should therefore add focused counterexamples:

- answerable one-chunk prompts where the correct behavior is concise extraction,
  not refusal;
- anti-tail examples where the assistant must stop after the sourced answer and
  not append a fallback refusal;
- Roman-Nepali prompts that preserve Roman output unless the user asks for
  Nepali script;
- exact-number/date/contact extraction tasks from noisy PDF chunks.

Repair seed file started from the failed smoke cases:

```text
seeds/service_eval_v6_repair_seed.jsonl
```

## 2026-05-16 v6.1 Repair Pass

The v6 quick eval showed the old dataset was badly imbalanced:

```text
corpora/sft_v6_train.jsonl
answer: 4
partial: 51
follow_up: 8
refuse: 7
off_domain: 2
```

That explains the refusal habit: answerable, source-supported cases were almost
absent from the clean train split.

New v6.1 artifacts:

```text
scripts/build_v6_1_repair_seed_from_gold.py
scripts/distill_planner_composer_v6_gold.py
seeds/service_eval_v6_1_gold_repair_seed.jsonl
corpora/sft_v6_1_gold_grounded_contracts.jsonl
corpora/sft_v6_1_gold_grounded_train.jsonl
corpora/sft_v6_1_gold_grounded_val.jsonl
corpora/sft_v6_1_train.jsonl
corpora/sft_v6_1_val.jsonl
```

The important change is `distill_planner_composer_v6_gold.py`: it uses the
reviewed gold eval chunks as the provided Sources. This isolates composer/SFT
behavior from retrieval misses. Live-RAG distillation is still useful, but it
should not be the only repair data path because a retrieval miss teaches a
refusal even when the held-out gold set proves the question is answerable.

Clean v6.1 combined split:

```text
train: 194 rows
  answer: 126
  partial: 51
  follow_up: 8
  refuse: 7
  off_domain: 2

val: 14 rows
  answer: 10
  partial: 3
  refuse: 1
```

Generated but excluded rows still matter as future data-quality work:

- raw URL leakage;
- contact source IDs missing;
- answer text with blocking-gap/refusal language despite answerability;
- exact phone/date/contact validator edge cases.

Training run started on playground L40S:

```text
instance: i-08dd7181446403e17
repo: voidash/gemma-helpdesk-v6-1-e4b-g6e-qlora-seed42
run label: sft_v6_1_e4b_g6e_qlora_seed42
base: google/gemma-4-E4B-it
method: QLoRA, rank 32, alpha 64, max_seq_length 2048
eval: quick48, judge-n 12, max-new-tokens 220
shutdown: automatic after HF upload
```

v6.1 training/eval result:

```text
status: early_stop_val_divergence
best step: 50
initial val: 1.0249
step 25 val: 0.2181
step 50 val: 0.1936  # best
step 75 val: 0.1958
step 100 val: 0.2231
step 125 val: 0.2257  # early stop

quick48 grounded eval:
chrF mean: 16.53
url_recall: 0.27
wrongly_refused: 7/48 = 14.6%
judge: 6 correct, 3 partial, 3 incorrect
judge groundedness mean: 3.67/5
judge citation correctness mean: 4.08/5
judge helpfulness mean: 3.50/5
Roman-NE degen: 0/10
```

Comparison to v6 quick24:

```text
wrong refusals improved: 33.3% -> 14.6%
Roman-NE remains clean: 0/10 degeneration
judge correct stayed flat: 50%
URL/citation behavior is still bad and inconsistent
```

Decision: still not deployable as the main composer. v6.1 confirms the dataset
balance fix helps the refusal habit, but the model still cites inconsistently
(`[1]`, raw URLs, sometimes no citation) and misses/rewrites exact source facts.
The next pass should train citation normalization explicitly and evaluate
source IDs separately from raw URL recall; deployment should remain API/RAG
composer plus deterministic resolver/extractors.

## 2026-05-16 v6.2 Citation-Control Pass

v6.2 targets the narrow failure left by v6.1: source formatting and refusal-tail
control. It does not try to solve corpus coverage or exact extraction by
memorization.

New artifact:

```text
scripts/build_sft_v6_2_control.py
corpora/sft_v6_2_control_rows.jsonl
corpora/sft_v6_2_train.jsonl
corpora/sft_v6_2_val.jsonl
```

The control builder starts from the reviewed v6.1 gold-grounded contracts and
adds four targeted row types:

```text
v6_2_source_id_final_answer
v6_2_rewrite_numeric_citations
v6_2_rewrite_raw_url_citations
v6_2_rewrite_refusal_tail
```

Combined split:

```text
train: 438 rows
  answer: 370
  partial: 51
  follow_up: 8
  refuse: 7
  off_domain: 2

val: 34 rows
  answer: 30
  partial: 3
  refuse: 1
```

Quality checks on generated v6.2 rows:

```text
assistant raw URLs: 0
assistant numeric citations like [1]: 0
product source citations like [S1]: present
```

The grounded eval script was updated to understand product-style `[S#]`
citations by mapping source IDs back to candidate chunk URLs for `url_recall`.
The eval prompt was also corrected to ask for `[S#]` citations instead of raw
URL citations; otherwise v6.2 would have been tested against the opposite
contract from its training target.

Training run:

```text
instance: i-08dd7181446403e17
type: g6e.xlarge / L40S
repo: voidash/gemma-helpdesk-v6-2-e4b-g6e-qlora-seed42
base: google/gemma-4-E4B-it
method: QLoRA, rank 32, alpha 64, max_seq_length 2048
eval: quick48, judge-n 12, max-new-tokens 220
shutdown: automatic after HF upload
```

v6.2 training/eval result:

```text
status: early_stop_val_divergence
wall time: 1495s
best step: 210
initial val: 0.7175
best val: 0.0844
aborted at step: 360

quick48 grounded eval:
chrF mean: 18.58
url_recall: 0.42
wrongly_refused: 6/48 = 12.5%
raw URL citations in model output: 0
numeric [1] citations in model output: 0
source-ID citations in model output: 34

judge: 7 correct, 2 partial, 3 incorrect
judge groundedness mean: 3.83/5
judge citation correctness mean: 5.00/5
judge helpfulness mean: 3.83/5
Roman-NE degen: 0/10
```

Comparison to v6.1 quick48:

```text
wrong refusals improved: 14.6% -> 12.5%
judge correct improved: 50.0% -> 58.3%
judge citation correctness improved: 4.08/5 -> 5.00/5
url_recall improved: 0.27 -> 0.42
Roman-NE remains clean: 0/10 degeneration
```

Decision: still not deployable as the main composer. v6.2 did fix the narrow
citation-format class: no raw URLs and no `[1]` citations appeared in quick48,
and judge citation correctness hit 5/5. But the model still misses the product
bar: wrong refusals remain above the 10% gate, source recall is far below the
0.70 gate, and many non-refusal answers omit `[S#]` citations entirely. This
adapter is useful evidence that targeted control rows work, not a replacement
for the API/RAG composer.

Next pass should add:

- mandatory-citation final-answer rows where every non-refusal answer must end
  factual sentences with `[S#]`;
- exact-extraction rows for numbers, dates, offices, and contacts;
- hard negative rows where refusal is correct, so the model does not learn to
  answer everything;
- service-dialogue rows that ask compact follow-ups before answering ambiguous
  government-service questions.

## 2026-05-16 v6.3 Control Pass

v6.3 tried to add the missing control classes from the v6.2 notes. This was a
deliberate stress test of whether one adapter can learn citation discipline,
exact extraction, hard negatives, and compact follow-up behavior at once.

New artifacts:

```text
scripts/build_sft_v6_3_control.py
scripts/run_v6_3_g6_qlora.sh       # L4 attempt, failed OOM
scripts/run_v6_3_g6e_qlora.sh      # L40S run
corpora/sft_v6_3_control_rows.jsonl
corpora/sft_v6_3_train.jsonl
corpora/sft_v6_3_val.jsonl
```

The builder starts from v6.2 train/val plus the reviewed v6.1 gold-grounded
contracts and adds:

```text
v6_3_mandatory_sentence_citations
v6_3_exact_value_extraction
v6_3_eval_failure_repair
v6_3_hard_negative_refusal
v6_3_service_dialogue_followup
```

Generated control rows:

```text
total: 190
mandatory citations: 66
exact extraction: 51
hard negative refusal: 35
eval failure repair: 28
dialogue follow-up: 10
```

Combined split:

```text
train: 613 rows
  answer: 504
  partial: 51
  refuse: 39
  follow_up: 17
  off_domain: 2

val: 49 rows
  answer: 41
  refuse: 4
  partial: 3
  follow_up: 1
```

Quality checks on generated v6.3 rows:

```text
assistant raw URLs: 0
assistant numeric citations like [1]: 0
answer rows missing [S#]: 0
source-ID citations in control rows: 323
```

Operational notes:

```text
uploaded data repo commits:
  train: e6dc46cfac7961c1c2d6aeec0e7087105da05fb4
  val:   429c30949173c61c5d8ff204a2430a47116da746

L4 g6.xlarge:
  instance: i-0f210f33f60b4f3ef
  repo: voidash/gemma-helpdesk-v6-3-e4b-g6-qlora-r16-seed42
  result: failed CUDA OOM even with LoRA rank 16

L40S g6e.xlarge capacity:
  us-east-1a: no capacity after polling
  us-east-1c: no capacity
  us-east-1d: no capacity
  us-east-1b: launched
```

Training run:

```text
instance: i-08847ed5c7763e607
az: us-east-1b
type: g6e.xlarge / L40S
repo: voidash/gemma-helpdesk-v6-3-e4b-g6e-qlora-seed42
base: google/gemma-4-E4B-it
method: QLoRA, rank 32, alpha 64, max_seq_length 2048
eval: quick48, judge-n 12, max-new-tokens 220
shutdown: automatic after HF upload
```

v6.3 training/eval result:

```text
status: early_stop_val_divergence
wall time: 1055s
initial val: 1.0509
best val: 0.1758
best step: 150
aborted at step: 240

quick48 grounded eval:
chrF mean: 15.69
url_recall: 0.92
wrongly_refused: 38/48 = 79.2%
raw URL citations in model output: 0
numeric [1] citations in model output: 0
source-ID citations in model output: 139

judge: 4 correct, 6 partial, 2 incorrect
judge groundedness mean: 3.92/5
judge citation correctness mean: 4.33/5
judge helpfulness mean: 3.00/5
Roman-NE degen: 10/10
Roman-NE loops: 10/10
```

Decision: v6.3 failed and must not be deployed. The high URL recall is not a
real product improvement because the model often answers with citations and
then appends or loops refusal/gap language. The Roman-Nepali smoke completely
regressed into repeated fallback text. v6.2 remains the better control adapter,
although it is also not main-composer deployable.

Root cause: v6.3 mixed too many refusal/hard-negative/follow-up examples into
the final-answer composer. That made the composer better at attaching source
IDs, but it also taught the model to add fallback refusal language after
otherwise answerable outputs. Hard negatives are still useful, but they should
train a resolver/classifier or planner gate, not be mixed heavily into the
final composer.

Next pass:

- keep hard-negative/refusal rows out of the final-answer composer, or route
  them into a separate planner/refusal classifier task;
- train the composer mostly on answerable, source-backed rows with explicit
  stop-after-answer examples;
- add anti-tail rows where the wrong answer contains a fallback refusal and the
  target answer removes it;
- add a Roman-Nepali replay gate before accepting a checkpoint;
- keep exact extraction, but do it with answerable contexts only;
- stop treating source recall alone as a success metric; refusal-tail and loop
  checks must be blocking gates.

## 2026-05-16 v6.4 Split-Task Pass

v6.4 is the direct response to the v6.3 failure. The key change is not "more
data"; it is separating behaviors that should not be learned as one final
composer habit.

New artifacts:

```text
scripts/build_sft_v6_4_split_task.py
scripts/run_v6_4_g6e_qlora.sh
corpora/sft_v6_4_split_control_rows.jsonl
corpora/sft_v6_4_train.jsonl
corpora/sft_v6_4_val.jsonl
```

Task split:

- planner JSON learns resolver/intake, follow-up, source classes, expected
  domains, retrieval queries, and gaps;
- answerability JSON learns hard negatives and source-pack insufficiency;
- final composer learns answer, partial answer, compact follow-up, and harmless
  off-domain steering only;
- exact extraction rows are answerable source-backed values only.

Important rule: hard-negative free-form refusals are intentionally kept out of
the final composer. That was the v6.3 contamination path.

Build result on k2:

```text
base kept: 468
v6.3 positive controls: 155
planner rows: 578
dialogue response rows: 180
hard-negative JSON rows: 48
control rows: 543
all rows: 950
train: 877
val: 73
```

Final split counts:

```text
answer: 484
partial: 54
follow_up: 92
off_domain: 16
planner: 253
refuse: 4
refuse_json: 47
```

Quality gate:

```text
assistant raw URLs: 0
assistant numeric citations like [1]: 0
bad JSON task outputs: 0
free-form composer refusal marker rows: 0
Hindi artifacts in Roman/English prompts: 0
long message rows >24k chars: 0
```

Training plan:

```text
base: google/gemma-4-E4B-it
instance: g6e.xlarge / L40S
repo: voidash/gemma-helpdesk-v6-4-e4b-g6e-qlora-seed42
method: QLoRA, rank 32, alpha 64, max_seq_length 2048
epochs: 3 with early-stop by val divergence
step checkpoints: 90,150,210,270,330,420,500
eval: quick48, judge-n 12, max-new-tokens 220
shutdown: automatic after HF upload
```

Acceptance bar is behavioral, not just val loss:

- Roman-Nepali smoke must not loop or switch to Hindi;
- wrong refusals must improve over v6.2 and stay below the product gate;
- source-ID citation format must remain clean;
- answerable one-source questions must answer instead of falling back;
- follow-up examples should ask compact slot questions while still giving
  useful routing/contact context.

Training/eval result:

```text
instance: i-08847ed5c7763e607
type: g6e.xlarge / L40S
repo: voidash/gemma-helpdesk-v6-4-e4b-g6e-qlora-seed42
status: completed train + quick48 eval, artifacts uploaded to HF
best val: 0.0969 at step 450
final val: 0.1031 at step 657
wall time in trainer: 2956.5s
```

The training report JSON currently labels the run `INCOMPLETE` even though
`abort_reason` is null and the final checkpoint/eval artifacts exist. Treat
that as a report-writer status bug; the log says training completed 657 steps
and final eval ran.

Quick48 result:

```text
grounded n: 48
chrF mean: 24.60
url_recall: 0.94
wrongly_refused: 2/48 = 4.2%
raw URL citations: 0 rows
numeric [1] citations: 0 rows
source-ID citations: 45/48 rows

judge n: 12
correct: 6
partial: 5
incorrect: 1
groundedness mean: 4.00/5
citation correctness mean: 4.58/5
helpfulness mean: 4.17/5

Roman-NE qualitative:
degen: 0/10
loops: 0/10
mojibake: 0/10
```

Decision: v6.4 is the first adapter that clears the previous quick48 gates:
wrong refusals below 10%, source recall above 0.70, no Roman loops, no raw URL
or numeric citations in grounded eval. It is a serious candidate for
RAG-backed composer testing.

Caveat: the standalone Roman qualitative prompts still often produce fallback
refusals when no source context is provided. That is acceptable only if the
model is used behind the resolver/RAG planner and not as a naked general
chatbot. Before deployment, run the service-navigator pipeline smoke with this
adapter and compare against the base/API composer on real RAG source packs.

Private k2 deployment and checkpoint sweep:

```text
date: 2026-05-16
k2 host: <k2-tailnet-ip>
private port: 8001
public port 8000: left untouched
model: google/gemma-4-E4B-it
adapter root: /Volumes/T9/gemma-god/adapters/gemma-helpdesk-v6-4-e4b-g6e-qlora-seed42
selected private checkpoint: best
health: ok, model_loaded=true, db_loaded=true
```

Real pipeline smoke against private k2 `best`:

```text
eval/reports/service_navigator_pipeline_v64_best_private_20260516.jsonl  8/8
eval/reports/navigator_smoke_v64_best_private_20260516.jsonl             7/7
eval/reports/rag_query_v64_best_private_20260516.jsonl                   15/15

rag_query refused: 1/15 expected unknown-source case
bad citations: 0/15
loops: 0/15
slow generation: 0/15
```

Focused 8-case service pipeline sweep:

```text
step210  8/8
step270  8/8
step330  8/8
step420  8/8
best     8/8
step500  8/8
final    8/8
```

Important caveat: those service-pipeline cases mostly took deterministic
resolver/composer paths (`generation=0`). They prove retrieval, source routing,
follow-up, contact extraction, and fallback guards. They do not by themselves
rank adapter decoding quality.

Direct CUDA decode sweep:

```text
report: eval/reports/sweep_v6_4_decode_20260516.json
instance: i-08847ed5c7763e607, playaround, g6e.xlarge/L40S
instance state after run: stopped

step210  5/6  failed naked no-source Jiri mayor prompt
step270  6/6
step330  6/6
step420  6/6
best     6/6
step500  6/6
final    6/6
```

Decode sweep caveat: the original scoring was too permissive for the naked
Jiri mayor prompt. On inspection, several passing checkpoints hallucinated a
mayor name when no source pack was supplied. Source-backed contact prompts were
grounded and cited correctly. Therefore v6.4 should be deployed only behind
resolver/RAG; the naked adapter is not trustworthy as a factual chatbot.

Deployment decision: keep private k2 port `8001` on `best` for RAG-backed
testing. `best` has the strongest prior quick48 evidence, passes the real
pipeline gates, and behaves well when supplied source packs. Do not expose it
as a public naked model endpoint.
