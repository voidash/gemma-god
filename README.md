# gemma-god

A domain-specific question-answering engine over Nepali government knowledge,
built for the Gemma hackathon. The working hypothesis: middlemen charge
citizens because procedural information is tacit, not documented. An engine
that properly surfaces this knowledge — with page-level citations, conversational
clarification, and a path to acquire what it doesn't know — can reduce that
tax.

**Status: work in progress.** Scope is deliberate: answer 50 common gov
questions with verifiable citations *deeply* before trying to answer 500
*shallowly*.

## Architecture (current and planned)

```
User (Nepali or Romanized or code-mixed)
    │
    ▼
Understanding Layer (Gemma 3 4B)              ← planned
    ├── normalize script (IndicXlit)
    ├── intent classify
    ├── entity extract
    └── decide: clarify | retrieve | dispatch outreach agent
    │
    ▼
Retrieval Layer
    ├── BM25 (current)                        ← shipped
    ├── dense (BGE-M3) + hybrid rerank        ← planned
    │
    ▼
Generation Layer (Gemma 3 4B)                 ← planned
    ├── grounded JSON output
    ├── per-claim verbatim citations
    ├── numeric-entity verbatim verifier
    ├── abstain-if-weak-evidence
    │
    ▼
Answer + (doc_id, page, snippet, link#page=N) citations
```

## What's shipped

A Rust corpus pipeline for Nepali gov PDFs:
- **Classifier** — per-tier detection (`A | BPreeti | BLegacyUnknown | C |
  E | Mixed | XInvalid`), with layered checks for legacy Nepali fonts.
- **Preeti / legacy-font converter** — ports the GPL-3.0 `casualsnek/npttf2utf`
  mapping to Rust; adds per-block conversion for mixed docs.
- **OCR** — Tesseract (Nepali `tessdata_best`) for scanned PDFs.
- **Crawler** — TLS-tolerant discovery of new PDFs from gov index pages.
- **Ingestion** — per-tier extraction and chunking to JSONL.
- **BM25 retrieval** — sub-second query over ~46k chunks.

See `PLAN.md` for the month-sized execution plan and `DOCUMENT.md` for the
ongoing engineering log.

## Layout

```
Cargo.toml               Rust crate manifest
src/
├── lib.rs
├── main.rs              CLI entrypoint: `gemma-god classify`
├── detector.rs          tier classifier
├── legacy_fonts.rs      Preeti / Kantipur / ... → Unicode converter
├── ocr.rs               Tesseract pipeline
├── crawler.rs           TLS-tolerant fetcher + link extractor
└── bin/
    ├── validate_converter.rs  batch validation harness
    ├── ocr_batch.rs           Tier C OCR driver
    ├── crawler.rs             seed-page discovery
    ├── ingest.rs              per-tier text extraction + chunking
    ├── build_index.rs         BM25 index builder
    └── query.rs               CLI retrieval
tests/integration.rs     ground-truth assertions against samples
scripts/
└── nepali_baseline.py   Gemma 3 Nepali benchmark harness
survey/
├── sites.yaml           enumerated gov sites with metadata
├── observations.md      round-1 domain findings
├── gemma3_nepali_smoke.md  Gemma 3 smoke-test results
└── ...                  (classification outputs, crawler state, etc.)
third_party/
└── npttf2utf/           embedded mapping table (GPL-3.0, attribution preserved)
PLAN.md                  forward-looking plan
DOCUMENT.md              engineering log
```

## Building

```bash
cargo build --release
cargo test
```

External tools expected on PATH: `pdftotext`, `pdfinfo`, `pdftoppm`, `tesseract`
(+ `nep.traineddata`). On macOS via MacPorts / Homebrew.

## Licensing

Code under this repo: see `LICENSE` (TBD).
Vendored `third_party/npttf2utf/` retains its upstream GPL-3.0 license.

## Not a medical / legal authority

Output is for informational use only. Users should verify any action-taking
information (fees, forms, office addresses, deadlines) with the relevant
government office before acting on it. The engine emits a freshness warning
whenever cited sources are old, and a confidence score on every answer.
