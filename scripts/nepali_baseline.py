#!/usr/bin/env python3
"""Gemma 3 4B Nepali baseline via mlx-lm.

Benchmarks:
  1. Belebele Nepali (npi_Deva)       — 200 MC comprehension questions
  2. FLORES-200 EN → NE                — 100 translation pairs (chrF++)
  3. FLORES-200 NE → EN                — 100 translation pairs (chrF++)
  4. Roman-Nepali qualitative          — 20 generations for manual review

Incremental results dump avoids losing work on disconnect.

Usage:
    python nepali_baseline.py [--out DIR] [--n-belebele N] [--n-flores N]
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
import traceback
from pathlib import Path

import sacrebleu
from datasets import load_dataset
from mlx_lm import generate, load

MODEL_NAME = "mlx-community/gemma-3-4b-it-bf16"
SEED = 42


def chat(model, tokenizer, user_msg: str, max_tokens: int = 300) -> str:
    messages = [{"role": "user", "content": user_msg}]
    prompt = tokenizer.apply_chat_template(
        messages, add_generation_prompt=True, tokenize=False
    )
    try:
        return generate(
            model, tokenizer, prompt=prompt, max_tokens=max_tokens, verbose=False
        )
    except Exception as e:
        return f"__ERROR__ {type(e).__name__}: {e}"


def extract_choice(response: str, valid: str = "ABCD") -> str | None:
    """Find the first standalone A/B/C/D in the response."""
    m = re.search(rf"\b([{valid}])\b", response)
    if m:
        return m.group(1)
    # Fallback: first A/B/C/D character
    for c in response:
        if c in valid:
            return c
    return None


def dump_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def eval_belebele(model, tokenizer, n: int, out_dir: Path) -> dict:
    print(f"\n=== Belebele Nepali (npi_Deva) — n={n} ===", flush=True)
    t0 = time.time()
    ds = load_dataset("facebook/belebele", "npi_Deva", split="test")
    print(f"  loaded dataset: {len(ds)} examples")
    rng = random.Random(SEED)
    indices = rng.sample(range(len(ds)), min(n, len(ds)))

    correct = 0
    total = 0
    no_answer = 0
    samples = []

    for i, idx in enumerate(indices):
        ex = ds[idx]
        prompt = (
            "Read the passage in Nepali and answer the question by choosing the "
            "single best option (A, B, C, or D). Reply with only the letter.\n\n"
            f"Passage: {ex['flores_passage']}\n\n"
            f"Question: {ex['question']}\n\n"
            f"A) {ex['mc_answer1']}\n"
            f"B) {ex['mc_answer2']}\n"
            f"C) {ex['mc_answer3']}\n"
            f"D) {ex['mc_answer4']}\n\n"
            "Answer:"
        )
        resp = chat(model, tokenizer, prompt, max_tokens=20)
        pred = extract_choice(resp)
        gold_map = {"1": "A", "2": "B", "3": "C", "4": "D"}
        gold = gold_map.get(str(ex["correct_answer_num"]))
        if pred is None:
            no_answer += 1
        elif pred == gold:
            correct += 1
        total += 1
        if i < 5:
            samples.append({
                "idx": idx, "pred": pred, "gold": gold,
                "response": resp[:120],
            })
        if (i + 1) % 25 == 0 or i == len(indices) - 1:
            acc = correct / total
            print(f"  [{i+1}/{len(indices)}] acc={acc:.3f}  no_answer={no_answer}", flush=True)

    result = {
        "benchmark": "Belebele Nepali",
        "n": total,
        "correct": correct,
        "accuracy": correct / total if total else 0.0,
        "no_answer": no_answer,
        "elapsed_sec": round(time.time() - t0, 1),
        "samples": samples,
    }
    dump_json(out_dir / "belebele.json", result)
    print(f"  DONE: accuracy={result['accuracy']:.3f} in {result['elapsed_sec']:.0f}s", flush=True)
    return result


def _load_flores_pairs() -> tuple[list[str], list[str]] | None:
    """Return (eng_sents, nep_sents) paired by id. None if all sources fail.

    Handles both schemas:
      * legacy `facebook/flores` config `eng_Latn-npi_Deva` — paired rows with
        `sentence_eng_Latn` / `sentence_npi_Deva` columns.
      * current `openlanguagedata/flores_plus` — one row per (id, language);
        columns `id` / `iso_639_3` / `iso_15924` / `text`. Requires id-pairing.
    """
    # Try the legacy paired-row dataset first.
    try:
        ds = load_dataset("facebook/flores", "eng_Latn-npi_Deva", split="dev")
        eng = [ex.get("sentence_eng_Latn") for ex in ds]
        nep = [ex.get("sentence_npi_Deva") for ex in ds]
        print(f"  loaded facebook/flores: {len(eng)} pairs", flush=True)
        return eng, nep
    except Exception as e:
        print(f"  facebook/flores failed: {str(e)[:140]}", flush=True)

    # Fall back: fetch the per-language JSONL files directly via hf_hub_download.
    # Bypasses the `datasets` library's flaky gate check on gated datasets —
    # hf_hub_download respects HF_TOKEN reliably, and flores_plus stores data
    # as `dev/{lang}.jsonl` with 1-to-1 line alignment across languages.
    try:
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
    except Exception as e:
        print(f"  openlanguagedata/flores_plus direct fetch failed: {str(e)[:200]}", flush=True)
        return None

    eng: list[str] = []
    nep: list[str] = []
    with open(eng_path, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            eng.append(row.get("text") or row.get("sentence") or "")
    with open(nep_path, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            nep.append(row.get("text") or row.get("sentence") or "")

    if len(eng) != len(nep):
        print(
            f"  flores_plus: eng ({len(eng)}) and npi ({len(nep)}) row counts differ; truncating",
            flush=True,
        )
        n = min(len(eng), len(nep))
        eng, nep = eng[:n], nep[:n]

    print(f"  loaded flores_plus: {len(eng)} pairs (aligned by row)", flush=True)
    return eng, nep


def eval_flores(model, tokenizer, n: int, direction: str, out_dir: Path) -> dict:
    """direction: 'en2ne' or 'ne2en'."""
    print(f"\n=== FLORES-200 {direction} — n={n} ===", flush=True)
    t0 = time.time()

    pairs = _load_flores_pairs()
    if pairs is None:
        return {"benchmark": f"FLORES {direction}", "error": "no pairs loaded"}
    eng_sents, nep_sents = pairs

    rng = random.Random(SEED)
    indices = rng.sample(range(len(eng_sents)), min(n, len(eng_sents)))

    hyps, refs = [], []
    samples = []
    errors = 0

    for i, idx in enumerate(indices):
        eng = eng_sents[idx]
        nep = nep_sents[idx]
        if direction == "en2ne":
            src, ref = eng, nep
            prompt = (
                "Translate the following English sentence into Nepali (Devanagari). "
                "Reply with only the Nepali translation.\n\n"
                f"English: {src}\n\nNepali:"
            )
        else:
            src, ref = nep, eng
            prompt = (
                "Translate the following Nepali sentence into English. "
                "Reply with only the English translation.\n\n"
                f"Nepali: {src}\n\nEnglish:"
            )
        if not src or not ref:
            errors += 1
            continue
        hyp = chat(model, tokenizer, prompt, max_tokens=200).strip()
        for prefix in ("Nepali:", "English:", "Translation:"):
            if hyp.startswith(prefix):
                hyp = hyp[len(prefix):].strip()
        hyps.append(hyp)
        refs.append(ref)
        if i < 5:
            samples.append({"src": src, "hyp": hyp, "ref": ref})
        if (i + 1) % 20 == 0 or i == len(indices) - 1:
            try:
                running = sacrebleu.corpus_chrf(hyps, [refs], word_order=2).score
            except Exception:
                running = 0.0
            print(f"  [{i+1}/{len(indices)}] running chrF++={running:.2f}", flush=True)

    try:
        chrf = sacrebleu.corpus_chrf(hyps, [refs], word_order=2)
        bleu = sacrebleu.corpus_bleu(hyps, [refs])
    except Exception as e:
        chrf = type("", (), {"score": 0.0})
        bleu = type("", (), {"score": 0.0})
        print(f"  scoring error: {e}", flush=True)

    result = {
        "benchmark": f"FLORES-200 {direction}",
        "n": len(hyps),
        "chrF_plus_plus": round(chrf.score, 2),
        "BLEU": round(bleu.score, 2),
        "errors": errors,
        "elapsed_sec": round(time.time() - t0, 1),
        "samples": samples,
    }
    dump_json(out_dir / f"flores_{direction}.json", result)
    print(
        f"  DONE: chrF++={result['chrF_plus_plus']:.2f}  BLEU={result['BLEU']:.2f} "
        f"in {result['elapsed_sec']:.0f}s", flush=True
    )
    return result


def eval_roman_nepali_qualitative(model, tokenizer, out_dir: Path) -> dict:
    print("\n=== Roman-Nepali qualitative (n=20) ===", flush=True)
    t0 = time.time()
    # Hand-crafted 20 Roman-Nepali queries covering gov-helpdesk domain.
    prompts = [
        "mero nagarikta banauna ko lagi kun office janu parcha?",
        "passport renew garna kaha janu parcha?",
        "company registration kasari garne? kati kharcha lagcha?",
        "PAN number kasari banaune?",
        "driving license ko lagi k k chaine?",
        "malai citizenship certificate chaiyo, kun kagajat chaine?",
        "VAT ra PAN ma k farak cha?",
        "mero gharbata kunai documents online submit garna sakinchha?",
        "kirtipur ma kun IRD office cha?",
        "jagga ra ghar ko lagi malpot kaha tirne?",
        "nepal sarkar le kati tax laucha?",
        "sarkari job ko bigyapan kaha herne?",
        "bachhako janmadarta kasari garne?",
        "marriage registration ko process k cha?",
        "vehicle ko blue book renewal kasari garne?",
        "insurance claim kasari garne?",
        "sahkaari sanstha darta garna k chaine?",
        "udyog darta ko lagi kaha janu parcha?",
        "sarkari scholarship ko bare jankari kaha?",
        "online tax file kasari garne?",
    ]
    results = []
    for i, p in enumerate(prompts):
        resp = chat(model, tokenizer, p, max_tokens=250)
        results.append({"q": p, "response": resp})
        print(f"  [{i+1}/{len(prompts)}] done", flush=True)

    out = {
        "benchmark": "Roman-Nepali qualitative",
        "n": len(results),
        "elapsed_sec": round(time.time() - t0, 1),
        "responses": results,
    }
    dump_json(out_dir / "roman_nepali.json", out)
    print(f"  DONE: {len(results)} responses in {out['elapsed_sec']:.0f}s", flush=True)
    return out


def write_report(all_results: dict, out_dir: Path) -> None:
    report = out_dir / "gemma3_nepali_baseline.md"
    lines = [
        "# Gemma 3 4B — Nepali Baseline Report",
        "",
        f"**Model:** `{MODEL_NAME}`",
        f"**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Seed:** {SEED}",
        "",
        "## Summary",
        "",
        "| Benchmark | n | Metric | Score |",
        "|---|---|---|---|",
    ]
    for key, r in all_results.items():
        if r is None:
            continue
        if "accuracy" in r:
            lines.append(f"| {r['benchmark']} | {r['n']} | accuracy | {r['accuracy']:.3f} |")
        if "chrF_plus_plus" in r:
            lines.append(f"| {r['benchmark']} | {r['n']} | chrF++ | {r['chrF_plus_plus']:.2f} |")
            lines.append(f"| {r['benchmark']} | {r['n']} | BLEU | {r['BLEU']:.2f} |")
    lines.append("")

    # Per-benchmark details
    for key, r in all_results.items():
        if r is None:
            continue
        lines.append(f"## {r['benchmark']}")
        lines.append("")
        for k in ("n", "accuracy", "correct", "no_answer", "chrF_plus_plus", "BLEU",
                  "errors", "elapsed_sec"):
            if k in r:
                lines.append(f"- **{k}:** {r[k]}")
        if "samples" in r:
            lines.append("")
            lines.append("### Samples")
            for s in r["samples"][:5]:
                lines.append("")
                lines.append("```")
                lines.append(json.dumps(s, ensure_ascii=False, indent=2))
                lines.append("```")
        if "responses" in r:
            lines.append("")
            lines.append("### Responses")
            for i, s in enumerate(r["responses"][:10]):
                lines.append(f"\n**Q{i+1}:** {s['q']}")
                lines.append(f"\n**A:** {s['response'][:400]}")
        lines.append("")

    report.write_text("\n".join(lines))
    print(f"\n=== REPORT WRITTEN to {report} ===", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="/Volumes/T9/gemma-god/eval")
    ap.add_argument("--n-belebele", type=int, default=200)
    ap.add_argument("--n-flores", type=int, default=100)
    ap.add_argument("--skip-belebele", action="store_true")
    ap.add_argument("--skip-flores", action="store_true")
    ap.add_argument("--skip-roman", action="store_true")
    args = ap.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[cfg] output dir: {out_dir}", flush=True)
    print(f"[cfg] seed: {SEED}", flush=True)

    print(f"[load] {MODEL_NAME}")
    t0 = time.time()
    model, tokenizer = load(MODEL_NAME)
    print(f"[load] ready in {time.time()-t0:.1f}s", flush=True)

    all_results: dict[str, dict | None] = {}

    if not args.skip_belebele:
        try:
            all_results["belebele"] = eval_belebele(model, tokenizer, args.n_belebele, out_dir)
        except Exception:
            traceback.print_exc()
            all_results["belebele"] = None

    if not args.skip_flores:
        try:
            all_results["flores_en2ne"] = eval_flores(model, tokenizer, args.n_flores, "en2ne", out_dir)
        except Exception:
            traceback.print_exc()
            all_results["flores_en2ne"] = None
        try:
            all_results["flores_ne2en"] = eval_flores(model, tokenizer, args.n_flores, "ne2en", out_dir)
        except Exception:
            traceback.print_exc()
            all_results["flores_ne2en"] = None

    if not args.skip_roman:
        try:
            all_results["roman_nepali"] = eval_roman_nepali_qualitative(model, tokenizer, out_dir)
        except Exception:
            traceback.print_exc()
            all_results["roman_nepali"] = None

    write_report(all_results, out_dir)
    print("\n[done]", flush=True)


if __name__ == "__main__":
    main()
