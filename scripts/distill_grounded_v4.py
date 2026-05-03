#!/usr/bin/env python3
"""SFT v4 grounded slice — retrieval-realistic distillation.

Differs from v1's `generate_sft_grounded.py` in one critical way: the teacher
answers from RETRIEVED chunks, not from the seed chunk that prompted the
question. This eliminates the train/serve mismatch v3a still had — at
inference, the model sees retrieval results, never the "ground-truth" chunk
that would have produced a clean question, so training on retrieval results
matches what the model will actually face.

Pipeline:
    Step 1: Pick N seed chunks across categories (skips mojibake-flagged).
    Step 2: For each seed, generate ONE citizen question (DeepSeek, batched).
    Step 3: For each question, run BILINGUAL FTS retrieval against the cleaned
            corpus → top-K chunks (top-5 by default, matching server config).
    Step 4: For each (question, retrieved_chunks), call DeepSeek with the
            SYSTEM_GROUNDED prompt. The teacher either cites + answers, OR
            refuses if retrieval missed the relevant content. Both outcomes
            are valid training data — the v4 model needs to learn both.
    Step 5: Write JSONL matching format_sft_v4.py's `format_grounded` reader.

Designed to run ON k2 (corpus DB lives there). For local runs, mount k2's
DB read-only over SSHFS and pass --db.

Cost estimate: 5500 items × (1 question call + 1 answer call) at DeepSeek
V4-Flash rates ≈ $5-7. Wallclock with --concurrency 12 ≈ 2h.

Usage on k2:
    python3 scripts/distill_grounded_v4.py \\
        --db /Volumes/T9/gemma-god/corpus_v2/index.db \\
        --n 5500 \\
        --out corpora/sft_v4_grounded.jsonl \\
        --concurrency 12 \\
        --seed 42

    # Smoke (10 items, validates the pipeline + cost budget):
    python3 scripts/distill_grounded_v4.py \\
        --db /Volumes/T9/gemma-god/corpus_v2/index.db \\
        --n 10 --concurrency 2
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

# ---- Config ----------------------------------------------------------------

DEFAULT_TOP_K = 5  # matches server's TOP_K_GOV when tacit isn't in play
CHUNK_TEXT_MAX_CHARS = 1200
CHUNK_MIN_LEN = 200    # skip nav/header garbage
CHUNK_MAX_LEN = 4000   # skip giant scraped tables

DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
DEEPSEEK_BASE = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/anthropic")

# ---- Bilingual anchor map (mirrored from server/main.py) -------------------
# Single source of truth; keeping a copy here avoids importing FastAPI from
# server/main.py (which would trigger model load).
BILINGUAL_ANCHORS: dict[str, tuple[str, ...]] = {
    "citizenship": ("नागरिकता", "नागरिकता प्रमाणपत्र"),
    "nagarikta":   ("नागरिकता",),
    "passport":    ("राहदानी",),
    "rahadani":    ("राहदानी",),
    "license":     ("लाइसेन्स", "अनुमतिपत्र"),
    "licence":     ("लाइसेन्स", "अनुमतिपत्र"),
    "anumatipatra":("अनुमतिपत्र",),
    "certificate": ("प्रमाणपत्र",),
    "pramanpatra": ("प्रमाणपत्र",),
    "recommendation": ("सिफारिश",),
    "sifarish":    ("सिफारिश",),
    "voter":       ("मतदाता", "मतदाता परिचयपत्र"),
    "matadata":    ("मतदाता",),
    "lost":        ("हराएमा", "हराएको"),
    "haraayo":     ("हराएमा",),
    "haraayeko":   ("हराएमा",),
    "renew":       ("नविकरण",),
    "nawikaran":   ("नविकरण",),
    "nabikaran":   ("नविकरण",),
    "apply":       ("निवेदन",),
    "application": ("निवेदन",),
    "nibedan":     ("निवेदन",),
    "register":    ("दर्ता",),
    "registration":("दर्ता",),
    "darta":       ("दर्ता",),
    "replace":     ("प्रतिलिपि",),
    "duplicate":   ("प्रतिलिपि",),
    "office":      ("कार्यालय",),
    "karyalaya":   ("कार्यालय",),
    "ministry":    ("मन्त्रालय",),
    "mantralaya":  ("मन्त्रालय",),
    "department":  ("विभाग",),
    "vibhag":      ("विभाग",),
    "municipality":("नगरपालिका",),
    "nagarpalika": ("नगरपालिका",),
    "ward":        ("वडा",),
    "wada":        ("वडा",),
    "district":    ("जिल्ला",),
    "jilla":       ("जिल्ला",),
    "dao":         ("जिल्ला प्रशासन कार्यालय",),
    "cdo":         ("प्रमुख जिल्ला अधिकारी",),
    "police":      ("प्रहरी",),
    "prahari":     ("प्रहरी",),
    "birth":       ("जन्म दर्ता",),
    "death":       ("मृत्यु दर्ता",),
    "marriage":    ("विवाह दर्ता",),
    "vivah":       ("विवाह",),
    "janma":       ("जन्म",),
    "mrityu":      ("मृत्यु",),
    "tax":         ("कर", "मालपोत"),
    "kar":         ("कर",),
    "malpot":      ("मालपोत",),
    "land":        ("जग्गा",),
    "jagga":       ("जग्गा",),
    "fee":         ("शुल्क",),
    "shulka":      ("शुल्क",),
    "nepal":       ("नेपाल",),
    "government":  ("सरकार",),
    "sarkar":      ("सरकार",),
    "citizen":     ("नागरिक",),
    "service":     ("सेवा",),
    "newspaper":   ("पत्रिका",),
    "patrika":     ("पत्रिका",),
}


# ---- System prompts --------------------------------------------------------

SYSTEM_GROUNDED = """\
You are a Nepal-government helpdesk. Answer the question using ONLY the \
provided gov.np sources.

HARD RULES:
1. After every factual claim, cite the source URL in square brackets, e.g. \
[https://www.moha.gov.np/...].
2. If a claim is not directly supported by ANY source, drop it or mark \
[unverified].
3. If NO source meaningfully addresses the question, refuse with: \
"मलाई यो प्रश्नको आधिकारिक स्रोत भेटिनँ" (Devanagari) or \
"Yo prashnako adhikarik srot bhetina" (Roman-Nepali) or \
"I cannot find an authoritative source for this" (English) — match \
the question's language.
4. Respond in the same language/script as the question.
5. Be concise and procedural.
6. Do NOT introduce yourself, do NOT mention being an AI, do NOT use vendor \
names."""

SYSTEM_QGEN = """\
You are generating training data for a Nepal-government helpdesk. Given a \
chunk of text from a gov.np document, write ONE realistic question a citizen \
might type into a search box that this chunk would help answer.

RULES:
- Question must be answerable from the chunk's content
- Use Devanagari, Roman-Nepali, English, or code-mixed — vary across the batch
- Conversational, not bookish. NOT "What is the citizenship process?" but \
"How do I get my citizenship certificate?" or "नागरिकता प्रमाणपत्र कसरी \
बनाउने?" or "Nagarikta kasari banaune?"
- 5-25 words, no leading "Q:" or numbering
- ONE question only — no preamble, no explanation"""


# ---- DeepSeek client (Anthropic-shape) -------------------------------------

def _read_deepseek_key() -> str:
    k = os.environ.get("DEEPSEEK_API_KEY")
    if k:
        return k
    fmw = Path.home() / ".fmw" / "deepseek"
    if fmw.exists():
        return fmw.read_text().strip()
    fmw_kv = Path.home() / ".fmw"
    if fmw_kv.exists():
        for line in fmw_kv.read_text().splitlines():
            if line.startswith("DEEPSEEK="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError(
        "DeepSeek API key not found. Set $DEEPSEEK_API_KEY or write to ~/.fmw/deepseek"
    )


class DeepSeek:
    """Thin DeepSeek (Anthropic-shape) client. Always sends thinking-disabled
    so V4-Flash doesn't burn tokens on internal reasoning."""

    def __init__(self, model: str = DEEPSEEK_MODEL, base_url: str = DEEPSEEK_BASE):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key = _read_deepseek_key()

    def chat(self, system: str, user: str, max_tokens: int = 800, retries: int = 3) -> str:
        payload = json.dumps({
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "thinking": {"type": "disabled"},
        }).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }
        last_err: Exception | None = None
        for attempt in range(retries):
            try:
                req = urllib.request.Request(
                    f"{self.base_url}/v1/messages",
                    data=payload, headers=headers, method="POST",
                )
                with urllib.request.urlopen(req, timeout=120) as resp:
                    data = json.loads(resp.read())
                parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
                return "".join(parts).strip()
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="replace")
                last_err = RuntimeError(f"HTTP {e.code}: {err_body[:300]}")
                if e.code in (429, 500, 502, 503, 504):
                    time.sleep(2 ** attempt)
                    continue
                raise last_err
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
                last_err = e
                time.sleep(2 ** attempt)
        raise RuntimeError(f"DeepSeek call failed after {retries} attempts: {last_err}")


# ---- Retrieval (mirrors server/main.py::Retriever.search) ------------------

def fts_search(conn: sqlite3.Connection, question: str, top_k: int = DEFAULT_TOP_K) -> list[dict]:
    """Bilingual FTS5 retrieval, mirroring server/main.py::Retriever.search.
    Strips non-word/Devanagari, lowercases ASCII, expands via BILINGUAL_ANCHORS,
    OR-joins quoted tokens, ranks by bm25."""
    cleaned = re.sub(r'[^\w\sऀ-ॿ]+', ' ', question).strip()
    if not cleaned:
        return []
    raw_tokens = [t.lower().strip() for t in cleaned.split() if t.strip()]
    expanded: list[str] = []
    for t in raw_tokens:
        if len(t) < 2:
            continue
        expanded.append(t)
        for extra in BILINGUAL_ANCHORS.get(t, ()):
            for sub in extra.split():
                if sub and sub not in expanded:
                    expanded.append(sub)
    if not expanded:
        return []
    fts_query = " OR ".join(f'"{t.replace(chr(34), chr(34)*2)}"' for t in expanded)
    try:
        rows = conn.execute(
            """
            SELECT chunks.chunk_id, chunks.text, documents.url,
                   sources.domain AS host, bm25(chunks_fts) AS score
              FROM chunks_fts
              JOIN chunks    ON chunks.chunk_id = chunks_fts.chunk_id
              JOIN documents ON documents.doc_id = chunks.doc_id
              JOIN sources   ON sources.source_id = documents.source_id
             WHERE chunks_fts MATCH ?
             ORDER BY score
             LIMIT ?
            """,
            (fts_query, top_k),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    out: list[dict] = []
    for i, r in enumerate(rows, 1):
        out.append({
            "rank": i,
            "chunk_id": r[0],
            "text": (r[1] or "")[:CHUNK_TEXT_MAX_CHARS],
            "url": r[2],
            "host": r[3],
            "score": float(r[4]) if r[4] is not None else None,
        })
    return out


# ---- Seed chunk selection --------------------------------------------------

def select_seed_chunks(db_path: Path, n: int, rng: random.Random) -> list[dict]:
    """Pick N seed chunks across language=devanagari/mixed/latin (skip
    mojibake_suspected — those got dropped during the rebuild but be defensive).
    Filter by length to skip nav/garbage."""
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        """
        SELECT chunks.chunk_id, chunks.text, documents.url,
               sources.source_id AS source_id,
               documents.doc_id, chunks.language
          FROM chunks
          JOIN documents ON chunks.doc_id = documents.doc_id
          JOIN sources   ON documents.source_id = sources.source_id
         WHERE documents.superseded_by IS NULL
           AND documents.removed_at IS NULL
           AND length(chunks.text) BETWEEN ? AND ?
           AND coalesce(chunks.language, 'unknown') != 'mojibake_suspected'
        """,
        (CHUNK_MIN_LEN, CHUNK_MAX_LEN),
    ).fetchall()
    conn.close()
    pool = [
        {
            "chunk_id": r[0], "text": r[1], "url": r[2],
            "source_id": r[3], "doc_id": r[4], "language": r[5],
        }
        for r in rows
    ]
    rng.shuffle(pool)
    if len(pool) < n:
        logging.warning("only %d eligible chunks (asked for %d) — using all", len(pool), n)
        return pool
    return pool[:n]


# ---- Pipeline --------------------------------------------------------------

def gen_question(seed: dict, ds: DeepSeek) -> str | None:
    excerpt = (seed["text"] or "")[:CHUNK_TEXT_MAX_CHARS]
    user = f"Document URL: {seed['url']}\n\nChunk:\n{excerpt}\n\nWrite ONE question:"
    try:
        q = ds.chat(SYSTEM_QGEN, user, max_tokens=200)
    except Exception as e:
        logging.warning("qgen failed for %s: %s", seed["chunk_id"], e)
        return None
    # Sanitize — strip "Q:", trailing punctuation noise, multi-line
    q = q.strip().split("\n")[0].strip()
    q = re.sub(r"^(Q[:.]\s*|Question[:.]\s*)", "", q, flags=re.I).strip()
    if len(q) < 8:
        return None
    return q


def detect_lang(s: str) -> str:
    has_dev = any('ऀ' <= c <= 'ॿ' for c in s)
    has_lat = any(c.isascii() and c.isalpha() for c in s)
    if has_dev and has_lat:
        return "code_mixed"
    if has_dev:
        return "devanagari"
    return "roman_nepali" if any(t in s.lower() for t in ("kasari", "ko", "ka", "mero")) else "english"


def gen_answer(question: str, chunks: list[dict], ds: DeepSeek) -> str | None:
    if not chunks:
        sources_block = "(no candidate sources surfaced)"
    else:
        parts = []
        for c in chunks:
            parts.append(f"[{c['rank']}] {c['url']}\n{c['text']}")
        sources_block = "\n\n".join(parts)
    user = f"Question: {question}\n\nSources:\n{sources_block}"
    try:
        return ds.chat(SYSTEM_GROUNDED, user, max_tokens=800)
    except Exception as e:
        logging.warning("answer gen failed for %r: %s", question[:60], e)
        return None


def process_one(seed: dict, ds: DeepSeek, db_path: Path, top_k: int) -> dict | None:
    q = gen_question(seed, ds)
    if not q:
        return None
    # Each thread gets its own SQLite conn — sqlite is !Sync.
    conn = sqlite3.connect(db_path)
    try:
        retrieved = fts_search(conn, q, top_k=top_k)
    finally:
        conn.close()
    answer = gen_answer(q, retrieved, ds)
    if not answer:
        return None
    return {
        "id": f"sft_v4_grnd_{seed['chunk_id'][:12]}",
        "source": "v4_grounded_retrieval",
        "question": q,
        "question_lang": detect_lang(q),
        "category": "other",  # source-level categorization deferred
        "chunks": [
            {"rank": c["rank"], "url": c["url"], "text": c["text"]}
            for c in retrieved
        ],
        "answer": answer,
        "seed_chunk_id": seed["chunk_id"],
        "seed_url": seed["url"],
        "seed_in_retrieved": any(c["chunk_id"] == seed["chunk_id"] for c in retrieved),
        "n_retrieved": len(retrieved),
        "skip": False,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="/Volumes/T9/gemma-god/corpus_v2/index.db",
                    help="path to corpus_v2 index.db (cleaned, post-rebuild)")
    ap.add_argument("--n", type=int, default=5500, help="target items")
    ap.add_argument("--out", default="corpora/sft_v4_grounded.jsonl")
    ap.add_argument("--top-k", type=int, default=DEFAULT_TOP_K,
                    help="retrieval top-K (matches server config; default 5)")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--limit", type=int, default=0,
                    help="hard cap on items processed (smoke runs)")
    ap.add_argument("--resume", action="store_true",
                    help="skip seeds whose IDs already appear in --out")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: db not found: {db_path}", file=sys.stderr)
        return 1
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rng = random.Random(args.seed)
    seeds = select_seed_chunks(db_path, args.n, rng)
    logging.info("selected %d seed chunks", len(seeds))

    done_ids: set[str] = set()
    if args.resume and out_path.exists():
        for line in out_path.open(encoding="utf-8"):
            try:
                done_ids.add(json.loads(line).get("seed_chunk_id", ""))
            except Exception:
                pass
        logging.info("resume: %d already done", len(done_ids))

    pending = [s for s in seeds if s["chunk_id"] not in done_ids]
    if args.limit > 0:
        pending = pending[:args.limit]
    logging.info("processing %d items", len(pending))

    ds = DeepSeek()
    write_lock = Lock()
    n_ok = 0
    n_err = 0
    n_refused = 0
    started = time.time()

    with out_path.open("a", encoding="utf-8") as fout, \
         ThreadPoolExecutor(max_workers=args.concurrency) as ex:
        futs = {ex.submit(process_one, s, ds, db_path, args.top_k): s for s in pending}
        for i, fut in enumerate(as_completed(futs), 1):
            try:
                rec = fut.result()
            except Exception as e:
                logging.warning("worker exception: %s", e)
                n_err += 1
                continue
            if rec is None:
                n_err += 1
                continue
            if "मलाई यो प्रश्नको आधिकारिक स्रोत" in rec["answer"] \
               or "Yo prashnako adhikarik" in rec["answer"] \
               or "I cannot find an authoritative source" in rec["answer"]:
                n_refused += 1
            with write_lock:
                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                fout.flush()
            n_ok += 1
            if i % 25 == 0:
                elapsed = time.time() - started
                rate = i / elapsed if elapsed > 0 else 0
                logging.info(
                    "[%d/%d] ok=%d err=%d refused=%d (%.1f items/sec, %.0fs elapsed)",
                    i, len(pending), n_ok, n_err, n_refused, rate, elapsed,
                )

    print(f"\n=== distill_grounded_v4 summary ===", file=sys.stderr)
    print(f"  attempted   : {len(pending)}", file=sys.stderr)
    print(f"  ok          : {n_ok}", file=sys.stderr)
    print(f"  errors      : {n_err}", file=sys.stderr)
    print(f"  refused     : {n_refused} ({100*n_refused/max(n_ok,1):.1f}%)", file=sys.stderr)
    print(f"  output      : {out_path}", file=sys.stderr)
    print(f"  wallclock   : {time.time()-started:.0f}s", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
