# PreVillage Benchmarks

This directory is the reviewer-facing benchmark entry point. The operational
eval scripts still live in `scripts/` and some historical eval files still live
under `eval/`, but the important public benchmark data is mirrored here.

Unless a row explicitly points to an upstream source with different terms, the
benchmark files published from this project should use `license: cc-by-4.0`.

## Included Benchmarks

| File | Purpose |
| --- | --- |
| `gov_helpdesk_gold_v1.jsonl` | Source-grounded government helpdesk gold set. Rows include questions, candidate chunks, reviewed gold answers, and source URLs. |
| `dev_guard_v4.jsonl` | Development guard set used to catch regression-prone service and language behavior. |
| `service_navigator_pipeline_smoke.jsonl` | Resolver/intake smoke cases: follow-up behavior, memory, routing, source domains, and no-generation paths. |
| `navigator_smoke.jsonl` | Lightweight navigator checks for common service-routing behavior. |
| `rag_query_smoke.jsonl` | End-to-end RAG answer smoke cases for high-demand services. |
| `service_matrix_smoke.jsonl` | Small cross-service matrix for areas like citizenship, vital registration, passport, PAN, and contacts. |
| `service_coverage_matrix.md` | Human-readable coverage matrix used to decide where crawling and evals were still weak. |

## How To Run The Main Gates

From the repository root:

```bash
python scripts/service_navigator_pipeline_audit.py
python scripts/navigator_smoke_audit.py
python scripts/rag_query_audit.py
python scripts/rag_retrieval_audit.py
python scripts/corpus_health_audit.py
```

The final public writeup reports these smoke gates:

```text
service pipeline: 8/8
navigator smoke: 7/7
RAG query audit: 15/15 with one expected refusal
bad citations: 0
generation loops: 0
slow-generation failures in smoke set: 0
```

## Benchmark Philosophy

These are product evals, not just model-loss checks. A good answer must use the
right source class, ask compact follow-ups when jurisdiction or case type
matters, avoid Hindi drift for Nepali users, cite source IDs/URLs from provided
evidence, and refuse only when the source pack truly does not support an
answer.
