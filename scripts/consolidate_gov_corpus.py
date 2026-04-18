#!/usr/bin/env python3
"""Re-shape survey/corpus_chunks.jsonl into the CPT-corpus format.

The BM25 ingestion emitted chunks (~600 chars each) with char_start/end
offsets within the full document. For CPT we want clean text records with
provenance tagging — the tokenizer+pack step will concatenate / window.

Output schema (one JSON object per line):
    {
      "source": "gov",
      "tier":        "A" | "BPreeti" | "Mixed" | "C" | "E",
      "doc_id":      filename,
      "source_url":  original gov URL (if known),
      "text":        chunk text,
      "tokens_est":  rough token estimate (char_count // 3 for Nepali)
    }
"""

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", default="survey/corpus_chunks.jsonl")
    ap.add_argument("--out", default="corpora/gov_nepali.jsonl")
    args = ap.parse_args()

    in_path = Path(args.in_path)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not in_path.is_file():
        print(f"error: {in_path} not found — run cargo run --bin ingest first", file=sys.stderr)
        return 2

    kept = 0
    total_chars = 0
    by_tier: dict[str, int] = {}

    with in_path.open() as f_in, out_path.open("w", encoding="utf-8") as f_out:
        for line in f_in:
            line = line.strip()
            if not line:
                continue
            chunk = json.loads(line)
            text = chunk.get("text", "").strip()
            if not text:
                continue
            tier = chunk.get("tier", "")
            # Keep only tiers that contribute Nepali pretraining fuel.
            # - A / BPreeti / Mixed / C contain Nepali content (converted from
            #   Preeti or OCR'd from scans).
            # - E is English-only gov content (bid notices, English Acts, OCR
            #   service manuals) — not useful for improving Nepali generation.
            #   Dedicated English-replay corpora (fineweb-edu) serve that
            #   purpose better.
            # - BLegacyUnknown / XInvalid / Unknown are skipped upstream.
            if tier not in ("A", "BPreeti", "Mixed", "C"):
                continue
            record = {
                "source": "gov",
                "tier": tier,
                "doc_id": chunk.get("doc_id", ""),
                "source_url": chunk.get("source_url"),
                "text": text,
                "tokens_est": len(text) // 3,  # rough
            }
            f_out.write(json.dumps(record, ensure_ascii=False) + "\n")
            kept += 1
            total_chars += len(text)
            by_tier[tier] = by_tier.get(tier, 0) + 1

    print(f"kept chunks: {kept:,}", file=sys.stderr)
    print(f"total chars: {total_chars:,} ({total_chars/1024/1024:.1f} MB)", file=sys.stderr)
    print(f"token estimate (chars/3): {total_chars//3:,}", file=sys.stderr)
    print("by tier:", file=sys.stderr)
    for t, c in sorted(by_tier.items(), key=lambda x: -x[1]):
        print(f"  {t:<18} {c:>8,}", file=sys.stderr)
    print(f"output: {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
