#!/usr/bin/env python3
"""Build a balanced v5 pilot training mix.

Inputs are already validated/generated artifacts:

- clean v5 RAG contract rows for source-grounded answering;
- v5 dialogue rows for intake/follow-up/memory/source routing;
- small replay anchors so the adapter does not forget harmless general tasks.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any


SYSTEM_REPLAY = """\
You are SpeakGov, a Nepal government-service navigator.
For Nepal government-service questions, be factual and route to official sources.
For harmless questions outside that scope, answer briefly and mention that you are primarily built for Nepal government services."""


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise SystemExit(f"{path}:{line_no}: bad JSON: {e}") from e
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def has_messages(row: dict[str, Any]) -> bool:
    messages = row.get("messages")
    return isinstance(messages, list) and len(messages) >= 2


def replay_to_messages(row: dict[str, Any], source: str) -> dict[str, Any] | None:
    question = (row.get("question") or "").strip()
    answer = (row.get("answer") or "").strip()
    if not question or not answer:
        return None
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_REPLAY},
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ],
        "source": source,
        "lang": row.get("question_lang") or row.get("lang") or "unknown",
        "category": row.get("category") or "replay",
    }


def sample_rows(rows: list[dict[str, Any]], n: int, rng: random.Random) -> list[dict[str, Any]]:
    if n <= 0 or not rows:
        return []
    if len(rows) <= n:
        rows = list(rows)
        rng.shuffle(rows)
        return rows
    return rng.sample(rows, n)


def expand_labeled(rows: list[dict[str, Any]], label: str, repeat: int = 1) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for rep in range(repeat):
        for row in rows:
            if not has_messages(row):
                continue
            new = dict(row)
            new["mix_source"] = label
            new["mix_repeat"] = rep
            out.append(new)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rag-train", default="corpora/sft_v5_pilot100_haiku_train.jsonl")
    ap.add_argument("--rag-val", default="corpora/sft_v5_pilot100_haiku_val.jsonl")
    ap.add_argument("--dialogue-train", default="corpora/sft_v5_dialogue_seed500_train.jsonl")
    ap.add_argument("--dialogue-val", default="corpora/sft_v5_dialogue_seed500_val.jsonl")
    ap.add_argument("--math-replay", default="corpora/sft_v4_math_anchor.jsonl")
    ap.add_argument("--english-replay", default="corpora/sft_v4_english_replay.jsonl")
    ap.add_argument("--roman-replay", default="corpora/sft_v4_roman_ne_open_qa.jsonl")
    ap.add_argument("--train-out", default="corpora/sft_v5_mix_dialogue500_train.jsonl")
    ap.add_argument("--val-out", default="corpora/sft_v5_mix_dialogue500_val.jsonl")
    ap.add_argument("--rag-repeat", type=int, default=3)
    ap.add_argument("--math-n", type=int, default=60)
    ap.add_argument("--english-n", type=int, default=40)
    ap.add_argument("--roman-n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    rag_train = load_jsonl(Path(args.rag_train))
    rag_val = load_jsonl(Path(args.rag_val))
    dialogue_train = load_jsonl(Path(args.dialogue_train))
    dialogue_val = load_jsonl(Path(args.dialogue_val))

    math_replay = [r for r in load_jsonl(Path(args.math_replay)) if not r.get("skip")]
    english_replay = [r for r in load_jsonl(Path(args.english_replay)) if not r.get("skip")]
    roman_replay = [r for r in load_jsonl(Path(args.roman_replay)) if not r.get("skip")]

    train: list[dict[str, Any]] = []
    train.extend(expand_labeled(rag_train, "v5_rag_clean_pilot100", repeat=args.rag_repeat))
    train.extend(expand_labeled(dialogue_train, "v5_dialogue_seed500", repeat=1))

    replay_train: list[dict[str, Any]] = []
    for source, rows, n in [
        ("v5_replay_math", math_replay, args.math_n),
        ("v5_replay_english", english_replay, args.english_n),
        ("v5_replay_roman", roman_replay, args.roman_n),
    ]:
        for row in sample_rows(rows, n, rng):
            formatted = replay_to_messages(row, source)
            if formatted:
                formatted["mix_source"] = source
                replay_train.append(formatted)
    train.extend(replay_train)
    rng.shuffle(train)

    val: list[dict[str, Any]] = []
    val.extend(expand_labeled(rag_val, "v5_rag_clean_pilot100_val", repeat=1))
    val.extend(expand_labeled(dialogue_val, "v5_dialogue_seed500_val", repeat=1))
    for source, rows, n in [
        ("v5_replay_math_val", math_replay, 10),
        ("v5_replay_english_val", english_replay, 10),
        ("v5_replay_roman_val", roman_replay, 10),
    ]:
        for row in sample_rows(rows, n, rng):
            formatted = replay_to_messages(row, source)
            if formatted:
                formatted["mix_source"] = source
                val.append(formatted)
    rng.shuffle(val)

    write_jsonl(Path(args.train_out), train)
    write_jsonl(Path(args.val_out), val)

    print("=== v5 training mix ===")
    print(f"rag train input: {len(rag_train)} x{args.rag_repeat}")
    print(f"dialogue train input: {len(dialogue_train)}")
    print(f"replay train input: {len(replay_train)}")
    print(f"train out: {len(train)}")
    print(f"val out: {len(val)}")
    counts = Counter(row.get("mix_source") or row.get("source") for row in train)
    for source, n in sorted(counts.items()):
        print(f"  train {source}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
