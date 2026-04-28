#!/usr/bin/env python3
"""Pull an English replay subset from `allenai/tulu-3-sft-mixture` for the
SFT v1 training mix's anti-forgetting slice.

Per recipe v0.4: 15% English replay prevents catastrophic forgetting of
English instruction-following. TULU 3 SFT is the well-known general
instruction mixture (FLAN, No Robots, OpenAssistant, Numina, etc.).

Output schema matches `generate_sft_grounded.py`:
    {
      "id": "sft_english_00001",
      "source": "tulu3_sft",
      "question": "...",
      "question_lang": "english",
      "category": "other",
      "chunks": [],
      "answer": "...",
      "skip": false
    }

Usage:
    python scripts/pull_tulu_subset.py --n 1500 --seed 42
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import re
import sys
from pathlib import Path

# TULU 3 mixes English with Spanish/German/Thai/Russian/Hindi/etc. The
# Latin-char ratio filter doesn't help (Spanish/German are Latin alphabet).
# Filter by source dataset instead — the OASST converted subset is multilingual,
# the rest are reliably English. Confirm with a token-overlap heuristic.
ENGLISH_SOURCE_ALLOW = re.compile(
    r"(flan|no_robots|numinamath|coconot|wildchat.*english|tulu-3-personas|"
    r"tulu-3-IF|tulu-3-instruction-following|hard-coded|sciriff|aya_dataset_dolma_v0_5|"
    r"tulu-3-wildguard|tulu-3-wildjailbreak|table_gpt|cssbench|hardcoded)",
    re.I,
)
ENGLISH_SOURCE_DENY = re.compile(r"oasst1|aya_dataset(?!.*english)|multilingual|nllb", re.I)

# Common English function words — at least 2 should appear in any real
# English passage of length >= ~50 chars.
ENGLISH_FUNCTION_WORDS = re.compile(
    r"\b(?:the|of|and|to|in|is|that|it|for|on|with|as|are|this|be|by|or|"
    r"an|at|from|but|not|have|has|was|were|will|can|you|your|i|we|they|"
    r"what|how|when|where|why|which|who)\b",
    re.I,
)


def is_english(source: str | None, text: str) -> bool:
    src = source or ""
    if ENGLISH_SOURCE_DENY.search(src):
        return False
    # Belt-and-suspenders — even allowed sources occasionally smuggle in
    # non-English. Require >= 3 distinct English function words in
    # text >= 50 chars.
    if len(text) < 50:
        return False
    matches = set(m.group(0).lower() for m in ENGLISH_FUNCTION_WORDS.finditer(text))
    return len(matches) >= 3


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1500)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--output", default="corpora/sft_v1_english_replay.jsonl")
    ap.add_argument("--min-chars", type=int, default=20)
    ap.add_argument("--max-chars-question", type=int, default=2000)
    ap.add_argument("--max-chars-answer", type=int, default=4000)
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    try:
        from datasets import load_dataset
    except ImportError:
        print("missing: pip install datasets", file=sys.stderr)
        return 1

    # Stream the dataset (it's ~939K records, no need to download all).
    logging.info("streaming allenai/tulu-3-sft-mixture …")
    ds = load_dataset("allenai/tulu-3-sft-mixture", split="train", streaming=True)

    rng = random.Random(args.seed)
    # Reservoir-sample 5x our target so we can filter for length, then pick n.
    pool_target = args.n * 5
    pool: list[dict] = []
    seen = 0

    for rec in ds:
        seen += 1
        if seen > 100_000:  # cap streaming time
            break
        msgs = rec.get("messages") or []
        # First user message + first assistant message
        user_msg = next((m for m in msgs if m.get("role") == "user"), None)
        asst_msg = next((m for m in msgs if m.get("role") == "assistant"), None)
        if not user_msg or not asst_msg:
            continue
        q = (user_msg.get("content") or "").strip()
        a = (asst_msg.get("content") or "").strip()
        if not q or not a:
            continue
        if len(q) < args.min_chars or len(a) < args.min_chars:
            continue
        if len(q) > args.max_chars_question:
            continue
        if len(a) > args.max_chars_answer:
            continue
        # English-only filter — drops oasst1_converted (multilingual) and any
        # record that doesn't have at least 3 English function words.
        if not is_english(rec.get("source"), q + " " + a):
            continue
        pool.append(
            {
                "question": q,
                "answer": a,
                "src_dataset": rec.get("source") or "tulu3",
            }
        )
        if len(pool) >= pool_target:
            break

    rng.shuffle(pool)
    sampled = pool[: args.n]

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for i, p in enumerate(sampled, 1):
            rec = {
                "id": f"sft_english_{i:05d}",
                "source": "tulu3_sft",
                "src_dataset": p["src_dataset"],
                "question": p["question"],
                "question_lang": "english",
                "category": "other",
                "chunks": [],
                "answer": p["answer"],
                "skip": False,
                "skip_reason": None,
                "gold_chunk_id": None,
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"\n=== TULU subset pull summary ===", file=sys.stderr)
    print(f"  streamed : {seen}", file=sys.stderr)
    print(f"  pool     : {len(pool)}", file=sys.stderr)
    print(f"  sampled  : {len(sampled)}", file=sys.stderr)
    print(f"  output   : {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
