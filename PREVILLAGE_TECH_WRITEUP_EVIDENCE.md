# PreVillage Technical Writeup Evidence

Snapshot: 2026-05-18.

This is the engineering-first evidence pack for the Gemma 4 Good writeup. The
writeup should not read like a clean product story. It should show the real
technical path: failed checkpoints, eval gates, RAG hardening, cost, and the
decision to move facts out of weights and into source-backed retrieval.

## Tech Images To Use First

Use these before the softer story/product images.

| Image | What it proves |
|---|---|
| `assets/previllage-writeup-gallery/tech/aws_cost_reality_20260518.png` | Project-attributable GPU/storage cost, with unrelated account-level EBS explicitly excluded. |
| `assets/previllage-writeup-gallery/tech/sft_iteration_reality.png` | CPT/SFT was iterative and failure-driven, not a single lucky training run. |
| `assets/previllage-writeup-gallery/tech/v6_progression_metrics.png` | The v6 line improved only after task separation. |
| `assets/previllage-writeup-gallery/tech/v6_4_training_command.png` | Real training command, hardware, rank, sequence length, checkpoint cadence, and QLoRA setup. |
| `assets/previllage-writeup-gallery/tech/rag_service_eval_gates.png` | Real service/RAG pipeline smoke reports, not a manually staged answer. |
| `assets/previllage-writeup-gallery/tech/failure_modes_smoke_tests.png` | The writeup should show the exact wrong behaviors that forced the architecture change. |
| `assets/previllage-writeup-gallery/tech_contact_sheet.jpg` | One-page review sheet for the technical gallery. |

## Cost Evidence

Cost Explorer query date:

```text
2026-05-18
```

Query window:

```text
Start=2026-05-01
End=2026-05-19
metric=UnblendedCost
```

Cost caveats:

- Cost Explorer end date is exclusive.
- The 2026-05-18 day may still be incomplete depending on AWS billing delay.
- These accounts are not project-tag-clean, so totals are account totals, not
  perfectly attributable project totals.
- The GPU-ish number is grouped from visible GPU instance usage types, not an
  official project tag allocation.

Profiles checked:

```text
playaround
devnet-staging
```

Account-level month-to-date result:

```text
playaround account total:      $811.07
devnet-staging account total:  $455.29
```

Do not use those account totals as PreVillage/Gemma project cost. They include
other shared resources.

Project-attributable compute we can defend:

| Profile | Attributable line | Cost | Basis |
|---|---:|---:|---|
| `playaround` | GPU-ish EC2 compute | `$173.44` | visible May usage for `g6e.xlarge`, `g6.xlarge`, and small related GPU usage used by Gemma/G2P runs |
| `devnet-staging` | GPU-ish EC2 compute | `$190.19` | May `g6e.xlarge`/`g4dn.xlarge` GPU usage from the earlier training/smoke phase |
| combined | GPU-ish EC2 compute | `$363.63` | Cost Explorer usage-type grouping, not project tags |

Project-attributable playaround storage we can defend from current named
training resources:

```text
g2p-piper-train-root-300gb          500 GB baseline gp3
gemma-v4b-train-playaround-root     200 GB baseline gp3
gemma-v5dlg500-42-root              200 GB baseline gp3
gemma-v5recipe-e4b-g6-root          200 GB baseline gp3
gemma-v5recipe-e4b-g6e-root         200 GB baseline gp3
gemma-v6-4-g6e-root                 200 GB baseline gp3
```

Estimated accrued storage for those named playaround training volumes through
the same billing window is about `$38.48`, with ongoing baseline cost around
`$120/month` if the 1.5 TB remains attached. This is an estimate from volume
sizes/create times and gp3 storage pricing, because Cost Explorer was not cleanly
tagged by project.

Explicitly excluded from PreVillage/Gemma cost:

```text
instance: i-08c5e2e93d93c010a
name: mosaic-sapin
type: r7a.2xlarge

vol-066085fca1b4bcc90  500 GB  gp3  80000 IOPS  2000 MB/s
vol-080a1e04cb88925ca 2048 GB  gp3  80000 IOPS  2000 MB/s
tags on 2 TB volume: Team=Mosaic, Owner=Sapin, Jira=STR-3058
```

Those two Mosaic/Sapin volumes explain most of the `playaround` EBS bill:

```text
EBS:VolumeP-IOPS.gp3       $415.01
EBS:VolumeP-Throughput.gp3 $ 80.85
EBS:VolumeUsage.gp3        $138.82
```

They should not be counted as our project spend. They are still useful as an
ops warning, but only as "shared account noise discovered during cost review."

Writeup framing:

> The defensible project cost is GPU compute plus the storage attached to the
> named Gemma/G2P training machines. The huge playaround EBS line was not ours:
> it came from unrelated Mosaic/Sapin high-IOPS gp3 volumes in the same shared
> account. That finding still matters operationally because it shows why
> project cost must be tagged, not inferred from account totals.

Do not claim:

```text
PreVillage spent $1266 on AWS.
PreVillage spent $634 on playaround EBS.
```

Safe claim:

```text
Measured May month-to-date GPU-ish EC2 compute across the two checked accounts
was $363.63. Named playaround training volumes add roughly $38.48 of accrued
baseline storage in the same window. Unrelated shared-account storage was
excluded.
```

## Training Reality

### CPT v1

Source:

```text
BENCHMARKS.md
DOCUMENT.md
```

Evidence:

- Belebele baseline fell from about `63%` to `52%`.
- FLORES English-to-Nepali chrF fell from `38.15` to `33.46`.
- Roman-Nepali degeneration/loops appeared.

Technical interpretation:

```text
CPT on an instruction-tuned model with mostly raw Nepali text caused
catastrophic forgetting of chat behavior.
```

### SFT v2

Source:

```text
SFT_V2_RESULTS.md
```

Important configuration:

```text
base: google/gemma-4-E2B-it
records: 11,896
hardware: 1x L40S / g6e.xlarge
method: LoRA via PEFT, rsLoRA
r / alpha: 64 / 128
optimizer: AdamW 8-bit
LR: 1e-4
schedule: cosine + 100-step warmup
effective batch: 16
best step: 600
```

Result:

- Refusal improved from `0/91` to `12/91`.
- Roman-Nepali degen improved to `0/10`.
- URL recall held at `0.89`.
- chrF regressed to `13.42`.
- Helpfulness remained weak.

### SFT v3a

Source:

```text
SFT_V3A_RESULTS.md
```

Configuration:

```text
base: google/gemma-4-E2B-it
records: 13,763
refusal share: 18.2%
LR: 1e-4
r / alpha: 64 / 128
hardware: L40S / g6e.xlarge
train wall: 2h51m
eval wall: 52m
```

Result:

- Refusal rose to `16/91`.
- chrF improved to `18.03`.
- Roman-Nepali degen returned at `3/10`.
- GSM8K collapsed from `60%` to `23%`.
- Eval judge silently broke because DeepSeek thinking mode was not disabled.

Technical lesson:

```text
The slice mechanism worked, but a partial-mix SFT still caused regressions.
Behavioral checks must be first-class gates, not post-hoc decoration.
```

### SFT v5

Source:

```text
SFT_V5_POSTMORTEM_AND_NEXT_PASS.md
```

Run:

```text
base: google/gemma-4-E4B-it
method: BF16 LoRA
hardware: g6e.xlarge / NVIDIA L40S 46 GB
train: corpora/sft_v5_recipe_round1_train.jsonl
best val loss: 0.2522
best/final step: 183
repo: voidash/gemma-helpdesk-seed42
```

Capacity lesson:

```text
g6.xlarge / L4 24 GB was not viable for this E4B recipe.
4-bit NF4 QLoRA loaded, but OOMed on first backward pass.
E4B training needed g6e.xlarge / L40S or a smaller model/shorter/rank-lower run.
```

Smoke prompts:

```text
how to get citizenship in Sankhuwasabha?
who to contact when i got cheated by manpower agency?
जिरी नगरपालिकाको नगर प्रमुख को हुन्?
birth certificate in Jiri
ma Qatar ma chu passport renew garna paryo
2 + 2 kati ho?
```

Failure modes:

- Invented a fake Jiri birth registration phone number.
- Answered ambiguous citizenship with a generic checklist instead of asking
  municipality/ward/case type.
- Misrouted manpower-agency cheating.
- Failed to answer Jiri mayor/contact from source data.
- Mixed wrong office context into Jiri birth registration.

Decision:

```text
Do not deploy v5.
Train planner/composer behavior over provided context instead.
```

## v6 Planner/Composer Evidence

Source:

```text
SFT_V6_PLANNER_COMPOSER.md
```

Thesis:

```text
The model should learn behavior over provided context.
It should not memorize government facts as weights.
```

Progression:

| Pass | Train rows | Key result | Decision |
|---|---:|---|---|
| `v6.0` | `72` | quick24 wrong refusals `33.3%`, URL recall `0.50` | under-covered |
| `v6.1` | `194` | wrong refusals `14.6%`, URL recall `0.27` | better refusal balance, still weak citations |
| `v6.2` | `438` | wrong refusals `12.5%`, citation correctness `5/5`, no raw URLs | useful control adapter, not deployable |
| `v6.3` | `613` | URL recall `0.92`, but wrong refusals `79.2%`, Roman loops `10/10` | failed; hard negatives contaminated final composer |
| `v6.4` | `877` | quick48 wrong refusals `4.2%`, URL recall `0.94`, source IDs `45/48`, Roman loops `0/10` | first serious RAG-backed candidate |

v6.4 training command source:

```text
scripts/run_v6_4_g6e_qlora.sh
```

Important hyperparameters:

```text
base: google/gemma-4-E4B-it
instance: g6e.xlarge / L40S
method: QLoRA
load: 4-bit NF4
lora rank: 32
lora alpha: 64
max sequence length: 2048
epochs: 3
per-device batch: 1
gradient accumulation: 4
warmup steps: 10
eval every: 30 optimizer steps
save/push every: 60 optimizer steps
checkpoint steps: 90,150,210,270,330,420,500
```

Critical caveat:

```text
v6.4 should only be shown as a RAG-backed composer candidate.
It is not safe as a naked factual chatbot.
```

## Real Eval Gates

Sources:

```text
eval/reports/service_navigator_pipeline_v64_best_private_20260516.jsonl
eval/reports/navigator_smoke_v64_best_private_20260516.jsonl
eval/reports/rag_query_v64_best_private_20260516.jsonl
eval/reports/sweep_v6_4_decode_20260516.json
```

Summary:

| Report | Result | Notes |
|---|---:|---|
| `service_navigator_pipeline_v64_best_private_20260516.jsonl` | `8/8` | zero issues, average wall time `22416.8 ms` |
| `navigator_smoke_v64_best_private_20260516.jsonl` | `7/7` | zero issues, average wall time `6991.3 ms` |
| `rag_query_v64_best_private_20260516.jsonl` | `15/15` | zero issues, one refusal and it was expected |
| focused checkpoint sweep | `8/8` for `step210`, `step270`, `step330`, `step420`, `best`, `step500`, `final` | proves pipeline paths, not naked model knowledge |

Caveat:

Many service-pipeline cases used deterministic resolver/composer paths. That is
not a weakness; it is the architecture. The product is a service navigator, not
a model memory contest.

## Technical Writeup Shape

The writeup should lead with engineering reality, not polish:

1. The problem is tacit route knowledge, not just missing PDFs.
2. We tried model-first learning and it failed in measurable ways.
3. RAG alone was not enough until resolver/source routing/evals were added.
4. SFT only started working when it became planner/composer behavior over
   source packs.
5. The cost and operational mistakes are real: GPU time was expensive, but
   storage/provisioned IOPS leaked even more.
6. The product is credible because failure gates shaped the architecture.

Useful paragraph:

> The most important engineering result was negative: a model that sounds
> cleaner can be more dangerous. v5 had low validation loss and still invented
> contacts, over-answered ambiguous cases, and misrouted services. v6 only
> became useful after planner, answerability, and final composition were split
> into separate tasks, and even then it is only a RAG-backed composer, not a
> factual model by itself.

Useful caption:

> These are not mock logs. They are the run scripts, eval reports, Cost Explorer
> output, and failed smoke cases that changed the architecture.
