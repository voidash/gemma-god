# gemma-god — Engine Plan

A proper domain-specific question-answering engine for Nepali government knowledge. Not a hackathon demo. Target: working system by hackathon date (~1 month from 2026-04-18). Rust core + Gemma 3 + outreach-capable agent layer.

---

## 0. Revised vision — what we are actually building

**Not** a RAG chatbot. An **agentic knowledge engine** with four properties:

1. **Page-level provenance.** Every answer cites `(doc, page, verbatim snippet, link#page=N)`. Page number + 2–3 sentence snippet is the citation granularity. Character-bbox tracking is explicitly scoped out as over-engineering.
2. **Conversational understanding.** The engine can push back on vague queries. An elderly user's half-formed question triggers clarifying turns, not a wild-guess search. Retrieval is downstream of understanding.
3. **Closed-loop gap handling.** When the corpus lacks coverage, the engine can dispatch an AI agent to acquire the knowledge via WhatsApp / voice / email to the key contact persons listed on each gov site.
4. **Trust-aware ingestion.** Acquired knowledge never enters the authoritative corpus blind. It's tagged by provenance (`scraped` / `converted` / `ocr` / `human-verified` / `agent-acquired`), scored for confidence, and surfaced for human approval before being canonical.

## 1. What's shipped (Phases 1–F, done 2026-04-18)

| Phase | Deliverable | State |
|---|---|---|
| 1 | Corpus survey — 15 Nepal gov sites enumerated; CDN + TLS + Preeti findings | ✅ `survey/sites.yaml`, `survey/observations.md` |
| A | Rust classifier: tier A / BPreeti / BLegacyUnknown / C / E / Mixed / XInvalid | ✅ `src/detector.rs` + 9 ground-truth tests |
| B | Preeti → Unicode converter (GPL-3.0 npttf2utf port) | ✅ `src/legacy_fonts.rs` |
| C | Per-block `convert_mixed` — preserves English + Devanagari | ✅ + 8 new tests |
| D | Tesseract Nepali OCR pipeline for Tier C | ✅ `src/ocr.rs`, `nep.traineddata` installed |
| E | Continuous-refresh crawler, TLS-tolerant, revalidation | ✅ `src/crawler.rs` + `src/bin/crawler.rs` |
| F | Ingestion → BM25 index → query end-to-end | ✅ 46 026 chunks indexed, sub-second query |

**Verified working:** query `"company registration"` → OCR e-service PDFs; query `"आर्थिक वर्ष"` → NRB Preeti-converted circulars; `"PAN tax"` → SEBON 2019 policy.

## 2. What's NOT shipped — open work organized by layer

### 2.1 Provenance layer
- [ ] Page-aware chunking: split at PDF page boundaries, store `page_num` per chunk
- [ ] Snippet extraction: rendered citation string of 2–3 sentences around match span
- [ ] URL fragment anchors: `#page=N` (or `#page=N&zoom=page-fit` for PDF.js viewers)
- [ ] Provenance propagation: retriever → answer → UI always carries `(doc_id, page, snippet, url#page=N, verified_at, verified_via)`
- [ ] Content-hash-based deduplication across near-duplicate docs (NRB re-issues same circular in two places)

### 2.2 Semantic retrieval layer
- [ ] BGE-M3 embeddings (via Ollama or ONNX Runtime in Rust)
- [ ] Hybrid search: BM25 ∪ dense → reciprocal-rank fusion → cross-encoder rerank (top 100 → top 10)
- [ ] Query expansion via Gemma 3 (single user query → 3–5 paraphrases covering gov-doc terminology)
- [ ] Cross-lingual: Romanized Nepali → Devanagari normalization, English query → Nepali corpus retrieval
- [ ] Negative queries / filter terms: `fiscal year 2082 NOT 2081`

### 2.3 Understanding layer (the "ask-back engine")
- [ ] Query intent classifier (Gemma 3): procedural / definitional / fee-lookup / form-finder / form-help / off-topic
- [ ] Entity extraction: agency, procedure, location, document, timeframe
- [ ] Clarifying-question generator: when intent or entity is ambiguous, engine emits a Nepali clarifying question instead of answering
- [ ] Multi-turn dialog state: which entities are locked in, which are open, what did the user already tell us
- [ ] Conversation reset + explicit "start over" handling
- [ ] Romanized-Nepali + code-switched input normalization

### 2.4 Generation layer (Gemma 3)
- [ ] Gemma 3 4B local serving (Ollama for dev, vLLM for prod later)
- [ ] Grounded answer prompt template: retrieved chunks + query → JSON output with per-claim citations
- [ ] Abstention-trained behavior: "मलाई यो जानकारी छैन, [contact] मा सम्पर्क गर्नुहोस्" as first-class output
- [ ] Numeric/entity verbatim verification post-generation
- [ ] Confidence score: high (all chunks agree) / medium (partial) / low (single weak chunk)
- [ ] Freshness warning: newest citation older than N months → visible caveat
- [ ] SFT dataset construction (~1 500 examples: grounded / partial / abstain / clarifying)
- [ ] LoRA fine-tune via Unsloth on Colab/local GPU

### 2.5 Acquisition / outreach layer (the new addition from this conversation)
- [ ] Gap detector: logs queries with no high-confidence answer to `survey/gaps.jsonl`
- [ ] Contact-person directory: extract from each gov site (we already have phone/email from round 1)
- [ ] Agent-driven outreach:
  - [ ] WhatsApp channel via WhatsApp Business API (Meta) or Twilio
  - [ ] Voice channel via Vapi or Bland AI or Retell AI (**research required — see §4**)
  - [ ] Email channel (simpler baseline — send query to `info@ministry.gov.np`, parse reply)
- [ ] Agent conversation script: identifies itself, states purpose, asks specific question, captures answer, thanks, hangs up
- [ ] Transcript → structured-fact extraction via Gemma 3
- [ ] Human approval queue: acquired facts require Nepali reviewer sign-off before entering canonical corpus
- [ ] Duplicate-contact throttle: don't call same officer >1/week
- [ ] Disclosure compliance: log that caller is AI, respect "do not call" opt-outs

### 2.6 Evaluation layer
- [ ] Adversarial Nepali eval set (200 Q, 4 buckets: answerable / stale-but-answerable / OOD-should-abstain / wrong-premise-trap)
- [ ] Metrics: answer accuracy, citation correctness, abstention rate on OOD, hallucinated-number rate, average turns-to-answer
- [ ] Per-tier retrieval recall (A / BPreeti / Mixed / C)
- [ ] Shadow traffic: real user queries logged (anonymized) for ongoing evaluation
- [ ] User-test with 5 elderly Nepalis by week 4 (**only real signal for "old-man usability"**)

### 2.7 UI surface
- [ ] Web chat (week 4, primary demo)
- [ ] Telegram/Viber bot (week 5, for real Nepal reach — Viber ~50% penetration)
- [ ] Voice interface (stretch, post-month)

## 3. Gemma 3 integration — research notes

### 3.1 Model family as of 2026-04

| Variant | Params | Context | Modalities | Best use |
|---|---|---|---|---|
| Gemma 3 1B | 1B | 32k | text only | constrained edge; too weak for Nepali reasoning alone |
| **Gemma 3 4B** | 4B | 128k | text + vision | **laptop + dev default** — Nepali-capable, local-runnable |
| Gemma 3 12B | 12B | 128k | text + vision | better Nepali, needs 24 GB+ VRAM or 4-bit quant |
| Gemma 3 27B | 27B | 128k | text + vision | rented GPU only; probably overkill |
| Gemma 3n E2B | ~2B effective | 32k | text (mobile) | on-device mobile app |
| Gemma 3n E4B | ~4B effective | 32k | text (mobile) | mid-range on-device |

Gemma 3 was trained on 140+ languages including Nepali. Quality on Nepali is usable but not native. Empirical check needed before committing — a 50-question Nepali smoke test should precede any fine-tune investment.

### 3.2 Function / tool calling in Gemma 3

- Native support. The model outputs JSON-structured tool calls in a specific chat template when prompted with tool definitions.
- Format: tool definitions go in the system prompt as JSON schemas. Model outputs `<function_call>{...}</function_call>` (or equivalent wrapper depending on serving stack).
- Supported by Ollama, vLLM, and HF Transformers; each has slightly different wrappers. Ollama has a JSON-mode for structured output.
- For our use: define tools for `search_corpus`, `clarify_with_user`, `dispatch_outreach_agent`, `lookup_office_contact`, `emit_final_answer`. The model routes each turn.

### 3.3 Deployment options

| Stack | Latency | Setup | Best for |
|---|---|---|---|
| **Ollama + Gemma 3 4B** (local) | ~50 tok/s on M2/M3 | `ollama run gemma3:4b` | **default for dev** |
| llama.cpp + GGUF 4-bit | ~30–80 tok/s CPU/GPU | manual but portable | pure CPU demo |
| MLX + Gemma 3 4B (Apple Silicon) | ~80 tok/s on M2 Max | Python, Apple-only | fastest on Mac |
| vLLM on rented GPU | 200+ tok/s | Docker, needs Nvidia | multi-user production |
| Vertex AI / Together.ai | remote | API key | no-infra serverless |

**Integration with Rust core:** call Ollama's HTTP endpoint (`localhost:11434/api/generate` or `/api/chat`) directly — simpler than embedding inference. Latency is fine for interactive QA.

### 3.4 Fine-tuning plan

- Base: Gemma 3 4B instruct (4B-it)
- Method: LoRA via Unsloth (one-file Python, free Colab T4 works for 4B)
- Dataset: ~1 500 examples covering:
  - 500 grounded-answer (context + question → cited JSON answer)
  - 500 partial-context (some info present, flag what isn't, ask or cite)
  - 300 abstention (off-corpus question → refusal with redirect)
  - 200 clarifying (vague question → clarifying Nepali question)
- Evaluation: held-out 300 adversarial-eval set (see §2.6)
- Cost: ~6 hours on free Colab; $30 on L4 if needed

## 4. AI outreach agent research — Bailey's agent ambiguity

**Clarification needed:** "Bailey's agent" — the exact product you're referencing is not immediately recognizable to me. Best candidates based on what fits:

| Product | Channel | Strengths | Nepal-relevant |
|---|---|---|---|
| **Bland AI** | voice (phone) | programmable voice agents, webhook-based, tool-calling | yes if you can afford per-minute |
| **Vapi** | voice + WebRTC | similar to Bland, more customizable | yes |
| **Retell AI** | voice | lowest latency, good for interactive | yes |
| **Twilio + own LLM** | voice / SMS / WhatsApp | most flexible, DIY | works in Nepal (ported numbers) |
| **WhatsApp Business API** | WhatsApp | official Meta API, requires business verification | **best for Nepal — everyone uses WhatsApp** |
| **Gmail API + Gemma 3** | email | free, trivial, useful baseline | works now |

**My recommendation** for this project given Nepal context:

1. **Start with email** — cheapest, no compliance surprise, gov contacts already have email addresses we harvested in round 1. Week-5 task: auto-draft a Nepali inquiry, send to `info@ministry.gov.np`, poll inbox, parse reply.
2. **Add WhatsApp next** — most Nepali gov officers check WhatsApp constantly, don't answer office phones. Requires WhatsApp Business API setup (~1 week) + Meta verification.
3. **Voice last** — per-minute cost, compliance risk (Nepal telecom rules on AI callers unclear), callee fatigue.

**Confirm which platform you meant by "Bailey's" so I don't pick wrong.** If it's a specific product I've missed, please share a link and I'll research it deeper.

## 5. Updated architecture

```
          ┌────────────────────────────────────────────────────┐
          │                   USER (Nepali)                    │
          │    "राहदानी फेर्न के लगछ? मेरो ५ वर्ष पुग्यो"       │
          └────────────────────────────┬───────────────────────┘
                                       ▼
                ┌──────────────────────────────────────────┐
                │ Understanding Layer (Gemma 3 4B)         │
                │  - Normalize (Romanized→Devanagari)      │
                │  - Intent classify                       │
                │  - Entity extract                        │
                │  - Decide: clarify | retrieve | outreach │
                └────┬──────────────┬───────────────┬─────┘
                     │              │               │
                     │ clarify      │ retrieve      │ gap → outreach
                     ▼              ▼               ▼
              ask user Q    ┌──────────────┐   ┌────────────┐
                            │ Retrieval    │   │ Outreach   │
                            │ BM25+Dense+  │   │ agent:     │
                            │ rerank       │   │ WhatsApp/  │
                            │ → top-K +    │   │ email/voice│
                            │  page+snip   │   │ → transcript│
                            └──────┬───────┘   └──────┬─────┘
                                   │                   │
                                   │      ┌────────────┘
                                   ▼      ▼
                            ┌──────────────────────────┐
                            │ Generation (Gemma 3 4B)  │
                            │ grounded, cited, JSON    │
                            │ + verbatim verify        │
                            │ + abstain if weak        │
                            │ + freshness warning      │
                            └──────────┬───────────────┘
                                       ▼
                            ┌──────────────────────────┐
                            │ Answer + (doc,page,snip, │
                            │ link#page=N) citations   │
                            └──────────────────────────┘

Background loops:
 - Crawler (weekly)             → urls_discovered.txt
 - Gap detector (continuous)    → gaps.jsonl → outreach queue
 - Human review (daily)         → approved facts enter canonical corpus
```

## 6. Week-by-week execution plan (4 weeks, assumes ~20 focused hours/week)

### Week 1 — Provenance correctness
- Rebuild chunking to be page-aware
- Per-tier per-page text extraction with page number preserved
- Citations: `(doc_id, page_num, snippet, source_url#page=N)`
- BM25 index updated with new schema
- Ground truth: top-3 results of existing test queries still correct, plus page numbers now shown

### Week 2 — Semantic retrieval + query understanding
- BGE-M3 via Ollama or ONNX
- Hybrid BM25 + dense + RRF
- Gemma 3 4B via Ollama: integration test + smoke test on Nepali
- Query rewriter: raw Nepali → 3 paraphrases + intent tag
- Clarifier: vague-query detector + clarifying question generator

### Week 3 — Generation, abstention, SFT
- Gemma 3 grounded-answer prompt + JSON schema
- Build ~1 500 SFT examples (semi-synthetic via Claude/GPT + human-QA'd sample)
- LoRA fine-tune on Colab
- Numeric/entity verbatim verifier post-gen
- Freshness gate

### Week 4 — Eval, outreach MVP, demo
- 200-Q adversarial eval
- Gap detector → gaps.jsonl
- Email-based outreach MVP (send Nepali inquiry, parse reply, extract fact, queue for review)
- Minimal web UI: Nepali chat, citations shown with page anchors
- Optional: 5 elderly Nepali users test the web UI

### Post-month (stretch, v2)
- WhatsApp Business API outreach
- Voice outreach (Vapi/Bland) if compliance path is clear
- Structured knowledge graph layer extracted from corpus
- Telegram / Viber bot for Nepal reach
- Shadow traffic + online learning from real queries

## 7. Decision forks — answer these before week 1

1. **Embedding compute** — local GPU (what card?) / rented GPU / CPU-only via Ollama nomic-embed?
2. **Gemma 3 serving** — Ollama for dev fine; for production hosting plan → laptop / rented GPU / Vertex AI?
3. **Outreach platform** — what did you mean by "Bailey's agent"? If unclear, do we start with email (free, boring, effective) or commit to WhatsApp Business API (~1 week setup, real reach)?
4. **Fine-tune compute** — free Colab T4 for LoRA fits 4B; do you have time to supervise the run or do we rent an L4 for speed?
5. **User testing access** — do you have 5 elderly Nepali users available for week 4? If not, we're guessing at UX.
6. **Team size** — is this you solo, or do you have a reviewer / Nepali QA partner? Changes week-4 outreach approval workflow.

## 8. Non-goals for month one (explicit)

- Structured knowledge-graph extraction from PDFs
- PDF character-bbox highlighting
- Autonomous agent acquisition without human approval
- Mobile app (native Android/iOS)
- Voice interface (input via voice, output via voice)
- Multi-user auth / accounts
- Scaling beyond one Rust process / one Gemma instance

---

*Last updated: 2026-04-18. Source of truth. Update this file when scope changes.*
