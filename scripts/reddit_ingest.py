#!/usr/bin/env python3
"""Reddit /r/Nepal ingestion pipeline for CPT corpus assembly.

Reads the arctic_shift archive at $REDDIT_RAW_DIR (73 .zst JSONL files,
~10.8 GB decompressed, 6.68 M records), filters to Nepali-content records
(Romanized Nepali, Devanagari, code-mixed), dedupes, strips Reddit markup,
and emits clean JSONL ready for tokenization.

Output schema:
    {
      "id":           reddit comment/post id
      "kind":         "comment" | "submission"
      "body":         cleaned text
      "created_utc":  int
      "score":        int
      "lang":         "roman_nepali" | "devanagari" | "code_mixed"
      "has_gov_kw":   bool (cheap pre-flag for gov-topic subset extraction)
      "orig_len":     int (chars before cleanup)
      "clean_len":    int
    }

Usage:
    python scripts/reddit_ingest.py [--raw-dir DIR] [--out FILE] [--max-records N]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

# --- Classification / filtering ------------------------------------------------

# Word-bounded markers (≥ 4 chars to avoid substring false-positives into English
# words like "mister", "mistakes", "you"). Matched via \b\b regex elsewhere.
ROMAN_NEPALI_MARKERS = frozenset(
    [
        "chha", "chhaina", "parcha", "parchha", "garnu", "janu", "malai",
        "mero", "timi", "tapai", "tapailai", "kaha", "kasari", "kina",
        "huncha", "hunchha", "bhayo", "gareko", "bhanchha", "bhaneko",
        "hola", "haru", "bhane", "bhayera", "nepali", "sanga", "garera",
        "chaiyo", "ramro", "naramro", "bhanera", "lagyo", "lagcha",
        "lagchha", "bhanne", "aile", "bhai", "didi", "pardaina",
        "pardaino", "garney", "garnu", "garchu", "garchha", "garchhu",
        "dherai", "thorai", "sabai", "arko", "aba", "ali",
    ]
)

# Word-bounded English markers — kept inline-spaced-form since tokenization
# is done via `in lower` substring check with surrounding spaces.
ENGLISH_MARKERS = frozenset(
    [" the ", " of ", " and ", " is ", " to ", " in ", " a ", " you ",
     " for ", " on ", " that ", " it ", " with ", " as ", " this ",
     " was ", " were ", " are ", " have ", " has ", " but ", " not "]
)

# Pre-compile union regex for Roman-NE markers — one pass over text per call.
_NE_MARKER_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(m) for m in ROMAN_NEPALI_MARKERS) + r")\b",
    re.IGNORECASE,
)

BOT_AUTHORS = frozenset(["AutoModerator", "RemindMeBot", "B0tRank", "imgurHubot"])

# Conservative list — covers company/tax/license/citizenship/passport ecosystems
# across scripts and common casual Roman-NE forms.
GOV_KEYWORDS = frozenset(
    [
        # English
        "passport", "citizenship", "pan card", "pan number", "vat",
        "inland revenue", "ird office", "driving license", "driving licence",
        "malpot", "nagarikta", "rahadani", "ocr office", "company registrar",
        "nepal rastra bank",
        # Devanagari
        "नागरिकता", "राहदानी", "दर्ता", "कार्यालय", "मन्त्रालय",
        "भन्सार", "मालपोत", "कम्पनी", "आन्तरिक राजस्व",
        # Roman-Nepali common forms
        "nagrikta", "bhansar", "rajaswo",
    ]
)

# Min/max body lengths to keep. <30 chars = noise; >8000 chars = probably junk post
MIN_LEN = 30
MAX_LEN = 8000


def classify_lang(text: str) -> str:
    """Returns one of: english, roman_nepali, devanagari, code_mixed, other.

    Roman-Nepali requires at least 3 word-bounded marker matches (not substring)
    AND strictly more Roman-NE markers than English markers. This is tight on
    purpose — previous loose version false-positived on English text containing
    short substrings that coincidentally matched short Nepali words (e.g.
    "ma" inside "mister", "mistakes"). Tight filter means we drop some real
    Roman-NE too, but for CPT we care much more about precision than recall.
    """
    deva = sum(1 for c in text if "\u0900" <= c <= "\u097F")
    latin = sum(1 for c in text if c.isalpha() and ord(c) < 128)
    total_alpha = deva + latin
    if total_alpha < 10:
        return "other"
    deva_ratio = deva / total_alpha

    if deva_ratio > 0.5:
        return "devanagari"
    if deva > 0 and deva_ratio > 0.05:
        return "code_mixed"

    # All-or-mostly Latin → disambiguate English vs Roman-Nepali
    lower = text.lower()
    eng_hits = sum(1 for w in ENGLISH_MARKERS if w in lower)
    ne_hits = len(_NE_MARKER_RE.findall(lower))
    if ne_hits >= 3 and ne_hits > eng_hits:
        return "roman_nepali"
    return "english"


# --- Cleanup ------------------------------------------------------------------

URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\(https?://[^)]+\)")
MENTION_RE = re.compile(r"/?u/\w+|/?r/\w+")
QUOTE_LINE_RE = re.compile(r"^\s*>+.*$", re.MULTILINE)
MULTI_WS_RE = re.compile(r"[\t ]+")
MULTI_NL_RE = re.compile(r"\n{3,}")
EDIT_TAG_RE = re.compile(r"(?im)^edit[^:]*:.*$")


def clean_body(text: str) -> str:
    # Replace markdown links with the link text
    text = MD_LINK_RE.sub(r"\1", text)
    # Strip bare URLs
    text = URL_RE.sub("", text)
    # Strip /u/ and /r/ mentions (references, not content)
    text = MENTION_RE.sub("", text)
    # Drop blockquote lines (almost always quoting someone else — not the author's voice)
    text = QUOTE_LINE_RE.sub("", text)
    # Drop "Edit:" / "edit 2:" footers
    text = EDIT_TAG_RE.sub("", text)
    # Normalize whitespace
    text = MULTI_WS_RE.sub(" ", text)
    text = MULTI_NL_RE.sub("\n\n", text)
    return text.strip()


def has_gov_keyword(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in GOV_KEYWORDS)


# --- Pipeline -----------------------------------------------------------------


def iter_zst_jsonl(path: Path):
    """Yield parsed JSON objects from a .zst-compressed JSONL file.

    Shells out to `zstd -dc` to avoid adding zstandard pip dependency.
    """
    proc = subprocess.Popen(
        ["zstd", "-dc", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=1024 * 1024,
    )
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            try:
                yield json.loads(line)
            except Exception:
                continue
    finally:
        proc.stdout.close()  # type: ignore[union-attr]
        proc.wait()


def extract_body(raw: dict, kind: str) -> str | None:
    # Comments: raw["body"]; Submissions: title + selftext.
    if kind == "comment":
        return raw.get("body")
    title = (raw.get("title") or "").strip()
    selftext = (raw.get("selftext") or "").strip()
    if title and selftext:
        return f"{title}\n\n{selftext}"
    return title or selftext or None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--raw-dir",
        default=os.environ.get("REDDIT_RAW_DIR", "/Users/cdjk/github/llm/new-place/data/raw"),
    )
    ap.add_argument(
        "--out",
        default="corpora/reddit_nepali.jsonl",
        help="Output JSONL (one record per line)",
    )
    ap.add_argument("--max-records", type=int, default=0, help="0 = all")
    ap.add_argument("--progress-every", type=int, default=200_000)
    args = ap.parse_args()

    raw_dir = Path(args.raw_dir)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    files = sorted(raw_dir.glob("*.jsonl.zst"))
    if not files:
        print(f"error: no .jsonl.zst files in {raw_dir}", file=sys.stderr)
        return 2
    print(f"input: {len(files)} files from {raw_dir}", file=sys.stderr)
    print(f"output: {out_path}", file=sys.stderr)

    # Counters
    seen_records = 0
    seen_bodies = 0
    kept = 0
    by_lang: dict[str, int] = {}
    by_kind: dict[str, int] = {}
    gov_hits = 0
    dupes = 0
    too_short = 0
    too_long = 0
    deleted = 0
    bot = 0
    english_skip = 0
    other_skip = 0

    seen_hashes: set[str] = set()
    t0 = time.time()

    with out_path.open("w", encoding="utf-8") as out_f:
        for fi, path in enumerate(files):
            for rec in iter_zst_jsonl(path):
                seen_records += 1
                kind = rec.get("kind") or ""
                raw = rec.get("raw") or {}
                body = extract_body(raw, kind)
                if not body:
                    continue
                author_raw = raw.get("author")
                author = author_raw if isinstance(author_raw, str) else ""
                if author in BOT_AUTHORS:
                    bot += 1
                    continue
                if body in ("[deleted]", "[removed]", ""):
                    deleted += 1
                    continue
                if len(body) < MIN_LEN:
                    too_short += 1
                    continue
                if len(body) > MAX_LEN:
                    too_long += 1
                    continue

                seen_bodies += 1
                cleaned = clean_body(body)
                if len(cleaned) < MIN_LEN:
                    too_short += 1
                    continue

                lang = classify_lang(cleaned)
                if lang == "english":
                    english_skip += 1
                    continue
                if lang == "other":
                    other_skip += 1
                    continue

                # Dedup on cleaned body hash
                h = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:16]
                if h in seen_hashes:
                    dupes += 1
                    continue
                seen_hashes.add(h)

                gov = has_gov_keyword(cleaned)
                if gov:
                    gov_hits += 1

                record = {
                    "id": raw.get("id") or raw.get("name") or h,
                    "kind": kind,
                    "body": cleaned,
                    "created_utc": raw.get("created_utc"),
                    "score": raw.get("score"),
                    "lang": lang,
                    "has_gov_kw": gov,
                    "orig_len": len(body),
                    "clean_len": len(cleaned),
                }
                out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                kept += 1
                by_lang[lang] = by_lang.get(lang, 0) + 1
                by_kind[kind] = by_kind.get(kind, 0) + 1

                if args.max_records and kept >= args.max_records:
                    break

                if seen_records % args.progress_every == 0:
                    elapsed = time.time() - t0
                    print(
                        f"  [{seen_records:>8,} seen  {kept:>7,} kept  "
                        f"{100*kept/max(1,seen_records):.2f}%]  "
                        f"file {fi+1}/{len(files)}  "
                        f"elapsed {elapsed:.0f}s",
                        file=sys.stderr,
                        flush=True,
                    )

            if args.max_records and kept >= args.max_records:
                break

    elapsed = time.time() - t0
    print("", file=sys.stderr)
    print("=== ingestion summary ===", file=sys.stderr)
    print(f"records seen:          {seen_records:>10,}", file=sys.stderr)
    print(f"non-empty bodies:      {seen_bodies:>10,}", file=sys.stderr)
    print(f"deleted/removed:       {deleted:>10,}", file=sys.stderr)
    print(f"bot authors:           {bot:>10,}", file=sys.stderr)
    print(f"too short (<{MIN_LEN} ch):   {too_short:>10,}", file=sys.stderr)
    print(f"too long (>{MAX_LEN} ch):  {too_long:>10,}", file=sys.stderr)
    print(f"english (skipped):     {english_skip:>10,}", file=sys.stderr)
    print(f"other-lang (skipped):  {other_skip:>10,}", file=sys.stderr)
    print(f"duplicates:            {dupes:>10,}", file=sys.stderr)
    print(f"kept:                  {kept:>10,}", file=sys.stderr)
    print("", file=sys.stderr)
    print("kept by language:", file=sys.stderr)
    for l, c in sorted(by_lang.items(), key=lambda x: -x[1]):
        print(f"  {l:<16} {c:>8,}", file=sys.stderr)
    print("kept by kind:", file=sys.stderr)
    for k, c in sorted(by_kind.items(), key=lambda x: -x[1]):
        print(f"  {k:<16} {c:>8,}", file=sys.stderr)
    print(f"gov-keyword hits:      {gov_hits:>10,}  ({100*gov_hits/max(1,kept):.1f}% of kept)", file=sys.stderr)
    print("", file=sys.stderr)
    print(f"elapsed: {elapsed:.0f}s", file=sys.stderr)
    print(f"output:  {out_path}  ({out_path.stat().st_size/1024/1024:.1f} MB)", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
