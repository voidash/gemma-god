# SFT v5 postmortem and next pass

Snapshot: 2026-05-14.

This document records the result of the 2026-05-13 v5 E4B run and the new
direction for the next SFT pass. Read this before generating more SFT data,
training another adapter, or deploying any v5 checkpoint.

## Bottom line

Do not deploy the v5 E4B adapter trained on
`corpora/sft_v5_recipe_round1_train.jsonl`.

The run technically completed and produced checkpoints, but smoke testing shows
the adapter is not reliable enough for SpeakGov. It learned cleaner style in
some cases, but it still invents facts, gives generic procedures when follow-up
questions are required, and misroutes some government services. That is worse
than a weak model when the product is a public-service navigator.

The next SFT pass should not train the model to know government facts. It should
train the model to behave as a planner/composer over provided context:

- resolve intent and missing slots;
- decide whether retrieval/source context is sufficient;
- ask compact follow-up questions;
- use only provided source snippets/source IDs;
- say uncertainty and gaps plainly;
- avoid Hindi drift, loops, chain-of-thought leakage, and generic filler.

Exact facts such as phone numbers, office holders, fees, URLs, and dates should
come from deterministic extraction or source-grounded RAG, not from adapter
memory.

## Run summary

Training run:

```text
base: google/gemma-4-E4B-it
method: BF16 LoRA on g6e.xlarge / NVIDIA L40S 46 GB
seed: 42
train: corpora/sft_v5_recipe_round1_train.jsonl
val: corpora/sft_v5_recipe_round1_val.jsonl
HF repo: voidash/gemma-helpdesk-seed42
```

Artifacts uploaded:

```text
voidash/gemma-helpdesk-seed42
  ckpt/step100/
  ckpt/best/
  ckpt/final/
  ckpt/state.json
  ckpt/training_report.json
  eval/sft_v5_recipe_e4b_seed42/
  smoke/v5_adapter_smoke_all.json
```

Training metrics:

```text
initial val loss: 3.3477
step 100 val loss: 0.3832
best/final step: 183
best val loss: 0.2522
status in report: INCOMPLETE
abort_reason: null
```

The low validation loss was misleading. It selected for the training surface
form, not product behavior.

## Capacity and recipe notes

An attempted `g6.xlarge` / NVIDIA L4 24 GB path was not viable:

- BF16 full-load path crawled and was near memory limits.
- QLoRA with 4-bit NF4, LoRA r=32/alpha=64, max sequence 1536 loaded, but OOMed
  on first backward pass.
- E4B training for this recipe needs the 48 GB `g6e.xlarge`/L40S path or a much
  smaller model/shorter sequence/lower-rank experiment.

Do not spend more time trying to force this E4B recipe onto L4 for training.
L4 can be used for slow 4-bit smoke/inference when capacity is unavailable.

## Eval result

The post-train eval summary reported:

```text
eval/sft_v5_recipe_e4b_seed42/SUMMARY.md

Full Gold: grounded n=0, refusal n=0
Belebele: 0/50
GSM8K: 0/30
Roman-NE degen: 10/10
```

This summary is partly an eval-harness failure because full-gold results were
empty, but it is still a hard stop. The model failed the regression slices and
the adapter required manual smoke before any deployment decision.

## Manual smoke test

Smoke artifact:

```text
voidash/gemma-helpdesk-seed42/smoke/v5_adapter_smoke_all.json
```

The smoke compared:

- base `google/gemma-4-E4B-it` in 4-bit;
- `step100`;
- `best`;
- `final`.

Prompts:

```text
how to get citizenship in Sankhuwasabha?
who to contact when i got cheated by manpower agency?
जिरी नगरपालिकाको नगर प्रमुख को हुन्?
birth certificate in Jiri
ma Qatar ma chu passport renew garna paryo
2 + 2 kati ho?
```

### Base

The base model was not acceptable as-is:

- leaked `thought` / chain-of-thought-like text;
- emitted stray Japanese/Thai/CJK tokens;
- mixed language oddly;
- asked some useful follow-ups, but was too unstable for production.

### Step 100

`step100` was worse than base on factual reliability:

- invented `Jiri Birth Registration Office contact number: 9801234567`;
- gave wrong Qatar passport guidance;
- botched harmless off-domain math by saying it could not give an official
  answer and included both `2 + 2 = 2` and `2 + 2 = 4`;
- gave a generic citizenship checklist without asking the necessary case
  follow-ups.

Do not use `step100`.

### Best and final

`best` and `final` behaved almost identically. They were cleaner stylistically
than base/step100, but still not deployable:

- citizenship in Sankhuwasabha: answered with a generic checklist instead of
  asking municipality/ward and case type first;
- manpower complaint: routed to FEB/Ministry wording when DOFE-first handling
  should be primary for agency cheating/complaints;
- Jiri mayor: did not answer from RAG/contact data and only said to contact the
  municipality;
- Jiri birth certificate: said "Jirimun", dragged in DAO Dolakha for
  birth-related services, and made source-unsupported claims;
- Qatar passport renewal: too vague and failed to route clearly to the Embassy
  of Nepal, Doha / passport portal context;
- math off-domain: acceptable short answer.

Do not use `best` or `final` on `helpdesk.ampixa.com`.

## Product decision

For the hackathon/demo path:

1. Use RAG plus a strong API composer as the main answer path.
2. Keep deterministic extractors for high-confidence exact facts.
3. Keep the small/local model out of production answers unless it passes the
   behavior gates below.
4. Treat SFT as planner/composer distillation, not as factual knowledge
   injection.

The demo advantage is the service navigator and RAG stack: resolver, source
routing, contacts, follow-up, and evidence. A weak local adapter can make the
product worse if it invents a contact or procedure.

## New SFT target

The next SFT model should learn the following tasks.

### 1. Resolver/intake task

Input:

- raw user message;
- recent chat memory;
- optional known slots.

Output:

- structured service/action/location/case slots;
- missing slots;
- compact follow-up question;
- partial contacts/source classes if known.

This should be trained as JSON and as final plain-chat response. Production can
use the JSON planner output internally.

### 2. Source-grounded composer task

Input:

- resolved user question;
- chat memory;
- retrieved source pack with `S1`, `S2`, etc.;
- source metadata: domain, title, date, source class, locality, confidence;
- distractor sources.

Output:

- concise answer using only source IDs;
- no raw URLs;
- unsupported details listed as missing/uncertain;
- follow-up checklist when answerability depends on user slots;
- contact handoff when relevant.

The model should not be rewarded for knowing facts absent from the source pack.

### 3. Answerability/source-selection contract

Train explicit contract rows separately from user-facing answer rows:

```json
{
  "answerability": "answer | partial | follow_up | refuse | off_domain",
  "relevant_source_ids": ["S1"],
  "irrelevant_source_ids": ["S2"],
  "facts": [
    {"claim": "...", "source_ids": ["S1"]}
  ],
  "missing_slots": ["municipality", "ward", "case_type"],
  "missing_sources": ["current ward-level checklist"],
  "recommended_next_action": "ask_follow_up | answer | source_discovery"
}
```

This is the main fix for the v5 failure. The model needs to learn visible
decisions, not only final answer prose.

### 4. Language and safety regularizer

Add explicit negatives and positives for:

- no Hindi unless user uses Hindi;
- no chain-of-thought markers;
- no stray CJK/Thai/Japanese tokens;
- no loops;
- harmless off-domain answers are brief and correct;
- answer in the user's script/style when possible.

## Data mix for the next pass

Do not reuse `sft_v5_recipe_round1_train.jsonl` as-is for another full run.

Recommended pilot mix before any 8k+ scale-up:

```text
planner/contract rows                 40%
source-grounded answer rows           25%
multi-turn service mini-flows         15%
source-discovery / insufficient RAG   10%
language/off-domain/replay            10%
```

Important changes from the failed run:

- down-weight final-answer-only rows;
- remove/refactor rows that teach the model to invent contacts or generic
  procedures;
- add more refusal-boundary and partial-answer cases with distractor sources;
- add back-and-forth examples where the model asks and then uses the answer;
- include deterministic exact-fact examples as extraction-from-source tasks,
  not memory tasks.

## Training recommendation

Do not repeat the failed recipe:

```text
LR 1e-4
rsLoRA r=64 alpha=128
2 epochs
checkpoint selected by val loss
```

Next pilot:

```text
LR: 2e-5 to 3e-5
LoRA rank: 16 or 32
epochs: 1 max
checkpoint every 25 or 50 optimizer steps
select by smoke/eval behavior, not val loss
```

Use `g6e.xlarge`/L40S for E4B. For E2B, run the same behavioral gates first;
E2B may be enough if the task is planner/composer over context instead of fact
memorization.

## Required eval gates

A checkpoint cannot be deployed unless it passes these smoke/eval gates:

- asks follow-up for ambiguous citizenship/passport/vital-registration cases;
- gives DOFE-first guidance for manpower-agency cheating;
- does not invent phone numbers, office names, fees, or URLs;
- answers harmless math correctly and briefly;
- no Hindi when the user did not ask Hindi;
- no `thought`, chain-of-thought, or foreign-token leakage;
- exact contact/person questions are source-backed or routed to deterministic
  extraction;
- citations/source IDs only reference retrieved context;
- wrong locality sources are rejected;
- Roman Nepali does not loop or collapse.

Minimum smoke prompts should include the six used above plus:

```text
who is information officer of Jiri municipality?
Jiri municipality phone number
police clearance online Nepal
lost citizenship certificate duplicate in Sankhuwasabha
driving license renew in Pokhara
PAN card kasari banaune?
passport renew in Doha Qatar
birth registration ward ma ke document chaincha?
```

## Immediate next steps

1. Keep `helpdesk.ampixa.com` on the RAG/API-composer path, not v5 adapter.
2. Build/patch the SFT data generator so every example is planner/contract-first.
3. Generate a small 200-record pilot with Claude/Sonnet or Opus using the live
   RAG source pack.
4. Manually audit 30-50 records before training.
5. Train a short checkpoint sweep with the gentler recipe.
6. Run the smoke gate before any full eval or deployment discussion.
