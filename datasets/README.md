# PreVillage Datasets

This directory is the reviewer-facing data entry point. It intentionally holds
small, public, source-controlled dataset artifacts only.

Public dataset releases for this project should use `license: cc-by-4.0`
and link back to the repository `LICENSE` / `NOTICE.md`.

## Included Here

| File | Purpose |
| --- | --- |
| `source_registry_lite.jsonl` | Public source registry used by the resolver/source router. It includes government domains, office names, authority tier guesses, crawl cadence, and manual source-ranking overrides. |
| `nepal_districts.jsonl` | District aliases and District Administration Office domain hints used for jurisdiction routing. |

## Larger Dataset Release

The full government corpus is too large and too frequently regenerated for Git.
The intended public dataset package is:

```text
source_registry.jsonl
documents.parquet
chunks.parquet
crawl_manifest.json
checksums.txt
README.md / dataset card
```

Dataset-card license field:

```yaml
license: cc-by-4.0
```

Canonical target:

```text
https://huggingface.co/datasets/voidash/previllage-nepal-gov-corpus
```

A Kaggle mirror can use the same dataset card and a small starter notebook for
judges.

## What Stays Out

Do not put these in this directory:

- WhatsApp auth state or message logs.
- Raw officer/citizen interviews without consent review.
- Private practical notes or unpublished phone numbers.
- Model checkpoints, adapters, GGUF files, crawl databases, or FTS indexes.
- Generated SFT records that depend on unreleased model outputs or private
  prompts.

The older `corpora/` directory remains in the repo because several scripts
still read those paths directly. Treat `datasets/` as the public data front
door and `corpora/` as the historical/script-compatible working location.
