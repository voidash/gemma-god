#!/usr/bin/env python3
"""Fast checkpoint eval for CPT runs.

Loads base Gemma 3 4B + a LoRA adapter, runs small-scale Belebele + FLORES
+ Roman-NE generations. Takes ~10 min per checkpoint. Intended to be run
against `checkpoints/cpt_vN/NNN_adapters.safetensors` (or the live
`checkpoints/cpt_vN/adapters.safetensors` when training is in progress).

Output: survey/eval/fast_eval_<label>.json with scores for trajectory
tracking, and prints a 1-line summary.

Usage:
    python scripts/fast_eval.py --adapter /path/to/adapters.safetensors --label step-500
    # or to baseline the base model without any adapter:
    python scripts/fast_eval.py --no-adapter --label base
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from pathlib import Path

BASE_MODEL = "mlx-community/gemma-3-4b-it-bf16"
SEED = 42
N_BELEBELE = 50
N_FLORES = 30
N_ROMAN = 10


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", help="Path to adapters.safetensors (omit for base-model eval)")
    ap.add_argument("--no-adapter", action="store_true")
    ap.add_argument("--label", required=True, help="Short label for this eval (e.g. step-500)")
    ap.add_argument("--out-dir", default="/Volumes/T9/gemma-god/eval")
    args = ap.parse_args()

    from mlx_lm import generate, load

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[load] base={BASE_MODEL}  adapter={args.adapter if not args.no_adapter else 'NONE'}", flush=True)
    t0 = time.time()
    if args.no_adapter:
        model, tokenizer = load(BASE_MODEL)
    else:
        adapter_path = args.adapter
        if adapter_path and os.path.isfile(adapter_path):
            # MLX-LM expects a DIRECTORY path for adapter loading.
            adapter_dir = str(Path(adapter_path).parent)
        else:
            adapter_dir = adapter_path
        model, tokenizer = load(BASE_MODEL, adapter_path=adapter_dir)
    print(f"[load] done in {time.time()-t0:.1f}s", flush=True)

    def chat(user_msg: str, max_tokens: int = 200) -> str:
        messages = [{"role": "user", "content": user_msg}]
        prompt = tokenizer.apply_chat_template(messages, add_generation_prompt=True, tokenize=False)
        return generate(model, tokenizer, prompt=prompt, max_tokens=max_tokens, verbose=False)

    # ---- Belebele (50 MC) -------------------------------------------------
    import sacrebleu
    from datasets import load_dataset

    rng = random.Random(SEED)
    print("\n[eval] Belebele Nepali (50 Qs)", flush=True)
    t_be = time.time()
    ds = load_dataset("facebook/belebele", "npi_Deva", split="test", token=os.environ.get("HF_TOKEN"))
    idxs = rng.sample(range(len(ds)), N_BELEBELE)
    correct = 0
    for i, idx in enumerate(idxs):
        ex = ds[idx]
        prompt = (
            "Read the passage in Nepali and answer the question by choosing the "
            "single best option (A, B, C, or D). Reply with only the letter.\n\n"
            f"Passage: {ex['flores_passage']}\n\n"
            f"Question: {ex['question']}\n\n"
            f"A) {ex['mc_answer1']}\nB) {ex['mc_answer2']}\n"
            f"C) {ex['mc_answer3']}\nD) {ex['mc_answer4']}\n\nAnswer:"
        )
        resp = chat(prompt, max_tokens=20)
        m = re.search(r"\b([ABCD])\b", resp)
        gold = {"1": "A", "2": "B", "3": "C", "4": "D"}.get(str(ex["correct_answer_num"]))
        if m and m.group(1) == gold:
            correct += 1
    belebele_acc = correct / N_BELEBELE
    belebele_sec = time.time() - t_be
    print(f"  Belebele: {correct}/{N_BELEBELE} = {belebele_acc:.3f}  ({belebele_sec:.0f}s)", flush=True)

    # ---- FLORES 30 pairs each direction ----------------------------------
    from huggingface_hub import hf_hub_download

    print("\n[eval] FLORES-200 NE<->EN (30 pairs each)", flush=True)
    token = os.environ.get("HF_TOKEN")
    eng_path = hf_hub_download("openlanguagedata/flores_plus", "dev/eng_Latn.jsonl",
                               repo_type="dataset", token=token)
    nep_path = hf_hub_download("openlanguagedata/flores_plus", "dev/npi_Deva.jsonl",
                               repo_type="dataset", token=token)
    eng = [json.loads(l)["text"] for l in open(eng_path)]
    nep = [json.loads(l)["text"] for l in open(nep_path)]
    sample_idx = rng.sample(range(min(len(eng), len(nep))), N_FLORES)

    flores_results: dict[str, float] = {}
    for direction in ("en2ne", "ne2en"):
        t_fl = time.time()
        hyps, refs = [], []
        for idx in sample_idx:
            if direction == "en2ne":
                src, ref = eng[idx], nep[idx]
                p = f"Translate the following English sentence into Nepali (Devanagari). Reply with only the translation.\n\nEnglish: {src}\n\nNepali:"
            else:
                src, ref = nep[idx], eng[idx]
                p = f"Translate the following Nepali sentence into English. Reply with only the translation.\n\nNepali: {src}\n\nEnglish:"
            h = chat(p, max_tokens=200).strip()
            for prefix in ("Nepali:", "English:", "Translation:"):
                if h.startswith(prefix):
                    h = h[len(prefix):].strip()
            hyps.append(h)
            refs.append(ref)
        chrf = sacrebleu.corpus_chrf(hyps, [refs], word_order=2).score
        flores_results[direction] = round(chrf, 2)
        print(f"  FLORES {direction}: chrF++ = {chrf:.2f}  ({time.time()-t_fl:.0f}s)", flush=True)

    # ---- Roman-NE generations --------------------------------------------
    print("\n[eval] Roman-Nepali qualitative (10 prompts)", flush=True)
    t_rn = time.time()
    roman_prompts = [
        "mero nagarikta banauna ko lagi kun office janu parcha?",
        "passport renew garna kaha janu parcha?",
        "company registration kasari garne?",
        "PAN number kasari banaune?",
        "driving license ko lagi k k chaine?",
        "VAT ra PAN ma k farak cha?",
        "nagarikta certificate hareyo, kaha janu parcha?",
        "jagga ko malpot kaha tirne?",
        "bachhako janmadarta kasari garne?",
        "online tax file kasari garne?",
    ]
    roman_responses = []
    for p in roman_prompts:
        r = chat(p, max_tokens=200)
        roman_responses.append({"q": p, "a": r})

    # Heuristic quality check: count catastrophic failures (e.g. repetition loops,
    # language-switch, empty). Conservative — just look for obvious degens.
    degen_count = 0
    for r in roman_responses:
        a = r["a"]
        if not a.strip():
            degen_count += 1
            continue
        words = a.split()
        if len(words) >= 5:
            # Repeating same short phrase >=5x is a loop
            first_5 = " ".join(words[:5])
            rest = a[len(first_5):]
            if rest.count(first_5) >= 3:
                degen_count += 1
    print(f"  Roman-NE: {N_ROMAN} generations, {degen_count} degen detected  ({time.time()-t_rn:.0f}s)", flush=True)

    # ---- write report ----------------------------------------------------
    result = {
        "label": args.label,
        "adapter": args.adapter if not args.no_adapter else None,
        "base_model": BASE_MODEL,
        "belebele_nepali": {
            "n": N_BELEBELE,
            "correct": correct,
            "accuracy": round(belebele_acc, 3),
            "elapsed_sec": round(belebele_sec, 1),
        },
        "flores": {
            "n": N_FLORES,
            "en2ne_chrf": flores_results["en2ne"],
            "ne2en_chrf": flores_results["ne2en"],
        },
        "roman_nepali": {
            "n": N_ROMAN,
            "degen_count": degen_count,
            "responses": roman_responses,
        },
        "elapsed_total_sec": round(time.time() - t0, 1),
    }

    out_path = out_dir / f"fast_eval_{args.label}.json"
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2))

    # one-line trajectory summary
    print(
        f"\n[{args.label}] "
        f"belebele={belebele_acc:.3f}  "
        f"flores_en2ne={flores_results['en2ne']:.1f}  "
        f"flores_ne2en={flores_results['ne2en']:.1f}  "
        f"roman_degen={degen_count}/{N_ROMAN}  "
        f"total={result['elapsed_total_sec']:.0f}s",
        flush=True,
    )
    print(f"wrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
