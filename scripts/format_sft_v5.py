#!/usr/bin/env python3
"""Format v5 RAG-contract records into trainer-ready messages JSONL.

Input is produced by `scripts/distill_rag_contract_v5.py`. This emits two
supervision tasks by default:

1. answer task: same production contract as server/main.py, final answer with
   [S#] citations.
2. contract task: explicit JSON task for answerability/source-selection/facts.

Keeping the contract task explicit avoids teaching the production prompt to emit
JSON unless we ask for JSON.
"""
from __future__ import annotations

import argparse
import json
import random
import re
from collections import Counter
from pathlib import Path
from typing import Any


CHUNK_TEXT_MAX_CHARS = 1200

SYSTEM_ANSWER = """\
You are SpeakGov, an independent helpdesk assistant for navigating Nepal government services.
Answer using ONLY the provided Sources. Cite factual claims with source IDs such as [S1].
If sources support only part of the answer, answer the supported part and say what is missing.
Refuse only when no source meaningfully addresses the question. Match the user's language/script.
For harmless questions outside Nepal government services, answer briefly and say you are primarily built for Nepal government services.
Be concise and procedural."""

SYSTEM_CONTRACT = """\
You are producing a RAG contract for a Nepal government-service helpdesk.
Return only valid JSON with answerability, relevant_source_ids, facts, missing, and answer.
answerability must be one of: answer, partial, refuse, off_domain.
Use only provided Sources. Cite by source ID such as [S1]."""


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


def compact_text(text: str, limit: int = CHUNK_TEXT_MAX_CHARS) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def source_ref(src: dict[str, Any], idx: int) -> str:
    ref = src.get("source_ref") or f"S{src.get('rank') or idx}"
    return ref if re.fullmatch(r"S\d{1,2}", str(ref)) else f"S{idx}"


def build_user_prompt(question: str, sources: list[dict[str, Any]]) -> str:
    lines = [f"Question: {question.strip()}", "", "Sources:"]
    if not sources:
        lines.append("(no candidate sources surfaced)")
        return "\n".join(lines)
    for idx, src in enumerate(sources, 1):
        ref = source_ref(src, idx)
        label = src.get("label") or ("CITIZEN INTERVIEW" if src.get("is_tacit") else "GOV.NP")
        lines.append(f"\n[{ref}] {label}")
        if src.get("url"):
            lines.append(f"URL: {src.get('url')}")
        if src.get("title"):
            lines.append(f"Title: {src.get('title')}")
        snippet = src.get("snippet") or src.get("text") or ""
        lines.append(f"Excerpt: {compact_text(snippet)}")
    return "\n".join(lines)


def canonical_contract(contract: dict[str, Any]) -> str:
    keep = {
        "answerability": contract.get("answerability"),
        "relevant_source_ids": contract.get("relevant_source_ids") or [],
        "facts": contract.get("facts") or [],
        "missing": contract.get("missing") or [],
        "answer": contract.get("answer") or "",
    }
    return json.dumps(keep, ensure_ascii=False, separators=(",", ":"))


def format_contract_record(rec: dict[str, Any], emit_contract_task: bool) -> list[dict[str, Any]]:
    if rec.get("error") or rec.get("validation_issues"):
        return []
    question = (rec.get("question") or "").strip()
    answer = (rec.get("answer") or rec.get("contract", {}).get("answer") or "").strip()
    sources = rec.get("sources") or []
    contract = rec.get("contract") or {}
    if not question or not answer:
        return []

    user = build_user_prompt(question, sources)
    out = [{
        "messages": [
            {"role": "system", "content": SYSTEM_ANSWER},
            {"role": "user", "content": user},
            {"role": "assistant", "content": answer},
        ],
        "source": "v5_rag_answer",
        "lang": rec.get("question_lang") or "mixed",
        "category": rec.get("topic") or "other",
    }]

    if emit_contract_task:
        out.append({
            "messages": [
                {"role": "system", "content": SYSTEM_CONTRACT},
                {"role": "user", "content": user + "\n\nReturn the JSON contract."},
                {"role": "assistant", "content": canonical_contract(contract)},
            ],
            "source": "v5_rag_contract_json",
            "lang": rec.get("question_lang") or "mixed",
            "category": rec.get("topic") or "other",
        })
    return out


def split_rows(rows: list[dict[str, Any]], val_frac: float, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rng = random.Random(seed)
    by_source: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_source.setdefault(row.get("source") or "unknown", []).append(row)

    train: list[dict[str, Any]] = []
    val: list[dict[str, Any]] = []
    for _, bucket in sorted(by_source.items()):
        rng.shuffle(bucket)
        n_val = max(1, int(round(len(bucket) * val_frac))) if len(bucket) >= 20 else max(0, int(round(len(bucket) * val_frac)))
        val.extend(bucket[:n_val])
        train.extend(bucket[n_val:])
    rng.shuffle(train)
    rng.shuffle(val)
    return train, val


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contracts", default="corpora/sft_v5_rag_contract.jsonl")
    ap.add_argument("--train-out", default="corpora/sft_v5_train.jsonl")
    ap.add_argument("--val-out", default="corpora/sft_v5_val.jsonl")
    ap.add_argument("--val-frac", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--no-contract-task", action="store_true")
    args = ap.parse_args()

    raw = load_jsonl(Path(args.contracts))
    formatted: list[dict[str, Any]] = []
    for rec in raw:
        formatted.extend(format_contract_record(rec, emit_contract_task=not args.no_contract_task))

    if not formatted:
        raise SystemExit(f"no valid formatted records from {args.contracts}")

    train, val = split_rows(formatted, val_frac=args.val_frac, seed=args.seed)
    write_jsonl(Path(args.train_out), train)
    write_jsonl(Path(args.val_out), val)

    counts = Counter(r.get("source") for r in formatted)
    print("=== format v5 summary ===")
    print(f"input records: {len(raw)}")
    print(f"formatted records: {len(formatted)}")
    print(f"train: {len(train)}")
    print(f"val: {len(val)}")
    print("by source:")
    for source, n in sorted(counts.items()):
        print(f"  {source}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
