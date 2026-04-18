#!/usr/bin/env python3
"""Pack per-source corpora into train/valid JSONL for mlx-lm LoRA CPT.

Reads each source JSONL from --corpora-dir, samples each slice up to its
token budget, shuffles across slices, and emits `train.jsonl` + `valid.jsonl`
with the `{text: ...}` schema mlx-lm expects.

Token estimation uses the `tokens_est` field each ingest script already
populated (char-count divided by a language-appropriate factor). Precise
tokenization happens at training time via the Gemma 3 tokenizer.

Usage:
    python scripts/pack_cpt_corpus.py [--corpora-dir DIR] [--out-dir DIR]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

SEED = 42

# Slice definitions. Each entry: {file, target_tokens, filter_fn (optional)}.
# None for target_tokens means "take everything available".
SLICES: list[dict[str, Any]] = [
    {"name": "gov_nepali",       "file": "gov_nepali.jsonl",       "target": None},
    {"name": "wikipedia_ne",     "file": "wikipedia_ne.jsonl",     "target": 20_000_000},
    {"name": "reddit_roman_ne",  "file": "reddit_nepali.jsonl",    "target": 10_000_000,
     "filter": lambda r: r.get("lang") == "roman_nepali"},
    {"name": "reddit_devanagari","file": "reddit_nepali.jsonl",    "target": 3_000_000,
     "filter": lambda r: r.get("lang") == "devanagari"},
    {"name": "reddit_code_mixed","file": "reddit_nepali.jsonl",    "target": 2_000_000,
     "filter": lambda r: r.get("lang") == "code_mixed"},
    {"name": "alpaca_nepali",    "file": "alpaca_nepali.jsonl",    "target": 4_000_000},
    {"name": "english_replay",   "file": "english_replay.jsonl",   "target": 16_000_000},
]

VALID_PCT = 5  # % held out for validation


def load_slice(path: Path, target_tokens: int | None, filter_fn=None, seed: int = SEED) -> tuple[list[str], int]:
    """Load texts from a JSONL file, filter + sample, return (texts, total_tokens_est).

    `tokens_est` is read from each record (set by the producing script); for
    sampling we shuffle and take records until we reach the token budget.
    """
    if not path.is_file():
        print(f"  SKIP {path.name}: not found", file=sys.stderr)
        return [], 0

    all_records: list[tuple[str, int]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if filter_fn is not None and not filter_fn(r):
                continue
            text = (r.get("text") or r.get("body") or "").strip()
            if not text:
                continue
            est = r.get("tokens_est")
            if est is None or est <= 0:
                # Fallback: rough char/3 for Devanagari, char/4 for ASCII
                deva = sum(1 for c in text if "\u0900" <= c <= "\u097F")
                est = (deva // 3) + ((len(text) - deva) // 4)
            all_records.append((text, int(est)))

    rng = random.Random(seed)
    rng.shuffle(all_records)

    kept_texts: list[str] = []
    total = 0
    if target_tokens is None:
        # Use everything available
        for text, est in all_records:
            kept_texts.append(text)
            total += est
    else:
        for text, est in all_records:
            if total >= target_tokens:
                break
            kept_texts.append(text)
            total += est

    return kept_texts, total


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpora-dir", default="/Volumes/T9/gemma-god/corpora")
    ap.add_argument("--out-dir", default="/Volumes/T9/gemma-god/cpt_data")
    ap.add_argument("--valid-pct", type=float, default=VALID_PCT)
    args = ap.parse_args()

    corpora = Path(args.corpora_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(SEED)

    # Load each slice
    all_texts: list[tuple[str, str]] = []  # (slice_name, text)
    slice_summary: list[dict[str, Any]] = []
    for slc in SLICES:
        path = corpora / slc["file"]
        print(f"\n=== {slc['name']}  ({slc['file']}) ===", file=sys.stderr)
        texts, tokens = load_slice(
            path,
            slc.get("target"),
            filter_fn=slc.get("filter"),
        )
        print(f"  records kept: {len(texts):,}  tokens_est: {tokens:,}", file=sys.stderr)
        for t in texts:
            all_texts.append((slc["name"], t))
        slice_summary.append({
            "name": slc["name"],
            "records": len(texts),
            "tokens_est": tokens,
            "target_tokens": slc.get("target"),
        })

    # Shuffle across slices
    rng.shuffle(all_texts)

    # Train/valid split
    n = len(all_texts)
    n_valid = max(100, int(n * args.valid_pct / 100))
    valid = all_texts[:n_valid]
    train = all_texts[n_valid:]

    train_path = out_dir / "train.jsonl"
    valid_path = out_dir / "valid.jsonl"

    with train_path.open("w", encoding="utf-8") as f:
        for _slc, text in train:
            f.write(json.dumps({"text": text}, ensure_ascii=False) + "\n")
    with valid_path.open("w", encoding="utf-8") as f:
        for _slc, text in valid:
            f.write(json.dumps({"text": text}, ensure_ascii=False) + "\n")

    total_tokens = sum(s["tokens_est"] for s in slice_summary)
    print(f"\n=== packed corpus ===", file=sys.stderr)
    print(f"total records: {n:,}  (train {len(train):,} / valid {len(valid):,})", file=sys.stderr)
    print(f"total tokens_est: {total_tokens:,}  ({total_tokens/1e6:.1f}M)", file=sys.stderr)
    print("\nper-slice:", file=sys.stderr)
    for s in slice_summary:
        pct = 100 * s["tokens_est"] / max(1, total_tokens)
        print(f"  {s['name']:<22}  records={s['records']:>7,}  tokens={s['tokens_est']:>11,}  ({pct:.1f}%)",
              file=sys.stderr)
    print(f"\noutput: {train_path}  ({train_path.stat().st_size/1024/1024:.1f} MB)", file=sys.stderr)
    print(f"output: {valid_path}  ({valid_path.stat().st_size/1024/1024:.1f} MB)", file=sys.stderr)

    # Manifest for reproducibility
    manifest_path = out_dir / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump({
            "seed": SEED,
            "valid_pct": args.valid_pct,
            "total_records": n,
            "total_tokens_est": total_tokens,
            "train_records": len(train),
            "valid_records": len(valid),
            "slices": slice_summary,
        }, f, indent=2)
    print(f"manifest: {manifest_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
