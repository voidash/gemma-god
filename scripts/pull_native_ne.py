#!/usr/bin/env python3
"""Pull a Nepali-instruction subset from `Saugatkafley/alpaca-nepali-sft` for
the SFT v1 training mix's "native Nepali anchor" slice.

Note on source: ai4bharat/indic-align Anudesh has very thin Nepali coverage
(~0.4% of records in our smoke). Saugatkafley is translated Alpaca but
provides 52K records of real Devanagari surface form, which is what we
need for the anchor slice's purpose: stop the model from drifting toward
DeepSeek's stylistic biases by mixing in a second teacher's output style.

Output schema matches `generate_sft_grounded.py` SFT format:
    {
      "id": "sft_native_ne_00001",
      "source": "saugatkafley_alpaca_ne",
      "question": "...",
      "question_lang": "devanagari",
      "category": "other",
      "chunks": [],
      "answer": "...",
      "skip": false
    }

Usage:
    python scripts/pull_native_ne.py --n 1500 --seed 42
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import re
import sys
from pathlib import Path

DEVA_RE = re.compile(r"[ऀ-ॣ॰-ॿ]")
LATIN_RE = re.compile(r"[A-Za-z]")


def is_devanagari_dominant(text: str, ratio_threshold: float = 0.4) -> bool:
    """At least 40% of letter-like chars should be Devanagari to pass."""
    deva = len(DEVA_RE.findall(text))
    latin = len(LATIN_RE.findall(text))
    if deva + latin == 0:
        return False
    return deva / (deva + latin) >= ratio_threshold


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1500)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--output", default="corpora/sft_v1_native_ne.jsonl")
    ap.add_argument("--min-chars", type=int, default=20)
    ap.add_argument("--max-chars", type=int, default=4000)
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    try:
        from datasets import load_dataset
    except ImportError:
        print("missing: pip install datasets", file=sys.stderr)
        return 1

    logging.info("loading Saugatkafley/alpaca-nepali-sft …")
    ds = load_dataset("Saugatkafley/alpaca-nepali-sft", split="train")
    logging.info("dataset size: %d records", len(ds))

    rng = random.Random(args.seed)
    indices = list(range(len(ds)))
    rng.shuffle(indices)

    out: list[dict] = []
    inspected = 0
    skipped_bad = 0
    skipped_short = 0
    skipped_long = 0
    skipped_non_deva = 0

    for i in indices:
        if len(out) >= args.n:
            break
        inspected += 1
        rec = ds[i]
        instr = (rec.get("instruction") or "").strip()
        inp = (rec.get("input") or "").strip()
        outp = (rec.get("output") or "").strip()
        if not instr or not outp:
            skipped_bad += 1
            continue

        # Compose question + answer. Alpaca records sometimes have a separate
        # "input" field; if present, append to question (Alpaca's normal format).
        question = instr if not inp else f"{instr}\n\n{inp}"
        answer = outp

        # Filters
        full_text = question + " " + answer
        if len(full_text) < args.min_chars:
            skipped_short += 1
            continue
        if len(question) > args.max_chars or len(answer) > args.max_chars:
            skipped_long += 1
            continue
        if not is_devanagari_dominant(full_text, ratio_threshold=0.3):
            skipped_non_deva += 1
            continue

        out.append(
            {
                "id": f"sft_native_ne_{len(out) + 1:05d}",
                "source": "saugatkafley_alpaca_ne",
                "question": question,
                "question_lang": "devanagari",
                "category": "other",
                "chunks": [],
                "answer": answer,
                "skip": False,
                "skip_reason": None,
                "gold_chunk_id": None,
            }
        )

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n=== native-NE pull summary ===", file=sys.stderr)
    print(f"  inspected: {inspected}", file=sys.stderr)
    print(f"  kept     : {len(out)}", file=sys.stderr)
    print(f"  skipped  : empty={skipped_bad} short={skipped_short} long={skipped_long} non_deva={skipped_non_deva}", file=sys.stderr)
    print(f"  output   : {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
