#!/usr/bin/env python3
"""Transliterate Devanagari Nepali to Romanized Nepali via IndicXlit.

Adds a synthetic Roman-NE slice to the CPT corpus — complements the natural
Reddit Roman-NE with deterministic transliterations of gov / Wikipedia text.

Per arxiv 2604.14171 methodology, permit orthographic variation (don't force
a single canonical Romanization) to match real-user typing distribution.
IndicXlit's default behavior already produces probabilistic variants via
beam search.

Prereq:
    uv pip install ai4bharat-transliteration

Inputs (Devanagari-dominant sources):
    corpora/gov_nepali.jsonl     (subset of tier=A / Mixed records)
    corpora/wikipedia_ne.jsonl   (sample)

Output:
    corpora/transliterated_roman_ne.jsonl

Each record carries a `source` field distinguishing the Devanagari origin.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def iter_devanagari_chunks(in_path: Path, max_chunks: int, min_chars: int = 50):
    """Yield Devanagari-dominant text records from a JSONL file."""
    n = 0
    with in_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            text = rec.get("text", "").strip()
            if len(text) < min_chars:
                continue
            # Count Devanagari ratio to skip English-heavy records
            deva = sum(1 for c in text if "\u0900" <= c <= "\u097F")
            latin = sum(1 for c in text if c.isalpha() and ord(c) < 128)
            total = deva + latin
            if total < 10 or (deva / total) < 0.3:
                continue
            yield rec, text
            n += 1
            if max_chunks and n >= max_chunks:
                break


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gov-in", default="corpora/gov_nepali.jsonl")
    ap.add_argument("--wiki-in", default="corpora/wikipedia_ne.jsonl")
    ap.add_argument("--out", default="corpora/transliterated_roman_ne.jsonl")
    ap.add_argument("--max-gov", type=int, default=3000)
    ap.add_argument("--max-wiki", type=int, default=3000)
    args = ap.parse_args()

    try:
        from ai4bharat.transliteration import XlitEngine
    except ImportError:
        print(
            "error: ai4bharat-transliteration not installed.\n"
            "  run: uv pip install ai4bharat-transliteration",
            file=sys.stderr,
        )
        return 2

    # `ne` is the Nepali language code in IndicXlit.
    print("loading IndicXlit engine (Nepali)...", file=sys.stderr, flush=True)
    engine = XlitEngine("ne", beam_width=3, src_script_type="indic")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    inputs = []
    if Path(args.gov_in).is_file():
        inputs.append(("gov_nepali", Path(args.gov_in), args.max_gov))
    if Path(args.wiki_in).is_file():
        inputs.append(("wikipedia_ne", Path(args.wiki_in), args.max_wiki))
    if not inputs:
        print("error: no input corpora found", file=sys.stderr)
        return 2

    t0 = time.time()
    n_out = 0
    total_chars = 0
    with out_path.open("w", encoding="utf-8") as out_f:
        for src_name, in_path, max_chunks in inputs:
            print(f"\n=== {src_name} (max {max_chunks}) ===", file=sys.stderr, flush=True)
            src_t0 = time.time()
            src_n = 0
            for rec, text in iter_devanagari_chunks(in_path, max_chunks):
                # IndicXlit operates at word/sentence level. For long text,
                # split by sentences and transliterate each.
                # Cheap sentence split on Devanagari danda + newline + period.
                import re
                sentences = [s.strip() for s in re.split(r"[।\n]+|\. ", text) if s.strip()]
                roman_sentences = []
                for s in sentences[:50]:  # cap per chunk to avoid runaway
                    try:
                        result = engine.translit_sentence(s)
                        # XlitEngine returns {'ne': 'romanized'} or similar dict
                        if isinstance(result, dict):
                            roman = result.get("ne") or next(iter(result.values()), "")
                        else:
                            roman = str(result)
                        if roman:
                            roman_sentences.append(roman)
                    except Exception:
                        continue
                if not roman_sentences:
                    continue
                roman_text = ". ".join(roman_sentences)
                record = {
                    "source": "indicxlit_roman",
                    "origin": src_name,
                    "origin_doc_id": rec.get("doc_id") or rec.get("title") or "",
                    "text": roman_text,
                    "tokens_est": len(roman_text) // 4,
                }
                out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                n_out += 1
                src_n += 1
                total_chars += len(roman_text)
                if src_n % 200 == 0:
                    elapsed = time.time() - src_t0
                    print(
                        f"  [{src_n}/{max_chunks}] {src_n/elapsed:.1f} chunks/sec",
                        file=sys.stderr,
                        flush=True,
                    )
            print(f"  {src_name}: {src_n} chunks in {time.time()-src_t0:.0f}s", file=sys.stderr)

    print(f"\ntotal: {n_out:,} records, {total_chars:,} chars ({total_chars/1024/1024:.1f} MB)", file=sys.stderr)
    print(f"token estimate: {total_chars//4:,}", file=sys.stderr)
    print(f"elapsed: {time.time()-t0:.0f}s", file=sys.stderr)
    print(f"output: {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
