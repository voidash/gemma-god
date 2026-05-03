#!/usr/bin/env python3
"""Assemble the v4 English replay slice from multi-seed TULU pulls.

Each `corpora/sft_v4_tulu_seed{42,100,200,300}.jsonl` pull lands on a
different shard cluster (TULU 3's parquet shards are source-clustered;
streaming.shuffle only randomizes within the loaded shard's window — see
scripts/pull_tulu_subset.py for the caveat).

This script:
  1. Reads all sft_v4_tulu_seed*.jsonl present
  2. Deduplicates by question text (occasional cross-shard overlap)
  3. Reports the source-dataset distribution so we can verify we got a
     mix of math (numinamath), instruction (no_robots), MC (flan), and
     reasoning (sciriff) — codex v4 spec
  4. Samples down to --n records (default 3000)
  5. Writes corpora/sft_v4_english_replay.jsonl

Run AFTER all sft_v4_tulu_seed*.jsonl pulls have completed.
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import random
import sys
from collections import Counter
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in-pattern", default="corpora/sft_v4_tulu_seed*.jsonl")
    ap.add_argument("--out", default="corpora/sft_v4_english_replay.jsonl")
    ap.add_argument("--n", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    paths = sorted(glob.glob(args.in_pattern))
    if not paths:
        print(f"ERROR: no files match {args.in_pattern}", file=sys.stderr)
        return 1
    logging.info("input files: %s", paths)

    seen_q: set[str] = set()
    pool: list[dict] = []
    src_count: Counter = Counter()
    file_contrib: Counter = Counter()
    for p in paths:
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                q = (r.get("question") or "").strip()
                if not q or q in seen_q:
                    continue
                seen_q.add(q)
                pool.append(r)
                src_count[r.get("src_dataset") or "?"] += 1
                file_contrib[Path(p).name] += 1

    logging.info("dedup pool: %d records", len(pool))
    logging.info("by file:")
    for name, n in file_contrib.most_common():
        logging.info("  %-40s %d", name, n)
    logging.info("by src_dataset:")
    for src, n in src_count.most_common():
        logging.info("  %-50s %d", src, n)

    rng = random.Random(args.seed)
    rng.shuffle(pool)
    sampled = pool[:args.n]

    # Re-id and standardize source for v4 attribution.
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for i, r in enumerate(sampled, 1):
            r["id"] = f"sft_v4_eng_{i:05d}"
            r["source"] = "v4_english_replay"
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    sampled_src = Counter(r.get("src_dataset") or "?" for r in sampled)
    print(f"\n=== assemble_v4_english_replay ===", file=sys.stderr)
    print(f"  inputs       : {len(paths)} files, {len(pool)} dedup records", file=sys.stderr)
    print(f"  sampled      : {len(sampled)} → {out_path}", file=sys.stderr)
    print(f"  by src_dataset (sampled):", file=sys.stderr)
    for src, n in sampled_src.most_common():
        print(f"    {n:>5d} {src}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
