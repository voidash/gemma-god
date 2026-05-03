#!/usr/bin/env python3
"""Filter the v1/v3 grounded slice (corpora/sft_v1_grounded.jsonl) by joining
each embedded chunk's chunk_id against the cleaned k2 SQLite, dropping any
record where:
  - any chunk is no longer in the current DB (was dropped during the
    mojibake rebuild — its text changed enough that the content-hash chunk_id
    no longer matches)
  - any chunk's `chunks.language` label is `mojibake_suspected` (the new
    src/crawler_v2/language.rs::devanagari_with_hybrid_mojibake_ratio
    classifier at threshold 0.10 caught it)

Codex called this out: my older `audit_mojibake.py` heuristic predates the
in-tree classifier, so reusing it would mis-filter. The DB labels are the
authoritative signal — they're populated by the indexer using the same
classifier the production retriever respects.

Output: corpora/sft_v4_grounded_v3carry.jsonl, same record schema as input
except `source` rewritten to "v4_grounded_v3carry" so format_sft_v4 attributes
correctly.

Usage on k2:
    python3 scripts/filter_v3_grounded_via_db.py \\
        --in corpora/sft_v1_grounded.jsonl \\
        --db /Volumes/T9/gemma-god/corpus_v2/index.db \\
        --out corpora/sft_v4_grounded_v3carry.jsonl

For local runs, the SQLite needs to be reachable — either copy index.db
locally or run via SSH.
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path


CLEAN_LANGS = {"devanagari", "latin", "mixed"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="in_path", default="corpora/sft_v1_grounded.jsonl")
    ap.add_argument("--db", default="/Volumes/T9/gemma-god/corpus_v2/index.db")
    ap.add_argument("--out", default="corpora/sft_v4_grounded_v3carry.jsonl")
    ap.add_argument(
        "--sample", type=int, default=0,
        help="if > 0, randomly sample N records from the kept set (after filtering). "
        "Use to bring v4 grounded count down to the codex 5500 target.",
    )
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    in_path = Path(args.in_path)
    if not in_path.exists():
        print(f"ERROR: input not found: {in_path}", file=sys.stderr)
        return 1
    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: db not found: {db_path}", file=sys.stderr)
        return 1

    # Pass 1: collect all chunk_ids and look up languages in one batched query.
    # This is much faster than per-record DB roundtrips.
    records: list[dict] = []
    all_chunk_ids: set[str] = set()
    with in_path.open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            records.append(r)
            for c in r.get("chunks", []):
                cid = c.get("chunk_id")
                if cid:
                    all_chunk_ids.add(cid)
    logging.info(
        "loaded %d records, %d distinct chunk_ids",
        len(records), len(all_chunk_ids),
    )

    chunk_lang: dict[str, str | None] = {}
    conn = sqlite3.connect(db_path)
    ids_list = list(all_chunk_ids)
    batch_size = 500
    for i in range(0, len(ids_list), batch_size):
        batch = ids_list[i:i+batch_size]
        placeholders = ",".join(["?"] * len(batch))
        q = f"SELECT chunk_id, language FROM chunks WHERE chunk_id IN ({placeholders})"
        for cid, lang in conn.execute(q, batch).fetchall():
            chunk_lang[cid] = lang
    conn.close()
    n_present = len(chunk_lang)
    n_missing = len(all_chunk_ids) - n_present
    logging.info(
        "DB lookup: %d/%d chunk_ids present (%d missing — dropped during rebuild)",
        n_present, len(all_chunk_ids), n_missing,
    )

    # Pass 2: keep records where ALL chunks are present AND clean.
    kept: list[dict] = []
    n_drop_missing = 0
    n_drop_mojibake = 0
    n_drop_unknown = 0
    for r in records:
        chunks = r.get("chunks", [])
        ok = True
        for c in chunks:
            cid = c.get("chunk_id")
            lang = chunk_lang.get(cid)
            if lang is None:
                ok = False
                n_drop_missing += 1
                break
            if lang == "mojibake_suspected":
                ok = False
                n_drop_mojibake += 1
                break
            if lang not in CLEAN_LANGS:
                ok = False
                n_drop_unknown += 1
                break
        if ok:
            r["source"] = "v4_grounded_v3carry"
            kept.append(r)

    logging.info("kept: %d / %d records", len(kept), len(records))
    logging.info(
        "dropped: missing-chunk=%d, mojibake-chunk=%d, unknown-lang-chunk=%d",
        n_drop_missing, n_drop_mojibake, n_drop_unknown,
    )

    if args.sample > 0 and len(kept) > args.sample:
        import random
        rng = random.Random(args.seed)
        rng.shuffle(kept)
        kept = kept[:args.sample]
        logging.info("sampled down to %d", len(kept))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for r in kept:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n=== filter_v3_grounded_via_db ===", file=sys.stderr)
    print(f"  input        : {in_path}  ({len(records)} records)", file=sys.stderr)
    print(f"  output       : {out_path} ({len(kept)} records)", file=sys.stderr)
    print(f"  dropped      : missing={n_drop_missing} mojibake={n_drop_mojibake} unknown={n_drop_unknown}", file=sys.stderr)
    print(f"  retention    : {100*len(kept)/max(len(records),1):.1f}%", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
