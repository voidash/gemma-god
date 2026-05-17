#!/usr/bin/env python3
"""Resumable source-by-source crawl/index runner.

Use this for broad coverage passes where `./crawl poll --all` is too risky:
some government sites hang inside a single source poll. This wrapper gives
each source a wall-clock timeout, logs one JSON record per source, and can be
resumed without repeating completed sources.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_DB = Path("/Volumes/T9/gemma-god/corpus_v2/index.db")
DEFAULT_CORPUS_ROOT = Path("/Volumes/T9/gemma-god/corpus_v2")
DEFAULT_RECIPES_DIR = Path("recipes")


@dataclass
class Source:
    source_id: str
    tier: int
    status: str
    active_docs: int
    chunks: int
    unchunked_docs: int


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def db_conn(db: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    return conn


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def load_done(log_path: Path) -> set[str]:
    done: set[str] = set()
    if not log_path.exists():
        return done
    with log_path.open(encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("phase") == "source_done" and rec.get("source_id"):
                done.add(rec["source_id"])
    return done


def source_stats(db: Path, source_id: str) -> dict[str, int]:
    with db_conn(db) as conn:
        row = conn.execute(
            """
            WITH live_docs AS (
                SELECT doc_id
                FROM documents
                WHERE source_id = ?
                  AND superseded_by IS NULL
                  AND removed_at IS NULL
            ),
            doc_chunks AS (
                SELECT d.doc_id, COUNT(c.chunk_id) AS n_chunks
                FROM live_docs d
                LEFT JOIN chunks c ON c.doc_id = d.doc_id
                GROUP BY d.doc_id
            )
            SELECT
                COUNT(*) AS active_docs,
                COALESCE(SUM(n_chunks), 0) AS chunks,
                COALESCE(SUM(CASE WHEN n_chunks = 0 THEN 1 ELSE 0 END), 0) AS unchunked_docs
            FROM doc_chunks
            """,
            (source_id,),
        ).fetchone()
    return {
        "active_docs": int(row["active_docs"] or 0),
        "chunks": int(row["chunks"] or 0),
        "unchunked_docs": int(row["unchunked_docs"] or 0),
    }


def load_sources(
    db: Path,
    tier_max: int,
    source_ids: list[str],
    only_no_docs: bool,
    only_unchunked: bool,
) -> list[Source]:
    with db_conn(db) as conn:
        where = ["s.status IN ('active', 'js_only')", "s.tier <= ?"]
        params: list[Any] = [tier_max]
        if source_ids:
            placeholders = ",".join("?" for _ in source_ids)
            where.append(f"s.source_id IN ({placeholders})")
            params.extend(source_ids)
        sql = f"""
            WITH live_docs AS (
                SELECT doc_id, source_id
                FROM documents
                WHERE superseded_by IS NULL
                  AND removed_at IS NULL
            ),
            doc_chunks AS (
                SELECT d.source_id, d.doc_id, COUNT(c.chunk_id) AS n_chunks
                FROM live_docs d
                LEFT JOIN chunks c ON c.doc_id = d.doc_id
                GROUP BY d.source_id, d.doc_id
            ),
            per_source AS (
                SELECT source_id,
                       COUNT(*) AS active_docs,
                       COALESCE(SUM(n_chunks), 0) AS chunks,
                       COALESCE(SUM(CASE WHEN n_chunks = 0 THEN 1 ELSE 0 END), 0) AS unchunked_docs
                FROM doc_chunks
                GROUP BY source_id
            )
            SELECT s.source_id, s.tier, s.status,
                   COALESCE(p.active_docs, 0) AS active_docs,
                   COALESCE(p.chunks, 0) AS chunks,
                   COALESCE(p.unchunked_docs, 0) AS unchunked_docs
            FROM sources s
            LEFT JOIN per_source p ON p.source_id = s.source_id
            WHERE {' AND '.join(where)}
            ORDER BY s.tier, COALESCE(p.active_docs, 0), s.source_id
        """
        rows = conn.execute(sql, params).fetchall()

    out: list[Source] = []
    for r in rows:
        s = Source(
            source_id=r["source_id"],
            tier=int(r["tier"]),
            status=r["status"],
            active_docs=int(r["active_docs"] or 0),
            chunks=int(r["chunks"] or 0),
            unchunked_docs=int(r["unchunked_docs"] or 0),
        )
        if only_no_docs and s.active_docs > 0:
            continue
        if only_unchunked and s.unchunked_docs <= 0:
            continue
        out.append(s)
    return out


def run_command(cmd: list[str], timeout_sec: int) -> dict[str, Any]:
    start = time.monotonic()
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout_sec)
        timed_out = False
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            stdout, stderr = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            stdout, stderr = proc.communicate()
    elapsed = round(time.monotonic() - start, 3)
    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "timed_out": timed_out,
        "elapsed_sec": elapsed,
        "stdout_tail": (stdout or "")[-4000:],
        "stderr_tail": (stderr or "")[-4000:],
    }


def ensure_fts(conn: sqlite3.Connection) -> None:
    if table_exists(conn, "chunks_fts"):
        return
    conn.executescript(
        """
        CREATE VIRTUAL TABLE chunks_fts USING fts5(
            chunk_id UNINDEXED,
            text,
            tokenize="unicode61 remove_diacritics 0"
        );
        """
    )


def sync_fts(db: Path) -> dict[str, int]:
    with db_conn(db) as conn:
        ensure_fts(conn)
        before = int(conn.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0])
        conn.execute("DROP TABLE IF EXISTS temp.existing_fts_chunk_ids")
        conn.execute(
            "CREATE TEMP TABLE existing_fts_chunk_ids(chunk_id TEXT PRIMARY KEY)"
        )
        conn.execute(
            """
            INSERT INTO existing_fts_chunk_ids(chunk_id)
            SELECT chunk_id FROM chunks_fts
            """
        )
        conn.execute(
            """
            INSERT INTO chunks_fts(chunk_id, text)
            SELECT c.chunk_id, c.text
            FROM chunks c
            LEFT JOIN existing_fts_chunk_ids f ON f.chunk_id = c.chunk_id
            WHERE f.chunk_id IS NULL
            """
        )
        conn.execute("DROP TABLE IF EXISTS temp.existing_fts_chunk_ids")
        conn.commit()
        after = int(conn.execute("SELECT COUNT(*) FROM chunks_fts").fetchone()[0])
    return {"fts_before": before, "fts_after": after, "fts_added": after - before}


def append_log(path: Path, rec: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        f.flush()


def parse_source_list(raw: str) -> list[str]:
    if not raw:
        return []
    p = Path(raw)
    try:
        path_exists = not any(ch.isspace() for ch in raw) and p.exists()
    except OSError:
        path_exists = False
    if path_exists:
        out: list[str] = []
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                out.extend(part.strip() for part in line.split() if part.strip())
        return out
    return [part.strip() for part in raw.replace(",", " ").split() if part.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--corpus-root", default=str(DEFAULT_CORPUS_ROOT))
    ap.add_argument("--recipes-dir", default=str(DEFAULT_RECIPES_DIR))
    ap.add_argument("--tier-max", type=int, default=5)
    ap.add_argument("--sources", default="", help="space/comma list or file path")
    ap.add_argument("--only-no-docs", action="store_true")
    ap.add_argument("--only-unchunked", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--poll-timeout-sec", type=int, default=90)
    ap.add_argument("--index-timeout-sec", type=int, default=900)
    ap.add_argument("--no-index", action="store_true")
    ap.add_argument("--sync-fts-every", type=int, default=10)
    ap.add_argument("--log", default="eval/reports/full_directory_crawl_batch.jsonl")
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        print(f"DB not found: {db}", file=sys.stderr)
        return 1

    log_path = Path(args.log)
    wanted = parse_source_list(args.sources)
    sources = load_sources(
        db=db,
        tier_max=args.tier_max,
        source_ids=wanted,
        only_no_docs=args.only_no_docs,
        only_unchunked=args.only_unchunked,
    )
    if args.resume:
        done = load_done(log_path)
        sources = [s for s in sources if s.source_id not in done]
    if args.limit and args.limit > 0:
        sources = sources[: args.limit]

    start_rec = {
        "phase": "batch_start",
        "started_at": utc_now(),
        "source_count": len(sources),
        "tier_max": args.tier_max,
        "only_no_docs": args.only_no_docs,
        "only_unchunked": args.only_unchunked,
        "poll_timeout_sec": args.poll_timeout_sec,
        "index_timeout_sec": args.index_timeout_sec,
        "sync_fts_every": args.sync_fts_every,
    }
    append_log(log_path, start_rec)
    print(json.dumps(start_rec, ensure_ascii=False), flush=True)

    if args.dry_run:
        for s in sources:
            print(f"{s.source_id}\tT{s.tier}\tdocs={s.active_docs}\tchunks={s.chunks}\tunchunked={s.unchunked_docs}")
        return 0

    processed = 0
    for idx, src in enumerate(sources, 1):
        source_id = src.source_id
        before = source_stats(db, source_id)
        print(f"[{idx}/{len(sources)}] poll {source_id} T{src.tier}", flush=True)
        poll = run_command(
            [
                "./crawl",
                "poll",
                "--source",
                source_id,
                "--recipes-dir",
                str(args.recipes_dir),
                "--out-root",
                str(args.corpus_root),
            ],
            timeout_sec=args.poll_timeout_sec,
        )
        index = None
        if not args.no_index:
            print(f"[{idx}/{len(sources)}] index {source_id}", flush=True)
            index = run_command(
                [
                    "./crawl",
                    "index-chunks",
                    "--source",
                    source_id,
                    "--corpus-root",
                    str(args.corpus_root),
                ],
                timeout_sec=args.index_timeout_sec,
            )
        after = source_stats(db, source_id)
        rec = {
            "phase": "source_done",
            "finished_at": utc_now(),
            "source_id": source_id,
            "tier": src.tier,
            "before": before,
            "after": after,
            "docs_delta": after["active_docs"] - before["active_docs"],
            "chunks_delta": after["chunks"] - before["chunks"],
            "poll": poll,
            "index": index,
        }
        append_log(log_path, rec)
        processed += 1
        print(
            f"[{idx}/{len(sources)}] done {source_id} "
            f"docs_delta={rec['docs_delta']} chunks_delta={rec['chunks_delta']} "
            f"poll_rc={poll['returncode']} poll_timeout={poll['timed_out']}",
            flush=True,
        )
        if args.sync_fts_every > 0 and processed % args.sync_fts_every == 0:
            fts = sync_fts(db)
            append_log(log_path, {"phase": "fts_sync", "finished_at": utc_now(), **fts})
            print(f"[fts] +{fts['fts_added']} -> {fts['fts_after']}", flush=True)

    if args.sync_fts_every == 0:
        done_rec = {
            "phase": "batch_done",
            "finished_at": utc_now(),
            "processed": processed,
            "fts_skipped": True,
        }
        append_log(log_path, done_rec)
        print(json.dumps(done_rec, ensure_ascii=False), flush=True)
        return 0

    fts = sync_fts(db)
    done_rec = {
        "phase": "batch_done",
        "finished_at": utc_now(),
        "processed": processed,
        **fts,
    }
    append_log(log_path, done_rec)
    print(json.dumps(done_rec, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
