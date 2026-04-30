#!/usr/bin/env python3
"""Format SFT v2 mix into trainer-ready messages JSONL.

v2 = v1 (3 slices) + 4 new capability/refusal slices:

  v1 slices (preserved from format_sft_v1.py):
    grounded_distilled       — 6553   reverse-instruction grounded answers
    native_ne_alpaca         — 1500   Saugatkafley Devanagari instructions
    english_replay           — 1500   TULU 3 English replay (anti-forgetting)

  v2 new slices (this file adds):
    refusal_distilled        — 1100   "I cannot find an authoritative source"
                                       in three languages × three categories
                                       (empty / partial / off_domain)
    translation_distilled    — 500    FLORES-200 NE↔EN translation pairs
                                       (excludes the 30 dev-set indices used
                                       in nepali_capability_eval to avoid
                                       contamination)
    mc_distilled             — ~443   trivia-style A/B/C/D MC, mostly
                                       bare-letter answers, mixes 3 langs
    brief_qa_distilled       — 300    short conversational Q&A without
                                       chunks; biased toward Roman-Nepali
                                       to fix the v1 degeneration on short
                                       Roman-NE prompts

Total target: ~11,400 records, 95/5 stratified train/val.

Each formatted record:
  {
    "messages": [
      {"role": "system",    "content": "..."},   # only for grounded + refusal
      {"role": "user",      "content": "..."},
      {"role": "assistant", "content": "..."}
    ],
    "source": "<slice tag>",
    "lang":   "...",
    "category": "...",
    "split": "train" | "val"
  }

The grounded + refusal slices share the SYSTEM_GROUNDED prompt because
they share the same task contract (cite-or-refuse). The other slices have
no system prompt — they're general-capability training.

Usage:
    python scripts/format_sft_v2.py
    python scripts/format_sft_v2.py --val-frac 0.05 --seed 42
"""
from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from pathlib import Path
from typing import Iterable


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

CHUNK_TEXT_MAX_CHARS = 1200


def _chunks_text(chunks: list) -> str:
    if not chunks:
        return "(no candidate sources surfaced)"
    parts = []
    for i, c in enumerate(chunks, 1):
        text = (c.get("text") or "")[:CHUNK_TEXT_MAX_CHARS]
        parts.append(f"[{c.get('rank', i)}] {c.get('url', '')}\n{text}")
    return "\n\n".join(parts)


def format_grounded(rec: dict) -> dict | None:
    """3-turn (system + user + assistant). For grounded slice + refusal slice
    (same task contract: cite-or-refuse)."""
    if rec.get("skip"):
        return None
    q = (rec.get("question") or "").strip()
    a = (rec.get("answer") or "").strip()
    if not q or not a:
        return None
    chunks = rec.get("chunks") or []
    user = f"Question: {q}\n\nSources:\n{_chunks_text(chunks)}"
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_GROUNDED},
            {"role": "user", "content": user},
            {"role": "assistant", "content": a},
        ],
        "source": rec.get("source") or "grounded_distilled",
        "lang": rec.get("question_lang") or "devanagari",
        "category": rec.get("category") or "other",
    }


def format_native_ne(rec: dict) -> dict | None:
    """Saugatkafley Alpaca-NE → 2-turn (no system, no chunks)."""
    if rec.get("skip"):
        return None
    q = (rec.get("question") or "").strip()
    a = (rec.get("answer") or "").strip()
    if not q or not a:
        return None
    return {
        "messages": [
            {"role": "user", "content": q},
            {"role": "assistant", "content": a},
        ],
        "source": "native_ne_alpaca",
        "lang": rec.get("question_lang") or "devanagari",
        "category": "other",
    }


def format_english(rec: dict) -> dict | None:
    """TULU 3 / FLAN v2 English replay → 2-turn."""
    if rec.get("skip"):
        return None
    q = (rec.get("question") or "").strip()
    a = (rec.get("answer") or "").strip()
    if not q or not a:
        return None
    return {
        "messages": [
            {"role": "user", "content": q},
            {"role": "assistant", "content": a},
        ],
        "source": "english_replay",
        "lang": "english",
        "category": "other",
    }


def format_capability(rec: dict) -> dict | None:
    """Translation / MC / brief Q&A — 2-turn, no system prompt, no chunks.

    These are *general-capability preservation* records — we deliberately
    don't wrap them in the gov-helpdesk system prompt because the goal is
    to teach the model to handle prompts of these shapes too, not just the
    grounded-helpdesk contract."""
    if rec.get("skip"):
        return None
    q = (rec.get("question") or "").strip()
    a = (rec.get("answer") or "").strip()
    if not q or not a:
        return None
    return {
        "messages": [
            {"role": "user", "content": q},
            {"role": "assistant", "content": a},
        ],
        "source": rec.get("source") or "capability_distilled",
        "lang": rec.get("question_lang") or "english",
        "category": rec.get("category") or "other",
    }


SLICE_FORMATTERS: dict[str, tuple[str, callable]] = {
    "grounded":       ("corpora/sft_v1_grounded.jsonl",      format_grounded),
    "native_ne":      ("corpora/sft_v1_native_ne.jsonl",     format_native_ne),
    "english_replay": ("corpora/sft_v1_english_replay.jsonl", format_english),
    "refusal":        ("corpora/sft_v2_refusals.jsonl",      format_grounded),
    "translation":    ("corpora/sft_v2_translation.jsonl",   format_capability),
    "mc":             ("corpora/sft_v2_mc.jsonl",            format_capability),
    "brief_qa":       ("corpora/sft_v2_brief_qa.jsonl",      format_capability),
}


def load_and_format(slice_name: str, formatter, path: Path) -> list[dict]:
    out: list[dict] = []
    if not path.exists():
        logging.warning("missing %s — skipping slice %s", path, slice_name)
        return out
    with path.open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            o = formatter(r)
            if o is not None:
                out.append(o)
    logging.info("loaded slice %s: %d records", slice_name, len(out))
    return out


def stratified_split(
    records_by_slice: dict[str, list[dict]],
    val_frac: float,
    rng: random.Random,
) -> tuple[list[dict], list[dict]]:
    train: list[dict] = []
    val: list[dict] = []
    for slice_name, records in records_by_slice.items():
        rng.shuffle(records)
        n_val = max(1, int(len(records) * val_frac))
        val.extend(records[:n_val])
        train.extend(records[n_val:])
        logging.info(
            "  %s: train=%d val=%d", slice_name, len(records) - n_val, n_val
        )
    rng.shuffle(train)
    rng.shuffle(val)
    return train, val


def write_jsonl(records: Iterable[dict], path: Path) -> int:
    n = 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-out", default="corpora/sft_v2_train.jsonl")
    ap.add_argument("--val-out", default="corpora/sft_v2_val.jsonl")
    ap.add_argument("--val-frac", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    records_by_slice: dict[str, list[dict]] = {}
    for slice_name, (path_str, fmt) in SLICE_FORMATTERS.items():
        records_by_slice[slice_name] = load_and_format(
            slice_name, fmt, Path(path_str)
        )
    total = sum(len(v) for v in records_by_slice.values())
    logging.info("total formatted: %d", total)
    if total == 0:
        print("no records to format", file=sys.stderr)
        return 1

    rng = random.Random(args.seed)
    train, val = stratified_split(records_by_slice, args.val_frac, rng)

    for r in train:
        r["split"] = "train"
    for r in val:
        r["split"] = "val"

    n_train = write_jsonl(train, Path(args.train_out))
    n_val = write_jsonl(val, Path(args.val_out))

    print(f"\n=== format v2 summary ===", file=sys.stderr)
    print(f"  total formatted: {total}", file=sys.stderr)
    print(f"  train ({n_train}): {args.train_out}", file=sys.stderr)
    print(f"  val   ({n_val}): {args.val_out}", file=sys.stderr)
    print(f"  val fraction: {n_val / total:.1%}", file=sys.stderr)

    # Per-slice composition for sanity
    from collections import Counter
    train_counts = Counter(r["source"] for r in train)
    val_counts = Counter(r["source"] for r in val)
    print(f"\n  composition (train / val):", file=sys.stderr)
    for src in sorted(set(list(train_counts) + list(val_counts))):
        print(f"    {src:>22s}: {train_counts.get(src, 0):>5d} / {val_counts.get(src, 0):>4d}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
