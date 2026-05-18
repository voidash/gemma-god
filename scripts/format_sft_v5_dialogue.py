#!/usr/bin/env python3
"""Format v5 dialogue contracts into trainer-ready JSONL messages.

These rows teach the service-navigator behavior: extract slots from chat,
decide whether to ask follow-up, choose source classes, preserve language, and
produce compact intake responses. They complement the RAG answer/contract rows
from `format_sft_v5.py`; they do not replace source-grounded answer training.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any


SYSTEM_DIALOGUE_RESPONSE = """\
You are SpeakGov, a Nepal government-service navigator.
Do resolver/intake before answering. Use the provided planner contract.
If the contract says follow-up is needed, ask a compact checklist and include useful non-speculative routing/contact/source context.
Remember details from chat history. Match the user's language/script.
Do not invent facts, phone numbers, officer names, fees, dates, or document lists."""

SYSTEM_DIALOGUE_CONTRACT = """\
You are the dialogue planner for SpeakGov, a Nepal government-service navigator.
Return only valid compact JSON. Extract service, action, location, case type, missing slots, decision, source classes, and retrieval query.
Ask follow-up when relevant ambiguity blocks a safe answer. Harmless off-domain questions get a light answer plus scope note."""


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
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


def compact_contract(rec: dict[str, Any]) -> dict[str, Any]:
    frame = rec.get("case_frame") or {}
    return {
        "decision": rec.get("decision"),
        "language": rec.get("language"),
        "service": frame.get("service"),
        "action": frame.get("action"),
        "case_type": frame.get("case_type"),
        "district": frame.get("district"),
        "municipality": frame.get("municipality"),
        "ward": frame.get("ward"),
        "missing_slots": frame.get("missing_slots") or [],
        "followup_questions": rec.get("followup_questions") or [],
        "retrieval_query": rec.get("retrieval_query"),
        "expected_domains": rec.get("expected_domains") or [],
        "source_classes": rec.get("source_classes") or {},
        "gaps": rec.get("gaps") or [],
    }


def history_text(history: list[dict[str, Any]]) -> str:
    if not history:
        return "(none)"
    lines = []
    for turn in history[-6:]:
        role = turn.get("role") or "user"
        content = (turn.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else "(none)"


def build_raw_dialogue_prompt(rec: dict[str, Any]) -> str:
    return "\n".join([
        f"History:\n{history_text(rec.get('history') or [])}",
        "",
        f"Latest user question: {rec.get('question')}",
        "",
        "Produce the dialogue planner JSON.",
    ])


def build_response_prompt(rec: dict[str, Any]) -> str:
    contract = json.dumps(compact_contract(rec), ensure_ascii=False, indent=2)
    return "\n".join([
        f"History:\n{history_text(rec.get('history') or [])}",
        "",
        f"Latest user question: {rec.get('question')}",
        "",
        f"Planner contract:\n{contract}",
        "",
        "Write the next assistant message.",
    ])


def canonical_json(obj: dict[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def format_record(rec: dict[str, Any], emit_contract_task: bool) -> list[dict[str, Any]]:
    if rec.get("validation_issues"):
        return []
    question = (rec.get("question") or "").strip()
    if not question:
        return []
    rows: list[dict[str, Any]] = []
    category = (rec.get("case_frame") or {}).get("service") or ("memory" if rec.get("decision") == "ack_memory" else "off_domain")
    answer = (rec.get("assistant_answer") or "").strip()
    if answer:
        rows.append({
            "messages": [
                {"role": "system", "content": SYSTEM_DIALOGUE_RESPONSE},
                {"role": "user", "content": build_response_prompt(rec)},
                {"role": "assistant", "content": answer},
            ],
            "source": "v5_dialogue_response",
            "decision": rec.get("decision"),
            "lang": rec.get("language"),
            "category": category,
        })
    if emit_contract_task:
        rows.append({
            "messages": [
                {"role": "system", "content": SYSTEM_DIALOGUE_CONTRACT},
                {"role": "user", "content": build_raw_dialogue_prompt(rec)},
                {"role": "assistant", "content": canonical_json(compact_contract(rec))},
            ],
            "source": "v5_dialogue_contract_json",
            "decision": rec.get("decision"),
            "lang": rec.get("language"),
            "category": category,
        })
    return rows


def split_rows(rows: list[dict[str, Any]], val_frac: float, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rng = random.Random(seed)
    rows = list(rows)
    rng.shuffle(rows)
    n_val = max(1, int(round(len(rows) * val_frac))) if rows else 0
    return rows[n_val:], rows[:n_val]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contracts", default="corpora/sft_v5_dialogue_contract_seed.jsonl")
    ap.add_argument("--train-out", default="corpora/sft_v5_dialogue_train.jsonl")
    ap.add_argument("--val-out", default="corpora/sft_v5_dialogue_val.jsonl")
    ap.add_argument("--val-frac", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--no-contract-task", action="store_true")
    args = ap.parse_args()

    raw = load_jsonl(Path(args.contracts))
    formatted: list[dict[str, Any]] = []
    for rec in raw:
        formatted.extend(format_record(rec, emit_contract_task=not args.no_contract_task))
    if not formatted:
        raise SystemExit(f"no valid formatted rows from {args.contracts}")

    train, val = split_rows(formatted, args.val_frac, args.seed)
    write_jsonl(Path(args.train_out), train)
    write_jsonl(Path(args.val_out), val)

    print("=== format v5 dialogue summary ===")
    print(f"input contracts: {len(raw)}")
    print(f"formatted records: {len(formatted)}")
    print(f"train: {len(train)}")
    print(f"val: {len(val)}")
    for key, n in sorted(Counter(r.get("source") for r in formatted).items()):
        print(f"  {key}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
