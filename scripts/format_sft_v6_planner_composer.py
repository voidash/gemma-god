#!/usr/bin/env python3
"""Format v6 planner/composer contracts into trainer-ready message JSONL.

Input is produced by `scripts/distill_planner_composer_v6.py`. The formatter
emits two supervision tasks:

1. planner/composer JSON contract task: learn intake, source routing,
   answerability, follow-ups, contacts, gaps, and grounded facts.
2. final-answer task: learn the user-facing plain chat response from the same
   source pack and approved contract.
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

SYSTEM_CONTRACT = """\
You are the planner/composer for SpeakGov, a Nepal government-service navigator.
Return only compact valid JSON. Resolve the user's case, decide whether to ask follow-up,
route source classes, select relevant source IDs, list only source-grounded facts/contacts,
state uncertainty/gaps, and write the final answer. Use only the provided Sources."""

SYSTEM_FINAL = """\
You are SpeakGov, a Nepal government-service navigator.
Use the provided planner/composer contract and Sources. Answer in plain chat.
Ask compact follow-up questions when the contract requires them. Cite source-backed facts with [S#].
Do not invent facts, phone numbers, officer names, fees, dates, document lists, or raw URLs.
Match the user's language/script and never answer in Hindi."""


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
    return str(ref) if re.fullmatch(r"S\d{1,2}", str(ref)) else f"S{idx}"


def history_text(history: list[dict[str, Any]]) -> str:
    if not history:
        return "(none)"
    lines: list[str] = []
    for turn in history[-8:]:
        role = turn.get("role") or "user"
        content = re.sub(r"\s+", " ", str(turn.get("content") or "")).strip()
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines) if lines else "(none)"


def source_pack_text(sources: list[dict[str, Any]]) -> str:
    lines = ["Sources:"]
    if not sources:
        lines.append("(no candidate sources surfaced)")
        return "\n".join(lines)
    for idx, src in enumerate(sources, 1):
        sid = source_ref(src, idx)
        label = src.get("label") or ("CITIZEN INTERVIEW" if src.get("is_tacit") else "GOV.NP")
        lines.append(f"\n[{sid}] {label}")
        if src.get("host"):
            lines.append(f"Host: {src.get('host')}")
        elif src.get("url"):
            host = re.sub(r"^https?://", "", str(src.get("url"))).split("/", 1)[0]
            if host:
                lines.append(f"Host: {host}")
        if src.get("title"):
            lines.append(f"Title: {src.get('title')}")
        lines.append(f"Excerpt: {compact_text(src.get('snippet') or src.get('text') or '')}")
    return "\n".join(lines)


def canonical_contract(contract: dict[str, Any]) -> dict[str, Any]:
    case_frame = contract.get("case_frame") or {}
    source_plan = contract.get("source_plan") or {}
    keep = {
        "schema_version": "planner_composer_v6",
        "case_frame": {
            "service": case_frame.get("service"),
            "action": case_frame.get("action"),
            "location": case_frame.get("location") or {},
            "case_type": case_frame.get("case_type"),
            "person_context": case_frame.get("person_context"),
            "known_slots": case_frame.get("known_slots") or {},
            "missing_slots": case_frame.get("missing_slots") or [],
        },
        "source_plan": {
            "needed_source_classes": source_plan.get("needed_source_classes") or [],
            "relevant_source_ids": source_plan.get("relevant_source_ids") or [],
            "irrelevant_source_ids": source_plan.get("irrelevant_source_ids") or [],
            "source_notes": source_plan.get("source_notes") or [],
        },
        "answerability": contract.get("answerability"),
        "facts": contract.get("facts") or [],
        "contacts": contract.get("contacts") or [],
        "uncertainty": contract.get("uncertainty") or [],
        "gaps": contract.get("gaps") or [],
        "followup_questions": contract.get("followup_questions") or [],
        "recommended_next_action": contract.get("recommended_next_action"),
        "final_answer": contract.get("final_answer") or "",
    }
    return keep


def build_contract_prompt(rec: dict[str, Any]) -> str:
    planner_hint = rec.get("planner_hint") or {}
    parts = [
        f"Conversation history:\n{history_text(rec.get('history') or [])}",
        "",
        f"Latest user question: {rec.get('question')}",
        "",
        f"Question language: {rec.get('question_lang') or 'mixed'}",
        "",
        "Planner hint:",
        json.dumps(planner_hint, ensure_ascii=False, separators=(",", ":")),
        "",
        "Retrieval quality:",
        json.dumps(rec.get("retrieve_quality") or {}, ensure_ascii=False, separators=(",", ":")),
        "",
        source_pack_text(rec.get("sources") or []),
        "",
        "Return the v6 planner/composer JSON contract.",
    ]
    return "\n".join(parts)


def build_final_prompt(rec: dict[str, Any], contract: dict[str, Any]) -> str:
    parts = [
        f"Conversation history:\n{history_text(rec.get('history') or [])}",
        "",
        f"Latest user question: {rec.get('question')}",
        "",
        source_pack_text(rec.get("sources") or []),
        "",
        "Planner/composer contract:",
        json.dumps(canonical_contract(contract), ensure_ascii=False, separators=(",", ":")),
        "",
        "Write the next assistant message.",
    ]
    return "\n".join(parts)


def format_record(rec: dict[str, Any], emit_contract_task: bool, include_invalid: bool) -> list[dict[str, Any]]:
    if rec.get("error"):
        return []
    if rec.get("validation_issues") and not include_invalid:
        return []
    contract = rec.get("contract") or {}
    answer = str(contract.get("final_answer") or rec.get("answer") or "").strip()
    question = str(rec.get("question") or "").strip()
    if not question or not answer:
        return []

    category = rec.get("topic") or (contract.get("case_frame") or {}).get("service") or "other"
    metadata = {
        "lang": rec.get("question_lang") or "mixed",
        "category": category,
        "answerability": contract.get("answerability"),
        "recommended_next_action": contract.get("recommended_next_action"),
        "seed_id": rec.get("id"),
    }

    rows: list[dict[str, Any]] = []
    if emit_contract_task:
        rows.append({
            "messages": [
                {"role": "system", "content": SYSTEM_CONTRACT},
                {"role": "user", "content": build_contract_prompt(rec)},
                {"role": "assistant", "content": json.dumps(canonical_contract(contract), ensure_ascii=False, separators=(",", ":"))},
            ],
            "source": "v6_planner_composer_contract_json",
            **metadata,
        })
    rows.append({
        "messages": [
            {"role": "system", "content": SYSTEM_FINAL},
            {"role": "user", "content": build_final_prompt(rec, contract)},
            {"role": "assistant", "content": answer},
        ],
        "source": "v6_planner_composer_final_answer",
        **metadata,
    })
    return rows


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
    ap.add_argument("--contracts", default="corpora/sft_v6_planner_composer_contracts.jsonl")
    ap.add_argument("--train-out", default="corpora/sft_v6_train.jsonl")
    ap.add_argument("--val-out", default="corpora/sft_v6_val.jsonl")
    ap.add_argument("--val-frac", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--no-contract-task", action="store_true")
    ap.add_argument("--include-invalid", action="store_true")
    args = ap.parse_args()

    raw = load_jsonl(Path(args.contracts))
    formatted: list[dict[str, Any]] = []
    for rec in raw:
        formatted.extend(format_record(rec, emit_contract_task=not args.no_contract_task, include_invalid=args.include_invalid))
    if not formatted:
        raise SystemExit(f"no valid formatted rows from {args.contracts}")

    train, val = split_rows(formatted, val_frac=args.val_frac, seed=args.seed)
    write_jsonl(Path(args.train_out), train)
    write_jsonl(Path(args.val_out), val)

    print("=== format v6 planner/composer summary ===")
    print(f"input contracts: {len(raw)}")
    print(f"formatted records: {len(formatted)}")
    print(f"train: {len(train)}")
    print(f"val: {len(val)}")
    for key, n in sorted(Counter(r.get("source") for r in formatted).items()):
        print(f"  {key}: {n}")
    print("by answerability:")
    for key, n in sorted(Counter(r.get("answerability") for r in formatted).items()):
        print(f"  {key}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
