#!/usr/bin/env python3
"""Format SFT v4 mix into trainer-ready messages JSONL.

v4 = full retrieval-realistic mix per the codex-vetted plan (see
SFT_V3A_RESULTS.md §next-steps and project_v3a_done_v4_plan.md).

Slices (target 16,000 records, 95/5 train/val):

  Retrieval-realistic (NEW vs v3a — built against the cleaned k2 corpus):
    grounded                — corpora/sft_v4_grounded.jsonl       (5500)  re-distill via prod retriever
    refusal                 — corpora/sft_v4_refusal.jsonl        (3600)  6 subcategories, retrieval-realistic
    anti_template           — corpora/sft_v4_anti_template.jsonl   (600)  upgrade from v3a's 270 with REAL chunks
    grounded_terse          — corpora/sft_v4_grounded_terse.jsonl  (350)  terse versions of grounded items
                                                                          (drop v3a's 139 open-ended terse —
                                                                          suspected Roman-NE degen culprit)

  Carryovers + bucket-pulled English replay:
    brief_qa                — corpora/sft_v4_brief_qa.jsonl        (700)
    english_replay_math     — corpora/sft_v4_english_replay_math.jsonl    (1200)  numinamath
    english_replay_instr    — corpora/sft_v4_english_replay_instr.jsonl   (1200)  no_robots / clean instr
    english_replay_mc       — corpora/sft_v4_english_replay_mc.jsonl       (400)  flan MC
    english_replay_reasn    — corpora/sft_v4_english_replay_reasn.jsonl    (200)  sciriff
    native_ne               — corpora/sft_v1_native_ne.jsonl       (1200)  v1 carryover (downweight from 1500)
    translation             — corpora/sft_v2_translation.jsonl     (500)   v2 carryover
    mc                      — corpora/sft_v4_mc.jsonl              (550)   v2's 443 + 107 top-up

Refusal share = (3600 + 600) / 16000 = 26.25%, hits codex §5 target naturally.

Output schema unchanged from v3 — same SYSTEM_GROUNDED prompt, same chunk-
in-user-message format. Stratified 95/5 train/val.

Usage:
    python scripts/format_sft_v4.py
    # Custom output:
    python scripts/format_sft_v4.py \\
        --train-out corpora/sft_v4_train.jsonl \\
        --val-out corpora/sft_v4_val.jsonl \\
        --val-frac 0.05 --seed 42
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

# Target counts per codex v4 spec — for assertion/warn during composition.
TARGET_COUNTS: dict[str, int] = {
    "grounded": 5500,
    "refusal_v4": 3600,
    "anti_template": 600,
    "grounded_terse": 350,
    "brief_qa": 700,
    "english_replay_math": 1200,
    "english_replay_instr": 1200,
    "english_replay_mc": 400,
    "english_replay_reasn": 200,
    "native_ne": 1200,
    "translation": 500,
    "mc": 550,
}


def _chunks_text(chunks: list) -> str:
    if not chunks:
        return "(no candidate sources surfaced)"
    parts = []
    for i, c in enumerate(chunks, 1):
        text = (c.get("text") or "")[:CHUNK_TEXT_MAX_CHARS]
        parts.append(f"[{c.get('rank', i)}] {c.get('url', '')}\n{text}")
    return "\n\n".join(parts)


def format_grounded(rec: dict) -> dict | None:
    """3-turn (system + user + assistant) — for grounded, refusal,
    anti-template, grounded-terse. All share the cite-or-refuse contract."""
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
        "source": rec.get("source") or "english_replay",
        "lang": "english",
        "category": "other",
    }


def format_capability(rec: dict) -> dict | None:
    """For translation, MC, brief_qa, terse — 2-turn, no system, no chunks
    (or single chunk for grounded_terse if present)."""
    if rec.get("skip"):
        return None
    q = (rec.get("question") or "").strip()
    a = (rec.get("answer") or "").strip()
    if not q or not a:
        return None
    chunks = rec.get("chunks") or []
    if chunks:
        user = f"Question: {q}\n\nSources:\n{_chunks_text(chunks)}"
    else:
        user = q
    return {
        "messages": [
            {"role": "user", "content": user},
            {"role": "assistant", "content": a},
        ],
        "source": rec.get("source") or "capability_distilled",
        "lang": rec.get("question_lang") or "english",
        "category": rec.get("category") or "other",
    }


SLICE_FORMATTERS: dict[str, tuple[str, callable]] = {
    # Retrieval-realistic (built against cleaned k2 corpus)
    "grounded":              ("corpora/sft_v4_grounded.jsonl",              format_grounded),
    "refusal_v4":            ("corpora/sft_v4_refusal.jsonl",               format_grounded),
    "anti_template":         ("corpora/sft_v4_anti_template.jsonl",         format_grounded),
    "grounded_terse":        ("corpora/sft_v4_grounded_terse.jsonl",        format_grounded),
    # Carryover + new buckets
    "brief_qa":              ("corpora/sft_v4_brief_qa.jsonl",              format_capability),
    "english_replay_math":   ("corpora/sft_v4_english_replay_math.jsonl",   format_english),
    "english_replay_instr":  ("corpora/sft_v4_english_replay_instr.jsonl",  format_english),
    "english_replay_mc":     ("corpora/sft_v4_english_replay_mc.jsonl",     format_english),
    "english_replay_reasn":  ("corpora/sft_v4_english_replay_reasn.jsonl",  format_english),
    "native_ne":             ("corpora/sft_v1_native_ne.jsonl",             format_native_ne),
    "translation":           ("corpora/sft_v2_translation.jsonl",           format_capability),
    "mc":                    ("corpora/sft_v4_mc.jsonl",                    format_capability),
}


def load_and_format(slice_name: str, formatter, path: Path) -> list[dict]:
    out: list[dict] = []
    if not path.exists():
        logging.warning("MISSING: %s — slice %s contributes 0 records", path, slice_name)
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
        n_val = max(1, int(len(records) * val_frac)) if records else 0
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
    ap.add_argument("--train-out", default="corpora/sft_v4_train.jsonl")
    ap.add_argument("--val-out", default="corpora/sft_v4_val.jsonl")
    ap.add_argument("--val-frac", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--allow-missing", action="store_true",
        help="if set, treat missing slice files as empty (warn) instead of bailing. "
        "Default: bail if any slice file is missing — safer for production runs.",
    )
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    # Pre-flight: check all slice files exist (unless --allow-missing).
    missing = [name for name, (path, _) in SLICE_FORMATTERS.items()
               if not Path(path).exists()]
    if missing and not args.allow_missing:
        print(f"\nERROR: missing slice files for v4:", file=sys.stderr)
        for name in missing:
            print(f"  - {name}: {SLICE_FORMATTERS[name][0]}", file=sys.stderr)
        print("\nRe-run with --allow-missing to compose a partial mix, or "
              "build the missing slices first.", file=sys.stderr)
        return 1

    records_by_slice: dict[str, list[dict]] = {}
    for slice_name, (path_str, fmt) in SLICE_FORMATTERS.items():
        records_by_slice[slice_name] = load_and_format(
            slice_name, fmt, Path(path_str)
        )
    total = sum(len(v) for v in records_by_slice.values())
    logging.info("total formatted: %d (target 16000)", total)
    if total == 0:
        print("no records to format", file=sys.stderr)
        return 1

    # Composition warnings: flag any slice that's significantly off-target.
    print("\n  composition vs target:", file=sys.stderr)
    for slice_name, target in TARGET_COUNTS.items():
        actual = len(records_by_slice.get(slice_name, []))
        delta = actual - target
        flag = "  " if abs(delta) <= max(50, target // 10) else "!!"
        print(f"  {flag} {slice_name:<26s} actual={actual:>5d} target={target:>5d} delta={delta:+d}", file=sys.stderr)

    rng = random.Random(args.seed)
    train, val = stratified_split(records_by_slice, args.val_frac, rng)

    for r in train:
        r["split"] = "train"
    for r in val:
        r["split"] = "val"

    n_train = write_jsonl(train, Path(args.train_out))
    n_val = write_jsonl(val, Path(args.val_out))

    print(f"\n=== format v4 summary ===", file=sys.stderr)
    print(f"  total formatted: {total}", file=sys.stderr)
    print(f"  train ({n_train}): {args.train_out}", file=sys.stderr)
    print(f"  val   ({n_val}): {args.val_out}", file=sys.stderr)
    print(f"  val fraction: {n_val / total:.1%}", file=sys.stderr)

    from collections import Counter
    train_counts = Counter(r["source"] for r in train)
    val_counts = Counter(r["source"] for r in val)
    print(f"\n  composition by source field (train / val):", file=sys.stderr)
    for src in sorted(set(list(train_counts) + list(val_counts))):
        print(f"    {src:>26s}: {train_counts.get(src, 0):>5d} / {val_counts.get(src, 0):>4d}", file=sys.stderr)

    # Refusal-share check — codex §5 target was 25-30%.
    refusal_total = (
        train_counts.get("refusal_distilled", 0) + val_counts.get("refusal_distilled", 0)
        + train_counts.get("refusal_v4", 0) + val_counts.get("refusal_v4", 0)
        # Anti-template chunks teach refusal of un-grounded sub-questions
        + train_counts.get("anti_template_distilled", 0) + val_counts.get("anti_template_distilled", 0)
    )
    pct = 100 * refusal_total / total if total else 0.0
    print(f"\n  refusal share (incl. anti-template): {refusal_total} / {total} = {pct:.1f}%", file=sys.stderr)
    print(f"  (codex v4 target: 25-30%)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
