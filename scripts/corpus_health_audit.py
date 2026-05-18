#!/usr/bin/env python3
"""Audit crawler corpus/index health before judging RAG answers.

This is intentionally DB-level. It catches failures like "the page was fetched
but never chunked", duplicate live URLs, empty PDF extraction, and stale poll
cycles before the model gets involved.

Usage:
    python3 scripts/corpus_health_audit.py \
        --db /Volumes/T9/gemma-god/corpus_v2/index.db \
        --corpus-root /Volumes/T9/gemma-god/corpus_v2
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import urllib.parse
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def rowdict(row: sqlite3.Row) -> dict[str, Any]:
    return {k: row[k] for k in row.keys()}


def canonical_url(url: str) -> str:
    if not url:
        return ""
    try:
        p = urllib.parse.urlsplit(urllib.parse.unquote(url.strip()))
        scheme = (p.scheme or "https").lower()
        host = p.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        path = p.path.rstrip("/")
        return urllib.parse.urlunsplit((scheme, host, path, p.query, ""))
    except Exception:
        return url.strip().rstrip("/")


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def load_sources(conn: sqlite3.Connection, source: str | None) -> list[dict[str, Any]]:
    sql = """
        SELECT source_id, domain, tier, status, last_polled_at, last_changed_at,
               last_failure_at, next_poll_at, consecutive_failures
        FROM sources
    """
    params: list[Any] = []
    if source:
        sql += " WHERE source_id = ?"
        params.append(source)
    sql += " ORDER BY tier, source_id"
    return [rowdict(r) for r in conn.execute(sql, params)]


def load_active_docs(conn: sqlite3.Connection, source: str | None) -> list[dict[str, Any]]:
    sql = """
        SELECT d.doc_id, d.source_id, s.domain, d.url, d.doc_type, d.status_code,
               d.title, d.language, d.fetched_at, d.extracted_text_path,
               d.raw_blob_path, d.text_chars, d.size_bytes, d.depth
        FROM documents d
        JOIN sources s ON s.source_id = d.source_id
        WHERE d.superseded_by IS NULL
          AND d.removed_at IS NULL
    """
    params: list[Any] = []
    if source:
        sql += " AND d.source_id = ?"
        params.append(source)
    return [rowdict(r) for r in conn.execute(sql, params)]


def load_chunk_counts(conn: sqlite3.Connection, source: str | None) -> dict[str, int]:
    sql = """
        SELECT d.doc_id, COUNT(c.chunk_id) AS n
        FROM documents d
        LEFT JOIN chunks c ON c.doc_id = d.doc_id
        WHERE d.superseded_by IS NULL
          AND d.removed_at IS NULL
    """
    params: list[Any] = []
    if source:
        sql += " AND d.source_id = ?"
        params.append(source)
    sql += " GROUP BY d.doc_id"
    return {r["doc_id"]: int(r["n"]) for r in conn.execute(sql, params)}


def load_latest_poll_cycles(conn: sqlite3.Connection, source: str | None) -> dict[str, dict[str, Any]]:
    if not table_exists(conn, "poll_cycles"):
        return {}
    sql = """
        SELECT pc.*
        FROM poll_cycles pc
        JOIN (
            SELECT source_id, MAX(started_at) AS started_at
            FROM poll_cycles
            GROUP BY source_id
        ) latest
          ON latest.source_id = pc.source_id
         AND latest.started_at = pc.started_at
    """
    params: list[Any] = []
    if source:
        sql += " WHERE pc.source_id = ?"
        params.append(source)
    return {r["source_id"]: rowdict(r) for r in conn.execute(sql, params)}


def path_exists(corpus_root: Path, rel_path: str | None) -> bool | None:
    if not rel_path:
        return None
    p = Path(rel_path)
    if not p.is_absolute():
        p = corpus_root / p
    return p.exists()


def audit(db: Path, corpus_root: Path, source: str | None, sample_limit: int) -> dict[str, Any]:
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    sources = load_sources(conn, source)
    active_docs = load_active_docs(conn, source)
    chunk_counts = load_chunk_counts(conn, source)
    latest_cycles = load_latest_poll_cycles(conn, source)

    by_source: dict[str, dict[str, Any]] = {}
    for src in sources:
        sid = src["source_id"]
        docs = [d for d in active_docs if d["source_id"] == sid]
        chunks = sum(chunk_counts.get(d["doc_id"], 0) for d in docs)
        without_chunks = [d for d in docs if chunk_counts.get(d["doc_id"], 0) == 0]
        pdfs = [d for d in docs if (d["doc_type"] or "").lower() == "pdf"]
        pdfs_without_chunks = [d for d in pdfs if chunk_counts.get(d["doc_id"], 0) == 0]
        htmls = [d for d in docs if (d["doc_type"] or "").lower() == "html"]
        htmls_without_chunks = [d for d in htmls if chunk_counts.get(d["doc_id"], 0) == 0]
        zero_text = [d for d in docs if int(d["text_chars"] or 0) == 0]
        missing_extracted = [
            d for d in docs
            if d.get("extracted_text_path")
            and path_exists(corpus_root, d.get("extracted_text_path")) is False
        ]
        by_source[sid] = {
            **src,
            "active_docs": len(docs),
            "chunks": chunks,
            "active_docs_without_chunks": len(without_chunks),
            "html_docs_without_chunks": len(htmls_without_chunks),
            "pdf_docs_without_chunks": len(pdfs_without_chunks),
            "zero_text_docs": len(zero_text),
            "missing_extracted_files": len(missing_extracted),
            "latest_poll_cycle": latest_cycles.get(sid),
            "samples": {
                "without_chunks": [
                    {
                        "url": d["url"],
                        "doc_type": d["doc_type"],
                        "text_chars": d["text_chars"],
                        "fetched_at": d["fetched_at"],
                        "title": d["title"],
                    }
                    for d in without_chunks[:sample_limit]
                ],
                "missing_extracted_files": [
                    {
                        "url": d["url"],
                        "extracted_text_path": d["extracted_text_path"],
                        "fetched_at": d["fetched_at"],
                    }
                    for d in missing_extracted[:sample_limit]
                ],
            },
        }

    canonical_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for d in active_docs:
        canonical_groups[canonical_url(d["url"])].append(d)
    duplicate_groups = {
        k: v for k, v in canonical_groups.items()
        if k and len({d["doc_id"] for d in v}) > 1
    }

    type_counts = Counter((d["doc_type"] or "unknown").lower() for d in active_docs)
    language_counts = Counter((d["language"] or "unknown").lower() for d in active_docs)
    fts_count = None
    if table_exists(conn, "chunks_fts"):
        fts_count = conn.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0]
    total_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    conn.close()

    active_without_chunks = sum(s["active_docs_without_chunks"] for s in by_source.values())
    selected_chunks = sum(s["chunks"] for s in by_source.values())
    total_active_docs = len(active_docs)
    summary = {
        "db": str(db),
        "corpus_root": str(corpus_root),
        "source_filter": source,
        "sources": len(sources),
        "active_docs": total_active_docs,
        "selected_live_chunks": selected_chunks,
        "total_chunks": total_chunks,
        "fts_chunks": fts_count,
        "active_docs_without_chunks": active_without_chunks,
        "active_docs_with_chunks": total_active_docs - active_without_chunks,
        "duplicate_canonical_urls": len(duplicate_groups),
        "doc_type_counts": dict(type_counts),
        "language_counts": dict(language_counts),
    }

    worst_sources = sorted(
        by_source.values(),
        key=lambda s: (
            -int(s["active_docs_without_chunks"]),
            -int(s["missing_extracted_files"]),
            s["source_id"],
        ),
    )

    return {
        "summary": summary,
        "worst_sources": [
            {
                "source_id": s["source_id"],
                "domain": s["domain"],
                "active_docs": s["active_docs"],
                "chunks": s["chunks"],
                "active_docs_without_chunks": s["active_docs_without_chunks"],
                "html_docs_without_chunks": s["html_docs_without_chunks"],
                "pdf_docs_without_chunks": s["pdf_docs_without_chunks"],
                "zero_text_docs": s["zero_text_docs"],
                "missing_extracted_files": s["missing_extracted_files"],
                "last_polled_at": s["last_polled_at"],
                "latest_stop_reason": (s.get("latest_poll_cycle") or {}).get("stop_reason"),
            }
            for s in worst_sources[:sample_limit]
        ],
        "duplicate_canonical_url_samples": [
            {
                "canonical_url": key,
                "urls": [
                    {
                        "source_id": d["source_id"],
                        "doc_id": d["doc_id"],
                        "url": d["url"],
                        "doc_type": d["doc_type"],
                        "fetched_at": d["fetched_at"],
                    }
                    for d in docs[:sample_limit]
                ],
            }
            for key, docs in list(duplicate_groups.items())[:sample_limit]
        ],
        "sources": by_source,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="/Volumes/T9/gemma-god/corpus_v2/index.db")
    ap.add_argument("--corpus-root", default="/Volumes/T9/gemma-god/corpus_v2")
    ap.add_argument("--source", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--sample-limit", type=int, default=12)
    ap.add_argument("--fail-on-any", action="store_true")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        print(f"DB not found: {db}", file=sys.stderr)
        return 1
    report = audit(
        db=db,
        corpus_root=Path(args.corpus_root),
        source=args.source or None,
        sample_limit=max(1, args.sample_limit),
    )

    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    s = report["summary"]
    print("=== corpus health ===")
    print(f"db: {s['db']}")
    print(f"sources: {s['sources']}")
    print(f"active docs: {s['active_docs']}")
    print(f"selected live chunks: {s['selected_live_chunks']}")
    print(f"total chunks: {s['total_chunks']}")
    print(f"fts chunks: {s['fts_chunks']}")
    print(f"active docs without chunks: {s['active_docs_without_chunks']}")
    print(f"duplicate canonical URLs: {s['duplicate_canonical_urls']}")
    print(f"doc types: {s['doc_type_counts']}")

    print("\nworst sources:")
    for src in report["worst_sources"]:
        print(
            f"- {src['source_id']} ({src['domain']}): "
            f"docs={src['active_docs']} chunks={src['chunks']} "
            f"no_chunks={src['active_docs_without_chunks']} "
            f"html_no_chunks={src['html_docs_without_chunks']} "
            f"pdf_no_chunks={src['pdf_docs_without_chunks']} "
            f"last_stop={src['latest_stop_reason']}"
        )

    if report["duplicate_canonical_url_samples"]:
        print("\nduplicate canonical URL samples:")
        for group in report["duplicate_canonical_url_samples"][:5]:
            urls = [u["url"] for u in group["urls"][:3]]
            print(f"- {group['canonical_url']}: {urls}")

    if args.out:
        print(f"\nwrote: {args.out}")

    if args.fail_on_any and (
        s["active_docs_without_chunks"] > 0
        or s["duplicate_canonical_urls"] > 0
        or s["fts_chunks"] != s["total_chunks"]
    ):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
