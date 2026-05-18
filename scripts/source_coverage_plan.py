#!/usr/bin/env python3
"""Rank government sources for the next crawl/index coverage pass.

The crawler registry tells us what we *could* cover. The SQLite index tells us
what we actually covered and chunked. This script combines both with observed
citizen-demand categories so a broad crawl still starts with the sites most
likely to answer useful public-service questions.

Usage:
    python3 scripts/source_coverage_plan.py --limit 40
    python3 scripts/source_coverage_plan.py --format commands --limit 20
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_DB = Path("/Volumes/T9/gemma-god/corpus_v2/index.db")
DEFAULT_SOURCES = Path("corpora/sources_tiered.jsonl")
DEFAULT_DEMAND = Path("corpora/reddit_gov_questions_classified.jsonl")
CORPUS_ROOT = "/Volumes/T9/gemma-god/corpus_v2"

ACTIONABLE_CLASSES = {"yes_procedure", "yes_info"}

CATEGORY_AUTHORITIES: dict[str, list[str]] = {
    "passport": ["nepalpassport", "passport", "mofa", "nagarikapp"],
    "citizenship": ["donidcr", "moha", "dao", "districtadministration", "nagarikapp"],
    "birth_registration": ["donidcr", "moha", "municipality", "rural municipality", "metropolitan", "nagarikapp"],
    "pan_vat": ["ird", "tax"],
    "tax": ["ird", "customs", "tax", "nrb"],
    "driving_license": ["dotm", "transport", "applydlnew", "ldims", "nagarikapp"],
    "police": ["nepalpolice", "traffic", "cid", "police", "opcr", "ldims"],
    "land": ["dolma", "land management", "malpot", "survey", "napi", "dos"],
    "education": ["education", "moest", "neb", "ctevt", "curriculum"],
    "business": ["ocr", "doind", "sebon", "nrb", "ird"],
    "visa_immigration": ["immigration", "dofe", "feb", "moless", "mofa", "labor", "labour", "feims", "foreignjob"],
    "health": ["health", "dohs", "edcd", "fwd"],
    "election": ["election", "voter"],
    "other": ["nepal government national portal", "nagarikapp", "opmcm"],
}

LOCAL_PRIORITY_HINTS = {
    "jiri",
    "kathmandu",
    "lalitpur",
    "pokhara",
    "bharatpur",
    "biratnagar",
    "birgunj",
    "butwal",
    "dharan",
    "hetauda",
    "janakpur",
    "nepalgunj",
    "dhangadhi",
    "ghorahi",
    "tulsipur",
    "itahari",
}


@dataclass
class SourceStats:
    source_id: str
    domain: str = ""
    homepage_url: str = ""
    name_en: str | None = None
    name_np: str | None = None
    office_type: str | None = None
    tier: int = 5
    status: str = "active"
    last_polled_at: str | None = None
    next_poll_at: str | None = None
    consecutive_failures: int = 0
    active_docs: int | None = None
    chunks: int | None = None
    active_docs_without_chunks: int | None = None
    html_docs_without_chunks: int | None = None
    pdf_docs_without_chunks: int | None = None
    latest_doc_at: str | None = None
    latest_stop_reason: str | None = None
    latest_poll_errors: int | None = None
    demand_categories: list[str] = field(default_factory=list)
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rows.append(json.loads(line))
    return rows


def source_id_from_domain(domain: str) -> str:
    return domain.lower().replace(".", "_").replace("-", "_")


def registry_sources(path: Path) -> dict[str, SourceStats]:
    out: dict[str, SourceStats] = {}
    for r in load_jsonl(path):
        sid = r.get("source_id") or source_id_from_domain(r.get("domain") or "")
        if not sid:
            continue
        out[sid] = SourceStats(
            source_id=sid,
            domain=r.get("domain") or "",
            homepage_url=r.get("homepage_url") or "",
            name_en=r.get("name_en"),
            name_np=r.get("name_np"),
            office_type=r.get("office_type"),
            tier=int(r.get("tier_guess") or r.get("tier") or 5),
            status=r.get("status") or "active",
        )
    return out


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def merge_db_stats(sources: dict[str, SourceStats], db: Path) -> bool:
    if not db.exists():
        return False
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row

    for r in conn.execute(
        """
        SELECT source_id, domain, homepage_url, name_en, name_np, office_type,
               tier, status, last_polled_at, next_poll_at, consecutive_failures
        FROM sources
        """
    ):
        sid = r["source_id"]
        s = sources.get(sid) or SourceStats(source_id=sid)
        s.domain = r["domain"] or s.domain
        s.homepage_url = r["homepage_url"] or s.homepage_url
        s.name_en = r["name_en"] or s.name_en
        s.name_np = r["name_np"] or s.name_np
        s.office_type = r["office_type"] or s.office_type
        s.tier = int(r["tier"] or s.tier)
        s.status = r["status"] or s.status
        s.last_polled_at = r["last_polled_at"]
        s.next_poll_at = r["next_poll_at"]
        s.consecutive_failures = int(r["consecutive_failures"] or 0)
        sources[sid] = s

    if table_exists(conn, "documents") and table_exists(conn, "chunks"):
        for r in conn.execute(
            """
            WITH live_docs AS (
                SELECT doc_id, source_id, doc_type, fetched_at
                FROM documents
                WHERE superseded_by IS NULL
                  AND removed_at IS NULL
            ),
            doc_chunks AS (
                SELECT d.source_id, d.doc_id, d.doc_type, d.fetched_at,
                       COUNT(c.chunk_id) AS n_chunks
                FROM live_docs d
                LEFT JOIN chunks c ON c.doc_id = d.doc_id
                GROUP BY d.source_id, d.doc_id
            )
            SELECT source_id,
                   COUNT(*) AS active_docs,
                   SUM(n_chunks) AS chunks,
                   SUM(CASE WHEN n_chunks = 0 THEN 1 ELSE 0 END) AS no_chunks,
                   SUM(CASE WHEN n_chunks = 0 AND lower(coalesce(doc_type,'')) = 'html' THEN 1 ELSE 0 END) AS html_no_chunks,
                   SUM(CASE WHEN n_chunks = 0 AND lower(coalesce(doc_type,'')) = 'pdf' THEN 1 ELSE 0 END) AS pdf_no_chunks,
                   MAX(fetched_at) AS latest_doc_at
            FROM doc_chunks
            GROUP BY source_id
            """
        ):
            s = sources.get(r["source_id"])
            if not s:
                continue
            s.active_docs = int(r["active_docs"] or 0)
            s.chunks = int(r["chunks"] or 0)
            s.active_docs_without_chunks = int(r["no_chunks"] or 0)
            s.html_docs_without_chunks = int(r["html_no_chunks"] or 0)
            s.pdf_docs_without_chunks = int(r["pdf_no_chunks"] or 0)
            s.latest_doc_at = r["latest_doc_at"]

    if table_exists(conn, "poll_cycles"):
        for r in conn.execute(
            """
            SELECT pc.source_id, pc.stop_reason, pc.errors
            FROM poll_cycles pc
            JOIN (
                SELECT source_id, MAX(started_at) AS started_at
                FROM poll_cycles
                GROUP BY source_id
            ) latest
              ON latest.source_id = pc.source_id
             AND latest.started_at = pc.started_at
            """
        ):
            s = sources.get(r["source_id"])
            if s:
                s.latest_stop_reason = r["stop_reason"]
                s.latest_poll_errors = int(r["errors"] or 0)

    conn.close()
    return True


def demand_counts(path: Path) -> Counter[str]:
    counts: Counter[str] = Counter()
    for r in load_jsonl(path):
        category = (r.get("category") or "other").strip() or "other"
        cls = r.get("class")
        if cls in ACTIONABLE_CLASSES:
            counts[category] += 10
        elif cls == "no_format" and category != "other":
            counts[category] += 2
    return counts


def haystack(s: SourceStats) -> str:
    return " ".join(
        str(x or "").lower()
        for x in [s.source_id, s.domain, s.homepage_url, s.name_en, s.name_np, s.office_type]
    )


def needle_hit(blob: str, needle: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", " ", blob.lower())
    compact = re.sub(r"[^a-z0-9]+", "", blob.lower())
    needle_norm = re.sub(r"[^a-z0-9]+", " ", needle.lower()).strip()
    needle_compact = re.sub(r"[^a-z0-9]+", "", needle.lower())
    if " " in needle_norm:
        return needle_norm in normalized
    tokens = set(normalized.split())
    if len(needle_compact) <= 4:
        return needle_compact in tokens
    return needle_compact in tokens or needle_compact in compact


def matched_categories(s: SourceStats, demand: Counter[str]) -> list[str]:
    blob = haystack(s)
    priority_local = s.tier == 5 and any(n in blob for n in LOCAL_PRIORITY_HINTS)
    hits: list[str] = []
    for category, needles in CATEGORY_AUTHORITIES.items():
        if s.tier == 5 and category in {"birth_registration", "citizenship"} and not priority_local:
            continue
        if any(needle_hit(blob, n) for n in needles):
            hits.append(category)
    if (
        priority_local
        and any(n in blob for n in ["mun", "municipality", "gaunpalika", "rural"])
    ):
        hits.extend(["birth_registration", "citizenship"])
    return sorted(set(h for h in hits if demand.get(h, 0) > 0))


def score_source(s: SourceStats, demand: Counter[str]) -> None:
    reasons: list[str] = []
    score = 0.0

    tier_weight = {1: 34, 2: 32, 3: 28, 4: 18, 5: 10}.get(s.tier, 8)
    score += tier_weight
    reasons.append(f"T{s.tier}")

    cats = matched_categories(s, demand)
    s.demand_categories = cats
    if cats:
        raw = sum(demand[c] for c in cats)
        demand_score = min(52.0, 8.0 + math.log1p(raw) * 13.0)
        score += demand_score
        reasons.append("demand:" + ",".join(cats[:4]))

    blob = haystack(s)
    if s.tier == 5 and any(h in blob for h in LOCAL_PRIORITY_HINTS):
        score += 18
        reasons.append("priority-local")

    if s.status != "active":
        score -= 70
        reasons.append(f"status:{s.status}")

    if s.active_docs is None:
        score += 16
        reasons.append("db-stats-missing")
    elif s.active_docs == 0:
        score += 42
        reasons.append("no-docs")
    else:
        no_chunks = int(s.active_docs_without_chunks or 0)
        chunks = int(s.chunks or 0)
        if chunks == 0:
            score += 38
            reasons.append("no-chunks")
        if no_chunks:
            ratio = no_chunks / max(1, int(s.active_docs or 0))
            score += min(34.0, math.log1p(no_chunks) * 8.0) + ratio * 18.0
            reasons.append(f"unchunked:{no_chunks}")
            if s.html_docs_without_chunks:
                score += min(12.0, math.log1p(int(s.html_docs_without_chunks)) * 4.0)
                reasons.append(f"html-unchunked:{s.html_docs_without_chunks}")

    if not s.last_polled_at:
        score += 20
        reasons.append("never-polled")
    if s.consecutive_failures:
        score += min(12, s.consecutive_failures * 3)
        reasons.append(f"failures:{s.consecutive_failures}")
    if s.latest_poll_errors:
        score += min(8, s.latest_poll_errors)
        reasons.append(f"poll-errors:{s.latest_poll_errors}")

    if s.latest_stop_reason in {"item_limit", "max_elapsed", "max_elapsed_sec", "frontier_limit"}:
        score += 10
        reasons.append(f"stopped:{s.latest_stop_reason}")

    s.score = round(score, 2)
    s.reasons = reasons


def row_for_output(s: SourceStats) -> dict[str, Any]:
    return {
        "source_id": s.source_id,
        "domain": s.domain,
        "homepage_url": s.homepage_url,
        "name_en": s.name_en,
        "office_type": s.office_type,
        "tier": s.tier,
        "status": s.status,
        "score": s.score,
        "demand_categories": s.demand_categories,
        "active_docs": s.active_docs,
        "chunks": s.chunks,
        "active_docs_without_chunks": s.active_docs_without_chunks,
        "html_docs_without_chunks": s.html_docs_without_chunks,
        "pdf_docs_without_chunks": s.pdf_docs_without_chunks,
        "last_polled_at": s.last_polled_at,
        "latest_stop_reason": s.latest_stop_reason,
        "reasons": s.reasons,
    }


def print_text(rows: list[SourceStats], db_loaded: bool) -> None:
    print("=== source coverage plan ===")
    print(f"db_stats: {'loaded' if db_loaded else 'not loaded'}")
    print(
        "score  tier  source_id                       docs  chunks  no_chunks  demand"
    )
    for s in rows:
        docs = "-" if s.active_docs is None else str(s.active_docs)
        chunks = "-" if s.chunks is None else str(s.chunks)
        no_chunks = "-" if s.active_docs_without_chunks is None else str(s.active_docs_without_chunks)
        demand = ",".join(s.demand_categories[:3]) or "-"
        print(
            f"{s.score:5.1f}  T{s.tier:<3}  {s.source_id[:30]:30} "
            f"{docs:>5}  {chunks:>7}  {no_chunks:>9}  {demand}"
        )
        print(f"       {s.domain} | {'; '.join(s.reasons[:8])}")


def print_commands(rows: list[SourceStats]) -> None:
    for s in rows:
        print(
            f"./crawl poll --source {s.source_id} "
            f"--recipes-dir recipes --out-root {CORPUS_ROOT}"
        )
        print(
            f"./crawl index-chunks --source {s.source_id} "
            f"--corpus-root {CORPUS_ROOT}"
        )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--sources", default=str(DEFAULT_SOURCES))
    ap.add_argument("--demand", default=str(DEFAULT_DEMAND))
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--tier-max", type=int, default=5)
    ap.add_argument("--format", choices=["text", "jsonl", "commands"], default="text")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    sources = registry_sources(Path(args.sources))
    if not sources:
        print(f"no sources loaded from {args.sources}", file=sys.stderr)
        return 1

    db_loaded = merge_db_stats(sources, Path(args.db))
    demand = demand_counts(Path(args.demand))
    if not demand:
        demand = Counter({"passport": 1, "citizenship": 1, "tax": 1})

    rows = [
        s for s in sources.values()
        if s.tier <= args.tier_max and s.status == "active"
    ]
    for s in rows:
        score_source(s, demand)
    rows.sort(key=lambda s: (-s.score, s.tier, s.source_id))
    rows = rows[: max(1, args.limit)]

    if args.format == "text":
        from io import StringIO
        old_stdout = sys.stdout
        buf = StringIO()
        try:
            sys.stdout = buf
            print_text(rows, db_loaded)
        finally:
            sys.stdout = old_stdout
        text = buf.getvalue()
        print(text, end="")
        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(text, encoding="utf-8")
    elif args.format == "commands":
        from io import StringIO
        old_stdout = sys.stdout
        buf = StringIO()
        try:
            sys.stdout = buf
            print_commands(rows)
        finally:
            sys.stdout = old_stdout
        text = buf.getvalue()
        print(text, end="")
        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(text, encoding="utf-8")
    else:
        lines = [json.dumps(row_for_output(s), ensure_ascii=False) for s in rows]
        text = "\n".join(lines) + "\n"
        print(text, end="")
        if args.out:
            Path(args.out).parent.mkdir(parents=True, exist_ok=True)
            Path(args.out).write_text(text, encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
