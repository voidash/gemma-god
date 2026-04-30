#!/usr/bin/env python3
"""Format SFT v3 partial mix into trainer-ready messages JSONL.

v3 = v2 mix + 3 new slices (refusal expansion + terse + anti-template). The
grounded slice is intentionally NOT re-distilled here because v3-fix.md §1
flagged that it should wait for Track B's bilingual retrieval fix — re-
distilling now would bake in the same train/serve mismatch v2 had.

Slices in this v3 partial mix:

  v2 carryovers (kept as-is):
    grounded                — corpora/sft_v1_grounded.jsonl       (6553)
    native_ne_alpaca        — corpora/sft_v1_native_ne.jsonl      (1500)
    english_replay          — corpora/sft_v1_english_replay.jsonl (1500)
    translation             — corpora/sft_v2_translation.jsonl    (500)
    mc                      — corpora/sft_v2_mc.jsonl             (443)
    brief_qa                — corpora/sft_v2_brief_qa.jsonl       (300)

  v3 new slices:
    refusal                 — corpora/sft_v3_refusals.jsonl       (2500)
                              — replaces v2 refusal (was 1100). Bumped to
                              meet v3-fix §5: 25-30% refusal share to
                              overcome v2's "always answer" prior.
    terse                   — corpora/sft_v3_terse.jsonl          (~197)
                              — addresses v3-fix §7: anti-verbosity, fights
                              v2's chrF regression (22→13).
    anti_template           — corpora/sft_v3_anti_template.jsonl  (~270)
                              — addresses v3-fix §6: prompt has chunks for
                              topic A, question asks A+B, gold answer
                              covers A and refuses B with [unverified].

Total target: ~13,260 records.

Composition note: the v2 refusal slice (1100) is REPLACED, not added. The
v3 refusal slice (2500) is the canonical refusal data going forward.

Output schema unchanged from v2. Stratified 95/5 train/val.

Usage:
    python scripts/format_sft_v3.py
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
    """3-turn (system + user + assistant). For grounded + refusal +
    anti-template + grounded-terse slices — all share the cite-or-refuse
    contract."""
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
        "source": "english_replay",
        "lang": "english",
        "category": "other",
    }


def format_capability(rec: dict) -> dict | None:
    """For translation, mc, brief_qa, terse open-ended — 2-turn, no
    system, no chunks (or single chunk for grounded_terse)."""
    if rec.get("skip"):
        return None
    q = (rec.get("question") or "").strip()
    a = (rec.get("answer") or "").strip()
    if not q or not a:
        return None

    # terse grounded_terse subcategory has chunks — render them in user msg.
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
    "grounded":       ("corpora/sft_v1_grounded.jsonl",       format_grounded),
    "native_ne":      ("corpora/sft_v1_native_ne.jsonl",      format_native_ne),
    "english_replay": ("corpora/sft_v1_english_replay.jsonl", format_english),
    "refusal_v3":     ("corpora/sft_v3_refusals.jsonl",       format_grounded),
    "translation":    ("corpora/sft_v2_translation.jsonl",    format_capability),
    "mc":             ("corpora/sft_v2_mc.jsonl",             format_capability),
    "brief_qa":       ("corpora/sft_v2_brief_qa.jsonl",       format_capability),
    "terse":          ("corpora/sft_v3_terse.jsonl",          format_capability),
    "anti_template":  ("corpora/sft_v3_anti_template.jsonl",  format_grounded),
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
    ap.add_argument("--train-out", default="corpora/sft_v3_train.jsonl")
    ap.add_argument("--val-out", default="corpora/sft_v3_val.jsonl")
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

    print(f"\n=== format v3 summary ===", file=sys.stderr)
    print(f"  total formatted: {total}", file=sys.stderr)
    print(f"  train ({n_train}): {args.train_out}", file=sys.stderr)
    print(f"  val   ({n_val}): {args.val_out}", file=sys.stderr)
    print(f"  val fraction: {n_val / total:.1%}", file=sys.stderr)

    from collections import Counter
    train_counts = Counter(r["source"] for r in train)
    val_counts = Counter(r["source"] for r in val)
    print(f"\n  composition (train / val):", file=sys.stderr)
    for src in sorted(set(list(train_counts) + list(val_counts))):
        print(f"    {src:>26s}: {train_counts.get(src, 0):>5d} / {val_counts.get(src, 0):>4d}", file=sys.stderr)

    # Refusal share — the key v3 metric
    refusal_total = train_counts.get("refusal_distilled", 0) + val_counts.get("refusal_distilled", 0)
    print(f"\n  refusal share: {refusal_total} / {total} = {100 * refusal_total / total:.1f}%", file=sys.stderr)
    print(f"  (v2 was 11%, v3-fix §5 target 25-30%)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
