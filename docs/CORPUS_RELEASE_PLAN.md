# Corpus Release Plan

The government corpus should be released, but not as an unreviewed dump.

## Recommendation

Publish a public, versioned **official-source corpus** on Hugging Face Datasets
and mirror a lightweight copy on Kaggle.

Use `license: cc-by-4.0` for the dataset card, with a provenance note that
source URLs point back to official government pages and that any upstream
third-party material keeps its own terms.

Hugging Face is better for reproducible ML/RAG workflows: dataset versions,
Parquet/JSONL loading, model-card links, and programmatic access. Kaggle is
better for hackathon judges and notebook-style exploration. Use Hugging Face as
the canonical dataset and Kaggle as the submission-friendly mirror.

The small source-controlled front door is [`../datasets/`](../datasets/). It
contains the public source registry and district routing hints, not the full
document/chunk export.

## What To Publish

Start with a "lite" official-source release:

```text
source_registry.jsonl
documents.parquet
chunks.parquet
crawl_manifest.json
checksums.txt
README.md / dataset card
```

Fields should include:

- source ID, domain, homepage URL, office name, office type, province/district;
- document URL, title, MIME type, crawl timestamp, content hash;
- extracted text chunks, language/script hints, chunk index, source/date fields;
- parser/OCR status and any known extraction warnings;
- source freshness and dedupe metadata.

## What Not To Publish Yet

Do not include these in the first public corpus release:

- private WhatsApp auth state or message logs;
- raw interview recordings, consent forms, or unpublished practical notes;
- personal phone numbers that are not already official public contacts;
- generated SFT records containing private prompts or unreleased model outputs;
- raw PDFs if licensing/redistribution status is unclear.

Human practical sources should be a separate reviewed dataset with explicit
consent status and public/private fields. The public version can include named
officer/staff/citizen guidance only when consent and verification are clear.

## Why Not Just GitHub

The full crawl and chunk data will be too large and too frequently regenerated
for source control. Git should contain code, recipes, small registries, eval
seeds, and documentation. Dataset platforms should contain versioned corpus
artifacts.

## First Release Checklist

1. Export from the current SQLite/FTS corpus into Parquet and JSONL.
2. Remove private/tacit/interview rows unless explicitly approved for public
   release.
3. Keep official public contact info only when it came from public office pages.
4. Include source URLs and crawl timestamps so every chunk is auditable.
5. Add a dataset card explaining provenance, limitations, stale-source risk,
   language/script quality, `license: cc-by-4.0`, and takedown/contact process.
6. Upload to `voidash/previllage-nepal-gov-corpus` on Hugging Face.
7. Create a Kaggle mirror with the same README and a small starter notebook.
