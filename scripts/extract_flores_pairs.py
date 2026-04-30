#!/usr/bin/env python3
"""Extract NE↔EN translation pairs from FLORES-200 dev split for SFT v2's
capability-preservation slice.

Why we need this: SFT v1 dropped FLORES chrF by ~12 pts in both directions,
not because the model lost translation ability but because the v1 mix had
zero translation examples — so the model started paraphrasing in its
preferred grounded-helpdesk style instead of producing translations close
to the FLORES reference style. This slice teaches the model to do
translation specifically.

We pull from the FLORES-200 *dev* split (997 paired sentences). We never
touch the dev-test or test split — and the 30 items used in
`nepali_capability_eval.py` are sampled from dev with seed=42, so we
exclude those by index to avoid eval contamination.

Output schema matches `generate_sft_grounded.py`:
    {
      "id": "sft_translation_00001",
      "source": "translation_distilled",
      "question": "Translate the following English sentence into Nepali...",
      "question_lang": "english" | "devanagari",
      "category": "translation_en2ne" | "translation_ne2en",
      "chunks": [],
      "answer": "<reference translation>",
      "skip": false
    }

Usage:
    python scripts/extract_flores_pairs.py --n 500
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path


EN2NE_PROMPT = (
    "Translate the following English sentence into Nepali (Devanagari). "
    "Reply with only the translation.\n\n"
    "English: {src}\n\n"
    "Nepali:"
)

NE2EN_PROMPT = (
    "Translate the following Nepali sentence into English. "
    "Reply with only the translation.\n\n"
    "Nepali: {src}\n\n"
    "English:"
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=500, help="total pairs (split half/half between directions)")
    ap.add_argument("--output", default="corpora/sft_v2_translation.jsonl")
    ap.add_argument("--seed", type=int, default=42)
    # The eval set in nepali_capability_eval.py uses seed=42 on the dev split
    # to pick 30 items per direction. We exclude those so v2 training never
    # sees the eval samples.
    ap.add_argument("--eval-seed", type=int, default=42)
    ap.add_argument("--eval-n", type=int, default=30)
    args = ap.parse_args()

    from huggingface_hub import hf_hub_download

    token = os.environ.get("HF_TOKEN")
    if not token:
        fmw = Path.home() / ".fmw"
        if fmw.exists():
            for line in fmw.read_text().splitlines():
                if line.startswith("HF_TOKEN="):
                    token = line.split("=", 1)[1].strip()
                    break

    print("loading FLORES-200 dev split...", file=sys.stderr)
    eng_path = hf_hub_download(
        "openlanguagedata/flores_plus", "dev/eng_Latn.jsonl",
        repo_type="dataset", token=token,
    )
    nep_path = hf_hub_download(
        "openlanguagedata/flores_plus", "dev/npi_Deva.jsonl",
        repo_type="dataset", token=token,
    )
    eng = [json.loads(l)["text"] for l in open(eng_path, encoding="utf-8")]
    nep = [json.loads(l)["text"] for l in open(nep_path, encoding="utf-8")]
    n_aligned = min(len(eng), len(nep))
    print(f"  {n_aligned} aligned pairs", file=sys.stderr)

    # Reproduce nepali_capability_eval.py's sample so we can exclude.
    eval_rng = random.Random(args.eval_seed)
    eval_idx = set(eval_rng.sample(range(n_aligned), min(args.eval_n, n_aligned)))
    print(f"  excluding {len(eval_idx)} indices used in eval", file=sys.stderr)

    available = [i for i in range(n_aligned) if i not in eval_idx]
    rng = random.Random(args.seed)
    rng.shuffle(available)

    n_per_dir = args.n // 2
    if 2 * n_per_dir > len(available):
        print(f"warning: requested {args.n} but only {2*len(available)} available", file=sys.stderr)
        n_per_dir = len(available) // 2

    en2ne_idx = available[:n_per_dir]
    ne2en_idx = available[n_per_dir : 2 * n_per_dir]

    out: list[dict] = []
    for i, idx in enumerate(en2ne_idx, 1):
        out.append({
            "id": f"sft_translation_en2ne_{i:05d}",
            "source": "translation_distilled",
            "question": EN2NE_PROMPT.format(src=eng[idx]),
            "question_lang": "english",
            "category": "translation_en2ne",
            "chunks": [],
            "answer": nep[idx],
            "skip": False,
            "skip_reason": None,
            "gold_chunk_id": None,
        })
    for i, idx in enumerate(ne2en_idx, 1):
        out.append({
            "id": f"sft_translation_ne2en_{i:05d}",
            "source": "translation_distilled",
            "question": NE2EN_PROMPT.format(src=nep[idx]),
            "question_lang": "devanagari",
            "category": "translation_ne2en",
            "chunks": [],
            "answer": eng[idx],
            "skip": False,
            "skip_reason": None,
            "gold_chunk_id": None,
        })

    rng.shuffle(out)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n=== flores extraction summary ===", file=sys.stderr)
    print(f"  total: {len(out)} pairs", file=sys.stderr)
    print(f"  en2ne: {len(en2ne_idx)}", file=sys.stderr)
    print(f"  ne2en: {len(ne2en_idx)}", file=sys.stderr)
    print(f"  excluded (eval): {len(eval_idx)}", file=sys.stderr)
    print(f"  output: {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
