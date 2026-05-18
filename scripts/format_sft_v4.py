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
from collections import Counter
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
REFUSAL_MARKERS = (
    "मलाई यो प्रश्नको आधिकारिक स्रोत",
    "Yo prashnako adhikarik",
    "I cannot find an authoritative source",
)

# Target counts per v4-minimal+ plan (codex-vetted scale-down from full
# rebuild). The grounded slice is filtered v3 carry — we sample down to
# ~5500 if larger; refusal stays as v3 carry (2500) since codex agreed
# the boundary fix is server-side BM25 gate territory.
TARGET_COUNTS: dict[str, int] = {
    "grounded": 5500,
    "refusal_v4": 2500,         # v3 carry, not the 3600 full-rebuild target
    "anti_template": 600,
    "grounded_terse": 350,
    "brief_qa": 700,
    "english_replay": 3000,     # combined across math/instr/MC/reasoning buckets
    "native_ne": 1200,
    "translation": 500,
    "mc": 550,
}


def assistant_text(rec: dict) -> str:
    for msg in reversed(rec.get("messages") or []):
        if msg.get("role") == "assistant":
            return msg.get("content") or ""
    return ""


def has_refusal_marker(rec: dict) -> bool:
    text = assistant_text(rec)
    return any(m in text for m in REFUSAL_MARKERS)


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
        # NOTE: hardcode "english_replay" rather than passing through
        # rec.get("source"). train_sft_v1.py's spike-gate at line 729 hard-
        # codes the literal string `english_replay` for the catastrophic-
        # forgetting check; if we emit "v4_english_replay" the gate never
        # fires (codex caught this in the v4 launch review).
        "source": "english_replay",
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


# v4-minimal+ data sources. The v4 plan was originally full retrieval-
# realistic rebuild, but codex agreed with the user's pushback:
#   - filter v3 grounded for clean chunks via DB language labels (NO rebuild)
#   - keep v3 refusals as-is (the 90% target is end-to-end, not SFT-only;
#     server-side BM25 relevance gate is the right fix per codex)
#   - REBUILD anti-template only — v3's 270 had FAKE invented URLs
#   - clean English replay via multi-seed TULU pulls (free)
#
# scripts/distill_grounded_v4.py + synthesize_refusal_v4.py are still in
# the tree as opt-in escalation paths if v4-minimal+ eval shows we actually
# need them — see SFT_V3A_RESULTS.md "Suggested next steps" for the
# decision criterion.
SLICE_FORMATTERS: dict[str, tuple[str, callable]] = {
    # Grounded — filtered v3 carry (joined against current SQLite chunks.language;
    # 624/9166 records dropped because their chunks no longer exist post-rebuild)
    "grounded":              ("corpora/sft_v4_grounded_v3carry.jsonl",      format_grounded),
    # Refusal — v3 carry (2500 items). Phrase-teaching, not boundary-teaching;
    # codex says the boundary belongs to the server-side BM25 gate.
    "refusal_v4":            ("corpora/sft_v3_refusals.jsonl",              format_grounded),
    # Anti-template — REBUILT with REAL chunks (v3's 270 had fake URLs;
    # synthesize_anti_template_v4.py produces 600 items via real retrieval).
    "anti_template":         ("corpora/sft_v4_anti_template.jsonl",         format_grounded),
    # Grounded-terse — pruned from v3 (58 items, dropped 139 open-ended).
    "grounded_terse":        ("corpora/sft_v4_grounded_terse.jsonl",        format_grounded),
    # Capability + replay carryovers / new pulls
    "brief_qa":              ("corpora/sft_v4_brief_qa.jsonl",              format_capability),
    # English replay: combined from 4 multi-seed TULU pulls (each lands on
    # a different shard cluster — math / instruction / MC / reasoning).
    # See scripts/assemble_v4_english_replay.py which concatenates +
    # samples down from 4 × 1500 to 3000.
    "english_replay":        ("corpora/sft_v4_english_replay.jsonl",        format_english),
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


def cap_to_targets(
    records_by_slice: dict[str, list[dict]],
    targets: dict[str, int],
    rng: random.Random,
) -> None:
    """Deterministically sample down oversize slices.

    v4-minimal accidentally trained on 6297 grounded records even though the
    target was 5500 because the composer only warned. For v4b, use
    --cap-to-targets so composition changes are explicit and reproducible.
    """
    for slice_name, target in targets.items():
        records = records_by_slice.get(slice_name)
        if not records or target <= 0 or len(records) <= target:
            continue
        rng.shuffle(records)
        del records[target:]
        logging.info("capped slice %s to target=%d", slice_name, target)


def cap_refusal_fraction(
    records: list[dict],
    max_frac: float,
    rng: random.Random,
) -> tuple[int, int, int]:
    """Cap refusal-marker records within a mixed slice.

    Retrieval-realistic grounded distillation can validly produce refusals when
    prod retrieval misses the seed fact. v4 already over-refused, so v4b may
    need to keep those boundary examples without letting them dominate the new
    grounded slice.

    Returns (kept_total, kept_refusals, dropped_refusals).
    """
    if max_frac < 0 or max_frac >= 1:
        return len(records), sum(1 for r in records if has_refusal_marker(r)), 0
    refused = [r for r in records if has_refusal_marker(r)]
    answered = [r for r in records if not has_refusal_marker(r)]
    if not records or not refused:
        return len(records), 0, 0
    max_refused = int((max_frac * len(answered)) / max(1e-9, 1.0 - max_frac))
    max_refused = max(0, min(max_refused, len(refused)))
    if len(refused) <= max_refused:
        return len(records), len(refused), 0
    rng.shuffle(refused)
    kept = answered + refused[:max_refused]
    rng.shuffle(kept)
    dropped = len(refused) - max_refused
    records[:] = kept
    return len(records), max_refused, dropped


def fill_slice_from_fallback(
    records: list[dict],
    fallback_path: Path,
    formatter,
    target: int,
    rng: random.Random,
) -> tuple[int, int]:
    """Fill a slice up to target from a fallback JSONL, deduping by prompt text."""
    need = target - len(records)
    if need <= 0:
        return 0, 0
    existing_prompts = {
        "\n".join(m.get("content", "") for m in r.get("messages") or [] if m.get("role") == "user")
        for r in records
    }
    pool: list[dict] = []
    for rec in load_and_format("grounded_fallback", formatter, fallback_path):
        prompt = "\n".join(
            m.get("content", "") for m in rec.get("messages") or [] if m.get("role") == "user"
        )
        if prompt in existing_prompts:
            continue
        pool.append(rec)
    rng.shuffle(pool)
    take = min(need, len(pool))
    records.extend(pool[:take])
    return take, max(0, need - take)


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
        "--grounded-path",
        default="corpora/sft_v4_grounded_v3carry.jsonl",
        help="grounded slice path. For v4b use corpora/sft_v4_grounded.jsonl.",
    )
    ap.add_argument(
        "--grounded-fallback-path",
        default="",
        help="optional fallback grounded JSONL used to fill the grounded target "
        "after refusal-capping a partial retrieval-realistic slice.",
    )
    ap.add_argument(
        "--brief-qa-path",
        default="corpora/sft_v4_brief_qa.jsonl",
        help="base no-chunk brief QA slice.",
    )
    ap.add_argument(
        "--roman-ne-open-qa-path",
        default="",
        help="optional v4b Roman-Nepali no-chunk service QA top-up.",
    )
    ap.add_argument(
        "--roman-ne-open-qa-target",
        type=int,
        default=400,
        help="target count for --roman-ne-open-qa-path when --cap-to-targets is set.",
    )
    ap.add_argument(
        "--english-replay-path",
        default="corpora/sft_v4_english_replay.jsonl",
        help="English replay path; lets v4b swap in a less math-only replay file.",
    )
    ap.add_argument(
        "--cap-to-targets",
        action="store_true",
        help="deterministically sample down any slice above TARGET_COUNTS. "
        "Under-target slices are kept and reported.",
    )
    ap.add_argument(
        "--grounded-max-refusal-frac",
        type=float,
        default=-1.0,
        help="optional cap for refusal-marker records inside the grounded slice, "
        "e.g. 0.15. Default -1 leaves the grounded slice unchanged.",
    )
    ap.add_argument(
        "--allow-missing", action="store_true",
        help="if set, treat missing slice files as empty (warn) instead of bailing. "
        "Default: bail if any slice file is missing — safer for production runs.",
    )
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    slice_formatters = dict(SLICE_FORMATTERS)
    slice_formatters["grounded"] = (args.grounded_path, format_grounded)
    slice_formatters["brief_qa"] = (args.brief_qa_path, format_capability)
    slice_formatters["english_replay"] = (args.english_replay_path, format_english)

    target_counts = dict(TARGET_COUNTS)
    if args.roman_ne_open_qa_path:
        slice_formatters["roman_ne_open_qa"] = (
            args.roman_ne_open_qa_path,
            format_capability,
        )
        target_counts["roman_ne_open_qa"] = args.roman_ne_open_qa_target

    # Pre-flight: check all slice files exist (unless --allow-missing).
    missing = [name for name, (path, _) in slice_formatters.items()
               if not Path(path).exists()]
    if args.grounded_fallback_path and not Path(args.grounded_fallback_path).exists():
        missing.append("grounded_fallback")
    if missing and not args.allow_missing:
        print(f"\nERROR: missing slice files for v4:", file=sys.stderr)
        for name in missing:
            if name == "grounded_fallback":
                print(f"  - {name}: {args.grounded_fallback_path}", file=sys.stderr)
            else:
                print(f"  - {name}: {slice_formatters[name][0]}", file=sys.stderr)
        print("\nRe-run with --allow-missing to compose a partial mix, or "
              "build the missing slices first.", file=sys.stderr)
        return 1

    records_by_slice: dict[str, list[dict]] = {}
    for slice_name, (path_str, fmt) in slice_formatters.items():
        records_by_slice[slice_name] = load_and_format(
            slice_name, fmt, Path(path_str)
        )

    rng = random.Random(args.seed)
    if args.grounded_max_refusal_frac >= 0:
        kept_total, kept_ref, dropped_ref = cap_refusal_fraction(
            records_by_slice.get("grounded", []),
            args.grounded_max_refusal_frac,
            rng,
        )
        logging.info(
            "grounded refusal cap %.1f%%: kept_total=%d kept_refusals=%d dropped_refusals=%d",
            100 * args.grounded_max_refusal_frac,
            kept_total,
            kept_ref,
            dropped_ref,
        )
    if args.grounded_fallback_path:
        added, short = fill_slice_from_fallback(
            records_by_slice.get("grounded", []),
            Path(args.grounded_fallback_path),
            format_grounded,
            target_counts["grounded"],
            rng,
        )
        logging.info(
            "grounded fallback fill: added=%d shortfall_after_fill=%d from %s",
            added,
            short,
            args.grounded_fallback_path,
        )
    if args.cap_to_targets:
        cap_to_targets(records_by_slice, target_counts, rng)

    total = sum(len(v) for v in records_by_slice.values())
    logging.info("total formatted: %d (target 16000)", total)
    if total == 0:
        print("no records to format", file=sys.stderr)
        return 1

    # Composition warnings: flag any slice that's significantly off-target.
    print("\n  composition vs target:", file=sys.stderr)
    for slice_name, target in target_counts.items():
        actual = len(records_by_slice.get(slice_name, []))
        delta = actual - target
        flag = "  " if abs(delta) <= max(50, target // 10) else "!!"
        print(f"  {flag} {slice_name:<26s} actual={actual:>5d} target={target:>5d} delta={delta:+d}", file=sys.stderr)

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

    train_counts = Counter(r["source"] for r in train)
    val_counts = Counter(r["source"] for r in val)
    print(f"\n  composition by source field (train / val):", file=sys.stderr)
    for src in sorted(set(list(train_counts) + list(val_counts))):
        print(f"    {src:>26s}: {train_counts.get(src, 0):>5d} / {val_counts.get(src, 0):>4d}", file=sys.stderr)

    # Refusal-share check — source names changed across v3/v4, so report both
    # source-bucket share and actual assistant-text marker share.
    refusal_sources = {
        "refusal_distilled",
        "refusal_v4",
        "v4_refusal_retrieval",
        "anti_template_distilled",
        "v4_anti_template",
    }
    source_refusal_total = sum(train_counts.get(s, 0) + val_counts.get(s, 0) for s in refusal_sources)
    marker_refusal_total = sum(1 for r in train + val if has_refusal_marker(r))
    source_pct = 100 * source_refusal_total / total if total else 0.0
    marker_pct = 100 * marker_refusal_total / total if total else 0.0
    print(
        f"\n  refusal share by source buckets: {source_refusal_total} / {total} = {source_pct:.1f}%",
        file=sys.stderr,
    )
    print(
        f"  refusal share by answer markers: {marker_refusal_total} / {total} = {marker_pct:.1f}%",
        file=sys.stderr,
    )
    print(f"  (codex v4 source-bucket target was 25-30%)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
