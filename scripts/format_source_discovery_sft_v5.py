#!/usr/bin/env python3
"""Format Opus source-discovery records into v5 planner SFT examples.

These examples teach the local model to inspect a current RAG pack and escalate
to source discovery when evidence is missing or irrelevant. They do not teach
free-form browsing; the assistant output is a structured source-discovery plan.
"""
from __future__ import annotations

import argparse
import json
import random
import re
from pathlib import Path
from typing import Any


SYSTEM = """\
You are SpeakGov's source-discovery planner.
Inspect the user's question and the current RAG sources. Return only JSON.
Your job is to decide whether current RAG is enough, identify missing official
source classes, propose official search/crawl targets, and give only source-
backed partial guidance. Do not invent facts, contacts, fees, deadlines, or URLs.
If current RAG sources are irrelevant, mark them as distractors."""


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


def compact(text: str, limit: int = 900) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def rag_pack_text(rag: dict[str, Any] | None) -> str:
    if not rag:
        return "(no current RAG pack)"
    lines: list[str] = []
    quality = rag.get("quality") or {}
    if quality:
        lines.append("Retrieval quality:")
        lines.append(json.dumps(quality, ensure_ascii=False, separators=(",", ":")))
        lines.append("")
    sources = rag.get("sources") or []
    if not sources:
        lines.append("(no current RAG sources surfaced)")
        return "\n".join(lines)
    for idx, src in enumerate(sources[:8], 1):
        sid = src.get("source_ref") or f"S{src.get('rank') or idx}"
        lines.append(f"[{sid}] {src.get('label') or 'SOURCE'}")
        if src.get("host"):
            lines.append(f"Host: {src.get('host')}")
        if src.get("url"):
            lines.append(f"URL: {src.get('url')}")
        if src.get("title"):
            lines.append(f"Title: {src.get('title')}")
        lines.append(f"Excerpt: {compact(src.get('snippet') or '')}")
        lines.append("")
    return "\n".join(lines).strip()


def user_prompt(row: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"Question: {row.get('question')}",
            "",
            "Current RAG sources:",
            rag_pack_text(row.get("rag_retrieve")),
            "",
            "Return the source-discovery JSON.",
        ]
    )


def output_contract(row: dict[str, Any]) -> str:
    d = row.get("discovery") or {}
    official_sources = []
    for src in d.get("official_sources") or []:
        official_sources.append(
            {
                "url": src.get("url"),
                "authority": src.get("authority"),
                "source_class": src.get("source_class"),
                "verification": src.get("verification"),
                "crawl_priority": src.get("crawl_priority"),
                "claims_supported": src.get("claims_supported") or [],
            }
        )
    out = {
        "rag_assessment": {
            "answerability": d.get("answerability"),
            "current_rag_enough": d.get("answerability") == "answer",
            "service": d.get("service"),
            "action": d.get("action"),
            "location": d.get("location"),
        },
        "needed_source_classes": sorted(
            {
                src.get("source_class")
                for src in d.get("official_sources") or []
                if src.get("source_class")
            }
        ),
        "official_sources_to_crawl": official_sources,
        "facts": d.get("facts") or [],
        "missing": d.get("missing") or [],
        "followups": d.get("followups") or [],
        "suggested_search_queries": d.get("suggested_search_queries") or [],
        "partial_answer": d.get("answer") or "",
    }
    return json.dumps(out, ensure_ascii=False, separators=(",", ":"))


def format_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if row.get("error") or not row.get("discovery"):
            continue
        out.append(
            {
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": user_prompt(row)},
                    {"role": "assistant", "content": output_contract(row)},
                ],
                "source": "v5_source_discovery_plan",
                "lang": "mixed",
                "category": (row.get("discovery") or {}).get("service") or "source_discovery",
                "source_discovery_id": row.get("id"),
            }
        )
    return out


def split_rows(rows: list[dict[str, Any]], val_frac: float, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rng = random.Random(seed)
    rows = list(rows)
    rng.shuffle(rows)
    n_val = max(1, round(len(rows) * val_frac)) if len(rows) >= 10 else 0
    return rows[n_val:], rows[:n_val]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--discoveries", required=True)
    ap.add_argument("--train-out", required=True)
    ap.add_argument("--val-out", required=True)
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--val-frac", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    formatted = format_rows(load_jsonl(Path(args.discoveries)))
    expanded: list[dict[str, Any]] = []
    for rep in range(max(1, args.repeat)):
        for row in formatted:
            new = dict(row)
            new["mix_repeat"] = rep
            expanded.append(new)
    train, val = split_rows(expanded, args.val_frac, args.seed)
    write_jsonl(Path(args.train_out), train)
    write_jsonl(Path(args.val_out), val)
    print(f"formatted: {len(formatted)}")
    print(f"expanded: {len(expanded)}")
    print(f"train: {len(train)}")
    print(f"val: {len(val)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
