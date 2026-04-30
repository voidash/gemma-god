#!/usr/bin/env python3
"""Narrow the cleaned r/Nepal dump to gov-procedure questions.

Input:   reddit_nepali.jsonl  (per-record `has_gov_kw` already pre-flagged at
                                ingest time by scripts/reddit_ingest.py)
Output:  reddit_gov_questions.jsonl

Filter:
    keep = has_gov_kw == True
           AND ( '?' in body
                 OR body matches an interrogative wh-marker
                       English:    how/where/what/when/why ... pattern
                       Roman-NE:   kasari / kaha / kati / kahile
                       Devanagari: कसरी / कहाँ / कति / कहिले / किन )

Recall is the responsibility of `has_gov_kw`. This stage only converts
"gov-related text" into "gov-related question". A second pass (Sonnet
classifier) can up-grade precision later if the heuristic dataset is too
noisy for SFT.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

# English wh-question patterns — paired tokens to avoid matching "how", "what"
# bare (which appear in declaratives constantly).
ENG_QUESTION_RE = re.compile(
    r"\b("
    r"how\s+(?:do|to|can|long|much|does|should|is|are|many)|"
    r"where\s+(?:do|can|to|is|are|should|i)|"
    r"what\s+(?:is|are|'s|do|does|should|happens|kind|are)|"
    r"when\s+(?:do|can|should|is|will|i)|"
    r"why\s+(?:do|did|is|are|can'?t)|"
    r"can\s+i\s|should\s+i\s|do\s+i\s+need|"
    r"anyone\s+(?:know|tried|knows|got|have)"
    r")",
    re.IGNORECASE,
)

# Roman-Nepali wh-words. These are unambiguous question carriers (no
# overloading with declarative use, unlike "garne" or "banaune"). `\s` after
# the token avoids matching as a substring of a longer Roman-NE word.
ROMAN_QUESTION_RE = re.compile(
    r"\b(kasari|kaha|kati|kahile|kun\s+thau|kun\s+office)\b",
    re.IGNORECASE,
)

# Devanagari wh-words. Devanagari word-boundary handling in Python's `re`
# is shaky, so we use bare substring matching — these tokens rarely appear
# inside other words.
DEVA_QUESTION_RE = re.compile(r"कसरी|कहाँ|कति|कहिले|किन")


def looks_like_question(body: str) -> bool:
    if "?" in body:
        return True
    if ENG_QUESTION_RE.search(body):
        return True
    if ROMAN_QUESTION_RE.search(body):
        return True
    if DEVA_QUESTION_RE.search(body):
        return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="corpora/reddit_nepali.jsonl")
    ap.add_argument("--output", default="corpora/reddit_gov_questions.jsonl")
    ap.add_argument(
        "--sample",
        type=int,
        default=0,
        help="reservoir-sample N kept records and print bodies to stderr",
    )
    ap.add_argument(
        "--posts-only",
        action="store_true",
        help="restrict to kind='post' (drops comment chatter)",
    )
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    seen = 0
    gov = 0
    skipped_kind = 0
    rejected_not_question = Counter()
    kept = 0
    by_lang: Counter[str] = Counter()
    by_kind: Counter[str] = Counter()
    samples: list[dict] = []
    rng = random.Random(args.seed)

    with in_path.open(encoding="utf-8") as f_in, out_path.open(
        "w", encoding="utf-8"
    ) as f_out:
        for line in f_in:
            r = json.loads(line)
            seen += 1
            if not r.get("has_gov_kw"):
                continue
            gov += 1

            if args.posts_only and r["kind"] != "post":
                skipped_kind += 1
                continue

            if not looks_like_question(r["body"]):
                rejected_not_question[r["kind"]] += 1
                continue

            kept += 1
            by_lang[r["lang"]] += 1
            by_kind[r["kind"]] += 1
            f_out.write(json.dumps(r, ensure_ascii=False) + "\n")

            if args.sample > 0:
                if len(samples) < args.sample:
                    samples.append(r)
                else:
                    j = rng.randint(0, kept - 1)
                    if j < args.sample:
                        samples[j] = r

    print("=== filter summary ===", file=sys.stderr)
    print(f"  records seen:       {seen:>7,}", file=sys.stderr)
    print(f"  has_gov_kw=True:    {gov:>7,}", file=sys.stderr)
    if args.posts_only:
        print(f"  skipped (comments): {skipped_kind:>7,}", file=sys.stderr)
    print(
        f"  rejected (gov but not question): {sum(rejected_not_question.values()):>7,}  "
        f"({dict(rejected_not_question)})",
        file=sys.stderr,
    )
    print(f"  kept gov questions: {kept:>7,}", file=sys.stderr)
    print(f"    by lang: {dict(by_lang)}", file=sys.stderr)
    print(f"    by kind: {dict(by_kind)}", file=sys.stderr)
    print(f"  output: {out_path}", file=sys.stderr)

    if samples:
        # Stable random ordering for reproducibility across runs.
        rng2 = random.Random(args.seed)
        rng2.shuffle(samples)
        print("\n=== samples ===", file=sys.stderr)
        for i, s in enumerate(samples, 1):
            print(
                f"\n--- {i} [{s['lang']}/{s['kind']}/score={s.get('score')}] ---",
                file=sys.stderr,
            )
            print(s["body"], file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
