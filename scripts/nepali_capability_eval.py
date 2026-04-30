#!/usr/bin/env python3
"""Standard Nepali capability benchmarks against an HF model (with or without
PEFT adapter).

Five benchmarks, comparable to the published Gemma 4 E2B/E4B baseline table:
  1. Belebele (npi_Deva)            — Bandarkar 2023 — accuracy
  2. INCLUDE-base-44 (Nepali)       — Romanou 2024  — accuracy
  3. FLORES-200 NE→EN               — NLLB 2022     — chrF
  4. FLORES-200 EN→NE               — NLLB 2022     — chrF
  5. XLSum Nepali                   — Hasan 2021    — ROUGE-L

Plus per-benchmark wallclock and a final aggregated wallclock.

Reuses `HFTransformersBackend` from `eval_sft_v1.py` so adapter loading +
Gemma 4 unwrap logic stays consistent with the gov-helpdesk eval.

Usage:
  # SFT v1 adapter
  python scripts/nepali_capability_eval.py \
      --base google/gemma-4-E4B-it \
      --adapter /home/ubuntu/checkpoints/sft_v1_seed42/best \
      --label sft_v1_seed42 \
      --out eval/reports/nepali_capability/sft_v1_seed42.json

  # Base model (no adapter)
  python scripts/nepali_capability_eval.py \
      --base google/gemma-4-E4B-it --no-adapter \
      --label e4b_base \
      --out eval/reports/nepali_capability/e4b_base.json
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import sys
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path

# Reuse HFTransformersBackend from eval_sft_v1
sys.path.insert(0, str(Path(__file__).parent))
from eval_sft_v1 import HFTransformersBackend  # noqa: E402


# ---- Belebele -------------------------------------------------------------


BELEBELE_PROMPT = (
    "Read the passage in Nepali and answer the question by choosing the "
    "single best option (A, B, C, or D). Reply with only the letter.\n\n"
    "Passage: {passage}\n\n"
    "Question: {question}\n\n"
    "A) {a}\nB) {b}\nC) {c}\nD) {d}\n\nAnswer:"
)


def run_belebele(backend, n: int = 60, seed: int = 42) -> dict:
    from datasets import load_dataset

    rng = random.Random(seed)
    t0 = time.time()
    logging.info("[belebele] loading npi_Deva test split…")
    ds = load_dataset(
        "facebook/belebele", "npi_Deva", split="test", token=os.environ.get("HF_TOKEN")
    )
    idxs = rng.sample(range(len(ds)), min(n, len(ds)))
    correct = 0
    items: list[dict] = []
    for i, idx in enumerate(idxs, 1):
        ex = ds[idx]
        prompt = BELEBELE_PROMPT.format(
            passage=ex["flores_passage"],
            question=ex["question"],
            a=ex["mc_answer1"],
            b=ex["mc_answer2"],
            c=ex["mc_answer3"],
            d=ex["mc_answer4"],
        )
        try:
            resp = backend.chat("", prompt, max_tokens=20)
        except Exception as e:
            items.append({"idx": idx, "error": f"{type(e).__name__}: {str(e)[:120]}"})
            continue
        m = re.search(r"\b([ABCD])\b", resp)
        gold = {"1": "A", "2": "B", "3": "C", "4": "D"}.get(str(ex["correct_answer_num"]))
        ok = bool(m and m.group(1) == gold)
        if ok:
            correct += 1
        items.append({"idx": idx, "gold": gold, "model": resp[:80], "ok": ok})
        if i % 10 == 0 or i == len(idxs):
            logging.info("[belebele] %d/%d acc=%.2f", i, len(idxs), correct / i)
    elapsed = time.time() - t0
    return {
        "n": len(idxs),
        "correct": correct,
        "accuracy": round(correct / max(1, len(idxs)), 4),
        "elapsed_sec": round(elapsed, 1),
        "items": items,
    }


# ---- INCLUDE-base-44 Nepali -----------------------------------------------


INCLUDE_PROMPT = (
    "Read the question in Nepali and answer by choosing the single best "
    "option (A, B, C, or D). Reply with only the letter.\n\n"
    "Question: {question}\n\n"
    "A) {a}\nB) {b}\nC) {c}\nD) {d}\n\nAnswer:"
)


def run_include(backend, n: int = 60, seed: int = 42) -> dict:
    from datasets import load_dataset

    rng = random.Random(seed)
    t0 = time.time()
    logging.info("[include] loading CohereLabs/include-base-44 Nepali test…")
    ds = load_dataset(
        "CohereLabs/include-base-44", "Nepali", split="test", token=os.environ.get("HF_TOKEN")
    )
    idxs = rng.sample(range(len(ds)), min(n, len(ds)))
    correct = 0
    items: list[dict] = []
    # answer field is integer 0..3 → A..D
    idx_to_letter = {0: "A", 1: "B", 2: "C", 3: "D"}
    for i, idx in enumerate(idxs, 1):
        ex = ds[idx]
        prompt = INCLUDE_PROMPT.format(
            question=ex["question"],
            a=ex["option_a"],
            b=ex["option_b"],
            c=ex["option_c"],
            d=ex["option_d"],
        )
        try:
            resp = backend.chat("", prompt, max_tokens=20)
        except Exception as e:
            items.append({"idx": idx, "error": f"{type(e).__name__}: {str(e)[:120]}"})
            continue
        m = re.search(r"\b([ABCD])\b", resp)
        gold = idx_to_letter.get(int(ex["answer"]))
        ok = bool(m and m.group(1) == gold)
        if ok:
            correct += 1
        items.append({"idx": idx, "gold": gold, "model": resp[:80], "ok": ok})
        if i % 10 == 0 or i == len(idxs):
            logging.info("[include] %d/%d acc=%.2f", i, len(idxs), correct / i)
    elapsed = time.time() - t0
    return {
        "n": len(idxs),
        "correct": correct,
        "accuracy": round(correct / max(1, len(idxs)), 4),
        "elapsed_sec": round(elapsed, 1),
        "items": items,
    }


# ---- FLORES-200 NE↔EN -----------------------------------------------------


def _load_flores() -> tuple[list[str], list[str]]:
    """Load aligned FLORES-200 (eng_Latn, npi_Deva) dev pairs.

    Uses openlanguagedata/flores_plus directly (the legacy facebook/flores
    repo's paired config is brittle). Each language has its own jsonl file
    aligned by row id."""
    from huggingface_hub import hf_hub_download

    token = os.environ.get("HF_TOKEN")
    eng_path = hf_hub_download(
        "openlanguagedata/flores_plus",
        "dev/eng_Latn.jsonl",
        repo_type="dataset",
        token=token,
    )
    nep_path = hf_hub_download(
        "openlanguagedata/flores_plus",
        "dev/npi_Deva.jsonl",
        repo_type="dataset",
        token=token,
    )
    eng = [json.loads(l)["text"] for l in open(eng_path, encoding="utf-8")]
    nep = [json.loads(l)["text"] for l in open(nep_path, encoding="utf-8")]
    n = min(len(eng), len(nep))
    return eng[:n], nep[:n]


def run_flores(backend, direction: str, n: int = 30, seed: int = 42) -> dict:
    """direction: 'en2ne' or 'ne2en'. Returns chrF."""
    import sacrebleu

    rng = random.Random(seed)
    t0 = time.time()
    logging.info("[flores-%s] loading FLORES-200…", direction)
    eng, nep = _load_flores()
    sample_idx = rng.sample(range(len(eng)), min(n, len(eng)))
    hyps: list[str] = []
    refs: list[str] = []
    items: list[dict] = []
    for i, idx in enumerate(sample_idx, 1):
        if direction == "en2ne":
            src, ref = eng[idx], nep[idx]
            prompt = (
                "Translate the following English sentence into Nepali (Devanagari). "
                "Reply with only the translation.\n\n"
                f"English: {src}\n\nNepali:"
            )
        else:
            src, ref = nep[idx], eng[idx]
            prompt = (
                "Translate the following Nepali sentence into English. "
                "Reply with only the translation.\n\n"
                f"Nepali: {src}\n\nEnglish:"
            )
        try:
            h = backend.chat("", prompt, max_tokens=200).strip()
        except Exception as e:
            items.append({"idx": idx, "error": f"{type(e).__name__}: {str(e)[:120]}"})
            hyps.append("")
            refs.append(ref)
            continue
        # Strip common prefixes the model adds
        for prefix in ("Nepali:", "English:", "Translation:"):
            if h.startswith(prefix):
                h = h[len(prefix):].strip()
        hyps.append(h)
        refs.append(ref)
        items.append({"idx": idx, "src": src[:120], "hyp": h[:120], "ref": ref[:120]})
        if i % 10 == 0 or i == len(sample_idx):
            logging.info("[flores-%s] %d/%d", direction, i, len(sample_idx))
    chrf_score = sacrebleu.corpus_chrf(hyps, [refs], word_order=2).score
    elapsed = time.time() - t0
    return {
        "n": len(sample_idx),
        "direction": direction,
        "chrf": round(chrf_score, 2),
        "elapsed_sec": round(elapsed, 1),
        "items": items,
    }


# ---- XLSum Nepali ROUGE-L --------------------------------------------------


XLSUM_PROMPT = (
    "Below is a Nepali news article. Write a one-or-two sentence summary "
    "in Nepali. Reply with only the summary.\n\n"
    "Article:\n{text}\n\nSummary:"
)


def _load_xlsum_nepali_test(cache_dir: Path | None = None) -> list[dict]:
    """Direct download of nepali_XLSum_v2.0.tar.bz2 from csebuetnlp/xlsum.

    The HF datasets library can't load this dataset anymore (script-based,
    no longer supported), so we fetch the archive ourselves."""
    cache = cache_dir or Path(tempfile.gettempdir()) / "xlsum_nepali"
    cache.mkdir(parents=True, exist_ok=True)
    archive = cache / "nepali_XLSum_v2.0.tar.bz2"
    if not archive.exists():
        url = "https://huggingface.co/datasets/csebuetnlp/xlsum/resolve/main/data/nepali_XLSum_v2.0.tar.bz2"
        token = os.environ.get("HF_TOKEN")
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req) as r, archive.open("wb") as f:
            f.write(r.read())
    test_jsonl = cache / "nepali_test.jsonl"
    if not test_jsonl.exists():
        with tarfile.open(archive, "r:bz2") as tf:
            tf.extractall(cache)
    out: list[dict] = []
    with test_jsonl.open(encoding="utf-8") as f:
        for line in f:
            out.append(json.loads(line))
    return out


def _rouge_l(hyp: str, ref: str) -> float:
    """ROUGE-L F1 using the LCS-based formulation. Tokenization is
    whitespace + Devanagari punctuation strip. Returns F1 in [0, 1]."""
    def tokenize(s: str) -> list[str]:
        s = re.sub(r"[।.!?,\"'\(\)\[\]:;]+", " ", s)
        return [t for t in s.split() if t]

    h = tokenize(hyp)
    r = tokenize(ref)
    if not h or not r:
        return 0.0
    # LCS via DP
    m, n = len(h), len(r)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m):
        for j in range(n):
            dp[i + 1][j + 1] = (dp[i][j] + 1) if h[i] == r[j] else max(dp[i + 1][j], dp[i][j + 1])
    lcs = dp[m][n]
    if lcs == 0:
        return 0.0
    precision = lcs / m
    recall = lcs / n
    return 2 * precision * recall / (precision + recall)


def run_xlsum(backend, n: int = 15, seed: int = 42) -> dict:
    rng = random.Random(seed)
    t0 = time.time()
    logging.info("[xlsum] loading nepali test split (direct fetch)…")
    records = _load_xlsum_nepali_test()
    idxs = rng.sample(range(len(records)), min(n, len(records)))
    rouge_l_scores: list[float] = []
    items: list[dict] = []
    for i, idx in enumerate(idxs, 1):
        ex = records[idx]
        # Truncate very long articles to keep prompt under 4k tokens
        text = ex["text"][:4000]
        prompt = XLSUM_PROMPT.format(text=text)
        try:
            hyp = backend.chat("", prompt, max_tokens=300).strip()
        except Exception as e:
            items.append({"idx": idx, "error": f"{type(e).__name__}: {str(e)[:120]}"})
            rouge_l_scores.append(0.0)
            continue
        # Strip common preamble
        for prefix in ("Summary:", "सारांश:"):
            if hyp.startswith(prefix):
                hyp = hyp[len(prefix):].strip()
        score = _rouge_l(hyp, ex["summary"])
        rouge_l_scores.append(score)
        items.append({
            "idx": idx,
            "id": ex.get("id"),
            "ref": ex["summary"][:200],
            "hyp": hyp[:200],
            "rouge_l": round(score, 4),
        })
        if i % 5 == 0 or i == len(idxs):
            mean_so_far = sum(rouge_l_scores) / len(rouge_l_scores)
            logging.info("[xlsum] %d/%d rouge_l_mean=%.3f", i, len(idxs), mean_so_far)
    elapsed = time.time() - t0
    rouge_l_mean = sum(rouge_l_scores) / max(1, len(rouge_l_scores))
    # XLSum convention reports ROUGE-L as percentage
    return {
        "n": len(idxs),
        "rouge_l": round(rouge_l_mean * 100, 2),
        "elapsed_sec": round(elapsed, 1),
        "items": items,
    }


# ---- Main --------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="google/gemma-4-E4B-it")
    ap.add_argument("--adapter", default=None, help="PEFT adapter dir")
    ap.add_argument("--no-adapter", action="store_true", help="run base model only")
    ap.add_argument("--label", required=True, help="run label, used in output JSON")
    ap.add_argument("--out", required=True, help="output JSON path")
    ap.add_argument("--belebele-n", type=int, default=60)
    ap.add_argument("--include-n", type=int, default=60)
    ap.add_argument("--flores-n", type=int, default=30)
    ap.add_argument("--xlsum-n", type=int, default=15)
    ap.add_argument(
        "--skip", default="",
        help="comma-separated benchmarks to skip: belebele,include,flores_ne2en,flores_en2ne,xlsum"
    )
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--torch-dtype", default="bfloat16")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )

    skip = {s.strip() for s in args.skip.split(",") if s.strip()}

    if args.no_adapter:
        args.adapter = None

    backend = HFTransformersBackend(
        base_model_id=args.base,
        adapter_path=args.adapter,
        device=args.device,
        torch_dtype=args.torch_dtype,
    )

    t_total = time.time()
    results: dict = {
        "label": args.label,
        "base_model": args.base,
        "adapter": args.adapter,
    }

    if "belebele" not in skip:
        results["belebele"] = run_belebele(backend, n=args.belebele_n, seed=args.seed)
    if "include" not in skip:
        results["include"] = run_include(backend, n=args.include_n, seed=args.seed)
    if "flores_ne2en" not in skip:
        results["flores_ne2en"] = run_flores(backend, "ne2en", n=args.flores_n, seed=args.seed)
    if "flores_en2ne" not in skip:
        results["flores_en2ne"] = run_flores(backend, "en2ne", n=args.flores_n, seed=args.seed)
    if "xlsum" not in skip:
        results["xlsum"] = run_xlsum(backend, n=args.xlsum_n, seed=args.seed)

    results["wallclock_sec"] = round(time.time() - t_total, 1)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n=== nepali capability eval: {args.label} ===")
    if "belebele" in results:
        print(f"  Belebele (npi_Deva, n={results['belebele']['n']}): {results['belebele']['accuracy']*100:.1f}%  ({results['belebele']['elapsed_sec']:.1f}s)")
    if "include" in results:
        print(f"  INCLUDE-base-44 (Nepali, n={results['include']['n']}): {results['include']['accuracy']*100:.1f}%  ({results['include']['elapsed_sec']:.1f}s)")
    if "flores_ne2en" in results:
        print(f"  FLORES NE→EN (n={results['flores_ne2en']['n']}): chrF {results['flores_ne2en']['chrf']:.2f}  ({results['flores_ne2en']['elapsed_sec']:.1f}s)")
    if "flores_en2ne" in results:
        print(f"  FLORES EN→NE (n={results['flores_en2ne']['n']}): chrF {results['flores_en2ne']['chrf']:.2f}  ({results['flores_en2ne']['elapsed_sec']:.1f}s)")
    if "xlsum" in results:
        print(f"  XLSum Nepali (n={results['xlsum']['n']}): ROUGE-L {results['xlsum']['rouge_l']:.2f}  ({results['xlsum']['elapsed_sec']:.1f}s)")
    print(f"  Wallclock total: {results['wallclock_sec']:.1f}s")
    print(f"  wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
