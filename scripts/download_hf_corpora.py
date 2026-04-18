#!/usr/bin/env python3
"""Download secondary CPT corpora from HuggingFace Hub.

Emits normalized JSONL into `corpora/`:
    - wikipedia_ne.jsonl        — Nepali Wikipedia articles
    - alpaca_nepali.jsonl       — Saugatkafley/alpaca-nepali-sft instructions
    - nepemo.jsonl              — NepEMO Reddit code-mixed (if available)
    - english_replay.jsonl      — HuggingFaceFW/fineweb-edu sample

Each record: {"source": "<corpus>", "text": "<content>", "tokens_est": int, ...metadata}

Requires HF_TOKEN for gated datasets (fineweb-edu isn't gated, Alpaca isn't,
Wikipedia isn't). Honors --skip-<name> flags to rerun only missing ones.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from datasets import load_dataset


def write_jsonl(path: Path, records) -> int:
    """Stream records to JSONL, return count written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1
    return n


def download_wikipedia_ne(out_path: Path) -> None:
    print("\n=== Wikipedia Nepali ===", flush=True)
    t0 = time.time()
    # Try several snapshot dates; HF keeps recent dumps.
    candidates = [
        ("wikimedia/wikipedia", "20231101.ne"),
        ("wikimedia/wikipedia", "20230601.ne"),
        ("graelo/wikipedia", "20230901.ne"),
    ]
    ds = None
    for repo, config in candidates:
        try:
            ds = load_dataset(repo, config, split="train", token=os.environ.get("HF_TOKEN"))
            print(f"  loaded {repo}:{config} ({len(ds)} articles)", flush=True)
            break
        except Exception as e:
            print(f"  {repo}:{config} failed: {str(e)[:100]}", flush=True)
    if ds is None:
        print("  WARNING: could not load any Wikipedia NE snapshot", flush=True)
        return

    def iter_records():
        for ex in ds:
            text = (ex.get("text") or "").strip()
            title = (ex.get("title") or "").strip()
            if len(text) < 100:
                continue  # skip tiny stubs
            yield {
                "source": "wikipedia_ne",
                "title": title,
                "text": text,
                "tokens_est": len(text) // 3,
                "url": ex.get("url"),
            }

    n = write_jsonl(out_path, iter_records())
    print(f"  kept {n:,} articles in {time.time()-t0:.0f}s -> {out_path}", flush=True)


def download_alpaca_nepali(out_path: Path) -> None:
    print("\n=== Alpaca Nepali (Saugatkafley/alpaca-nepali-sft) ===", flush=True)
    t0 = time.time()
    try:
        ds = load_dataset("Saugatkafley/alpaca-nepali-sft", split="train", token=os.environ.get("HF_TOKEN"))
    except Exception as e:
        print(f"  failed: {str(e)[:150]}", flush=True)
        return
    print(f"  loaded {len(ds)} instruction rows", flush=True)

    def iter_records():
        for ex in ds:
            # Alpaca format: instruction, input, output.
            instr = (ex.get("instruction") or "").strip()
            inp = (ex.get("input") or "").strip()
            outp = (ex.get("output") or "").strip()
            if not (instr or outp):
                continue
            # For CPT language modeling, concat into single text block.
            parts = [instr]
            if inp:
                parts.append(inp)
            if outp:
                parts.append(outp)
            text = "\n\n".join(parts).strip()
            if len(text) < 30:
                continue
            yield {
                "source": "alpaca_nepali",
                "text": text,
                "tokens_est": len(text) // 3,
                "instruction": instr,
                "input": inp,
                "output": outp,
            }

    n = write_jsonl(out_path, iter_records())
    print(f"  kept {n:,} records in {time.time()-t0:.0f}s -> {out_path}", flush=True)


def download_english_replay(out_path: Path, target_tokens: int) -> None:
    print(f"\n=== English replay (fineweb-edu, target ~{target_tokens/1e6:.0f}M tokens) ===", flush=True)
    t0 = time.time()
    try:
        # fineweb-edu-10BT is a smaller subsample, easier to stream.
        ds = load_dataset(
            "HuggingFaceFW/fineweb-edu",
            name="sample-10BT",
            split="train",
            streaming=True,
            token=os.environ.get("HF_TOKEN"),
        )
    except Exception as e:
        print(f"  fineweb-edu sample-10BT failed: {str(e)[:150]}; trying default", flush=True)
        try:
            ds = load_dataset(
                "HuggingFaceFW/fineweb-edu",
                split="train",
                streaming=True,
                token=os.environ.get("HF_TOKEN"),
            )
        except Exception as e2:
            print(f"  fineweb-edu default failed: {str(e2)[:150]}", flush=True)
            return

    def iter_records():
        tokens_so_far = 0
        n = 0
        for ex in ds:
            text = (ex.get("text") or "").strip()
            if len(text) < 200:
                continue
            tok = len(text) // 4  # rough English chars/token
            yield {
                "source": "english_replay",
                "text": text,
                "tokens_est": tok,
            }
            tokens_so_far += tok
            n += 1
            if tokens_so_far >= target_tokens:
                print(f"  reached {tokens_so_far:,} tokens after {n:,} records; stopping", flush=True)
                break

    n = write_jsonl(out_path, iter_records())
    print(f"  kept {n:,} records in {time.time()-t0:.0f}s -> {out_path}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="corpora")
    ap.add_argument("--english-tokens", type=int, default=16_000_000,
                    help="Target token budget for English replay slice")
    ap.add_argument("--skip-wiki", action="store_true")
    ap.add_argument("--skip-alpaca", action="store_true")
    ap.add_argument("--skip-english", action="store_true")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    token = os.environ.get("HF_TOKEN")
    if not token:
        print("warning: HF_TOKEN not set; gated datasets will fail", file=sys.stderr)

    if not args.skip_wiki:
        download_wikipedia_ne(out_dir / "wikipedia_ne.jsonl")
    if not args.skip_alpaca:
        download_alpaca_nepali(out_dir / "alpaca_nepali.jsonl")
    if not args.skip_english:
        download_english_replay(out_dir / "english_replay.jsonl", args.english_tokens)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
