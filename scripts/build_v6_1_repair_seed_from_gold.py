#!/usr/bin/env python3
"""Build v6.1 planner/composer repair seeds from the reviewed gold eval set."""
from __future__ import annotations

import argparse
import json
import urllib.parse
from pathlib import Path
from typing import Any


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
            f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def host_for(row: dict[str, Any]) -> str | None:
    urls: list[str] = []
    gold = row.get("gold_chunk") or {}
    if gold.get("url"):
        urls.append(str(gold["url"]))
    for chunk in row.get("candidate_chunks") or []:
        if chunk.get("url"):
            urls.append(str(chunk["url"]))
    for url in urls:
        host = urllib.parse.urlparse(url).netloc.lower()
        if host:
            return host[4:] if host.startswith("www.") else host
    return None


def expected_behavior(row: dict[str, Any]) -> str:
    typ = row.get("type")
    if typ == "grounded":
        return "answer"
    if typ == "refusal":
        return "refuse"
    return "partial_or_followup"


def notes_for(row: dict[str, Any], host: str | None) -> str:
    typ = row.get("type")
    lang = row.get("question_lang") or "unknown"
    cat = row.get("question_category") or "other"
    chunks = len(row.get("candidate_chunks") or [])
    parts = [f"v6.1 gold-derived repair seed; type={typ}; category={cat}; lang={lang}; chunks={chunks}."]
    if typ == "grounded":
        parts.append("If candidate sources contain the answer, do not append a fallback refusal.")
        if chunks <= 1:
            parts.append("One-source answerability repair: extract the exact requested fact instead of refusing.")
        if lang == "roman_nepali":
            parts.append("Preserve Roman-Nepali Latin script in the final answer.")
    elif typ == "refusal":
        parts.append("Refusal calibration: refuse only because sources are missing/irrelevant, not because of generic uncertainty.")
    else:
        parts.append("Partial/follow-up calibration: ask compact follow-ups when the user case is ambiguous.")
    if host:
        parts.append(f"Expected source host: {host}.")
    return " ".join(parts)


def build(rows: list[dict[str, Any]], include_types: set[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        typ = row.get("type")
        if typ not in include_types:
            continue
        question = str(row.get("question") or "").strip()
        if not question:
            continue
        host = host_for(row)
        seed = {
            "id": f"v6_1_gold_{row.get('id')}",
            "service": row.get("question_category") or "other",
            "topic": row.get("question_category") or "other",
            "question": question,
            "question_lang": row.get("question_lang"),
            "expected_behavior": expected_behavior(row),
            "expected_domains": [host] if host else [],
            "priority": "p0" if typ == "grounded" else "p1",
            "notes": notes_for(row, host),
        }
        out.append(seed)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default="eval/gov_helpdesk_gold_v1.jsonl")
    ap.add_argument("--out", default="seeds/service_eval_v6_1_gold_repair_seed.jsonl")
    ap.add_argument(
        "--include-types",
        default="grounded,refusal,ungrounded_attempt",
        help="comma-separated gold row types to include",
    )
    args = ap.parse_args()

    include_types = {s.strip() for s in args.include_types.split(",") if s.strip()}
    rows = load_jsonl(Path(args.gold))
    seeds = build(rows, include_types)
    write_jsonl(Path(args.out), seeds)
    print(f"wrote {len(seeds)} seeds to {args.out}")
    counts: dict[str, int] = {}
    for seed in seeds:
        key = str(seed.get("expected_behavior") or "unknown")
        counts[key] = counts.get(key, 0) + 1
    print(json.dumps(counts, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
