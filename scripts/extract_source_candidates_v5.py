#!/usr/bin/env python3
"""Extract crawl/source candidates from Claude source-discovery JSONL."""
from __future__ import annotations

import argparse
import json
import re
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


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


def host_of(url: str) -> str:
    parsed = urllib.parse.urlparse(url if "://" in url else "https://" + url)
    return parsed.netloc.lower().removeprefix("www.")


def homepage_for(url: str) -> str:
    parsed = urllib.parse.urlparse(url if "://" in url else "https://" + url)
    scheme = parsed.scheme or "https"
    return f"{scheme}://{parsed.netloc}/"


def source_id_for(host: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", host.lower()).strip("_")


def load_registry(path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in load_jsonl(path):
        host = str(row.get("domain") or "").lower().removeprefix("www.")
        if host:
            out[host] = row
    return out


def tier_for(source_classes: set[str]) -> int:
    if source_classes & {"law_or_rule", "notice_or_fee"}:
        return 2
    if source_classes & {"service_page", "citizen_charter", "form_or_download", "contact_or_staff"}:
        return 3
    return 4


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--discoveries", required=True)
    ap.add_argument("--registry", default="corpora/sources_tiered.jsonl")
    ap.add_argument("--candidates-out", required=True)
    ap.add_argument("--overrides-out", default="")
    args = ap.parse_args()

    registry = load_registry(Path(args.registry))
    grouped: dict[str, dict[str, Any]] = {}
    mentions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    classes: dict[str, set[str]] = defaultdict(set)
    priorities: Counter[str] = Counter()

    for row in load_jsonl(Path(args.discoveries)):
        discovery = row.get("discovery") or {}
        for src in discovery.get("official_sources") or []:
            url = str(src.get("url") or "").strip()
            if not url:
                continue
            host = host_of(url)
            if not host:
                continue
            classes[host].add(str(src.get("source_class") or "other_official"))
            if src.get("crawl_priority") == "high":
                priorities[host] += 3
            elif src.get("crawl_priority") == "medium":
                priorities[host] += 2
            else:
                priorities[host] += 1
            mentions[host].append(
                {
                    "question_id": row.get("id"),
                    "question": row.get("question"),
                    "url": url,
                    "title": src.get("title"),
                    "authority": src.get("authority"),
                    "source_class": src.get("source_class"),
                    "verification": src.get("verification"),
                    "evidence": src.get("evidence"),
                    "claims_supported": src.get("claims_supported") or [],
                }
            )

    candidates: list[dict[str, Any]] = []
    overrides: list[dict[str, Any]] = []
    for host, rows in sorted(mentions.items()):
        existing = registry.get(host)
        source_id = existing.get("source_id") if existing else source_id_for(host)
        source_classes = classes[host]
        candidate = {
            "source_id": source_id,
            "domain": host,
            "homepage_url": existing.get("homepage_url") if existing else homepage_for(rows[0]["url"]),
            "existing_in_registry": bool(existing),
            "existing_tier": existing.get("tier_guess") if existing else None,
            "recommended_tier": tier_for(source_classes),
            "priority_score": priorities[host],
            "source_classes": sorted(source_classes),
            "mentions": rows,
        }
        candidates.append(candidate)
        if not existing:
            overrides.append(
                {
                    "op": "add",
                    "source_id": source_id,
                    "domain": host,
                    "homepage_url": candidate["homepage_url"],
                    "name_en": rows[0].get("authority") or host,
                    "name_np": None,
                    "office_type": "Federal",
                    "province": None,
                    "tier_guess": candidate["recommended_tier"],
                    "poll_interval_hours": 24,
                    "reason": (
                        "Added from Opus source-discovery v5 for citizen-demand RAG gap: "
                        f"{rows[0].get('question_id')}"
                    ),
                }
            )

    candidates.sort(key=lambda r: (-r["priority_score"], r["domain"]))
    write_jsonl(Path(args.candidates_out), candidates)
    if args.overrides_out:
        write_jsonl(Path(args.overrides_out), overrides)
    print(f"candidates: {len(candidates)} -> {args.candidates_out}")
    print(f"new overrides: {len(overrides)}" + (f" -> {args.overrides_out}" if args.overrides_out else ""))
    for row in candidates[:20]:
        status = "existing" if row["existing_in_registry"] else "new"
        print(f"- {row['domain']} {status} priority={row['priority_score']} classes={','.join(row['source_classes'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
