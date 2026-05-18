#!/usr/bin/env python3
"""Focused v4b checkpoint + decoding sweep.

This is intentionally narrower than full eval. It checks the surfaces that
blocked v4b:
  - Roman-Nepali no-source prompts for repetition/mojibake/empty output.
  - The grounded gold items that v4b final wrongly marked as refused.
"""
from __future__ import annotations

import argparse
import gc
import json
import logging
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from eval_groundedness import (  # noqa: E402
    SYSTEM_PROMPT,
    build_user_prompt,
    load_gold,
    score_one,
)
from eval_sft_v1 import (  # noqa: E402
    MOJIBAKE_RE,
    ROMAN_PROMPTS,
    _detect_repetition_loop,
    _unwrap_gemma4_clippable_linears,
)


REFUSAL_PAT = re.compile(
    r"(आधिकारिक स्रोत भेटिन|cannot find an authoritative source|source bhetina|srot bhetina)",
    re.I,
)


DECODE_PRESETS = {
    "baseline_300": {"max_new_tokens": 300, "repetition_penalty": 1.0, "no_repeat_ngram_size": 0},
    "short_180": {"max_new_tokens": 180, "repetition_penalty": 1.0, "no_repeat_ngram_size": 0},
    "short_rep_180": {"max_new_tokens": 180, "repetition_penalty": 1.10, "no_repeat_ngram_size": 6},
    "rep_240": {"max_new_tokens": 240, "repetition_penalty": 1.08, "no_repeat_ngram_size": 6},
    "short_rep_trim_180": {
        "max_new_tokens": 180,
        "repetition_penalty": 1.10,
        "no_repeat_ngram_size": 6,
        "post_trim": True,
    },
}


def trim_repeated_refusal_tail(text: str) -> str:
    """Small server-side-style postprocess candidate for repeated refusal tails."""
    lines = [ln.rstrip() for ln in text.splitlines()]
    out: list[str] = []
    refusal_seen = 0
    unverified_seen = 0
    seen_norm: Counter[str] = Counter()
    for line in lines:
        norm = re.sub(r"\s+", " ", line.strip().lower())
        if not norm:
            if out and out[-1]:
                out.append("")
            continue
        if "[unverified]" in norm:
            unverified_seen += 1
            if unverified_seen > 1:
                break
        if REFUSAL_PAT.search(norm):
            refusal_seen += 1
            if refusal_seen > 1:
                break
        seen_norm[norm] += 1
        if seen_norm[norm] > 1:
            break
        out.append(line)
    return "\n".join(out).strip()


class SweepBackend:
    def __init__(self, base_model: str, adapter: Path, torch_dtype: str = "bfloat16"):
        import torch
        from peft import PeftModel
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        token = os.environ.get("HF_TOKEN")
        self.tokenizer = AutoTokenizer.from_pretrained(base_model, token=token, trust_remote_code=True)
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        if not self.tokenizer.chat_template:
            from huggingface_hub import hf_hub_download

            tpl = hf_hub_download(base_model, "chat_template.jinja", token=token)
            self.tokenizer.chat_template = Path(tpl).read_text(encoding="utf-8")

        dtype = getattr(torch, torch_dtype)
        logging.info("loading base model: %s", base_model)
        self.model = AutoModelForCausalLM.from_pretrained(
            base_model,
            token=token,
            torch_dtype=dtype,
            device_map="cuda",
            trust_remote_code=True,
        )
        n = _unwrap_gemma4_clippable_linears(self.model)
        if n:
            logging.info("unwrapped %d Gemma4ClippableLinear modules", n)
        logging.info("loading adapter: %s", adapter)
        self.model = PeftModel.from_pretrained(self.model, str(adapter))
        self.model.eval()
        self.device = next(self.model.parameters()).device

    def close(self) -> None:
        del self.model
        gc.collect()
        self.torch.cuda.empty_cache()

    def chat_batch(self, prompts: list[tuple[str, str]], decode: dict) -> list[str]:
        torch = self.torch
        texts: list[str] = []
        for system, user in prompts:
            msgs = []
            if system:
                msgs.append({"role": "system", "content": system})
            msgs.append({"role": "user", "content": user})
            texts.append(self.tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True))

        prev_side = self.tokenizer.padding_side
        self.tokenizer.padding_side = "left"
        try:
            encoded = self.tokenizer(texts, return_tensors="pt", padding=True, add_special_tokens=False)
        finally:
            self.tokenizer.padding_side = prev_side

        input_ids = encoded["input_ids"].to(self.device)
        attention_mask = encoded["attention_mask"].to(self.device)
        prompt_len = input_ids.size(1)
        kwargs = {
            "max_new_tokens": int(decode["max_new_tokens"]),
            "do_sample": False,
            "pad_token_id": self.tokenizer.pad_token_id or self.tokenizer.eos_token_id,
            "eos_token_id": self.tokenizer.eos_token_id,
        }
        if float(decode.get("repetition_penalty", 1.0)) != 1.0:
            kwargs["repetition_penalty"] = float(decode["repetition_penalty"])
        if int(decode.get("no_repeat_ngram_size", 0)) > 0:
            kwargs["no_repeat_ngram_size"] = int(decode["no_repeat_ngram_size"])

        with torch.no_grad():
            out_ids = self.model.generate(input_ids, attention_mask=attention_mask, **kwargs)

        outs: list[str] = []
        for i in range(out_ids.size(0)):
            text = self.tokenizer.decode(out_ids[i, prompt_len:], skip_special_tokens=True).strip()
            if decode.get("post_trim"):
                text = trim_repeated_refusal_tail(text)
            outs.append(text)
        return outs


def roman_prompts() -> list[tuple[str, str, str]]:
    return [
        (p, SYSTEM_PROMPT, f"Question: {p}\n\nSources:\n(no candidate sources surfaced)")
        for p in ROMAN_PROMPTS
    ]


def load_wrongly_refused_gold(gold_path: Path, previous_full_gold: Path) -> list[dict]:
    gold = {r["id"]: r for r in load_gold(gold_path)}
    prev = json.loads(previous_full_gold.read_text(encoding="utf-8"))["results"]
    ids = [r["id"] for r in prev if r.get("type") == "grounded" and r.get("wrongly_refused")]
    return [gold[i] for i in ids if i in gold]


def summarize_roman(items: list[dict]) -> dict:
    return {
        "n": len(items),
        "n_degen": sum(1 for r in items if r["loop"] or r["mojibake"] or r["empty"]),
        "n_loop": sum(1 for r in items if r["loop"]),
        "n_mojibake": sum(1 for r in items if r["mojibake"]),
        "n_empty": sum(1 for r in items if r["empty"]),
        "n_refusal_marker": sum(1 for r in items if REFUSAL_PAT.search(r["a"])),
        "n_unverified": sum(1 for r in items if "[unverified]" in r["a"].lower()),
        "avg_chars": round(sum(len(r["a"]) for r in items) / max(1, len(items)), 1),
    }


def summarize_wrong(results: list[dict]) -> dict:
    return {
        "n": len(results),
        "wrongly_refused": sum(1 for r in results if r.get("wrongly_refused")),
        "model_refused": sum(1 for r in results if r.get("model_refused")),
        "url_recall_mean": round(
            sum(float(r.get("url_recall") or 0.0) for r in results) / max(1, len(results)), 4
        ),
        "chrf_mean": round(sum(float(r.get("chrf") or 0.0) for r in results) / max(1, len(results)), 4),
        "n_loop": sum(1 for r in results if _detect_repetition_loop(r.get("model_output", ""))),
        "n_refusal_marker": sum(1 for r in results if REFUSAL_PAT.search(r.get("model_output", ""))),
    }


def run_one(adapter: Path, ckpt_name: str, args: argparse.Namespace, wrong_gold: list[dict]) -> list[dict]:
    backend = SweepBackend(args.base, adapter, args.torch_dtype)
    rows: list[dict] = []
    try:
        for preset_name in args.presets:
            decode = DECODE_PRESETS[preset_name]
            logging.info("checkpoint=%s preset=%s", ckpt_name, preset_name)
            t0 = time.time()

            rp = roman_prompts()
            roman_out = backend.chat_batch([(system, user) for _, system, user in rp], decode)
            roman_items = []
            for (q, _, _), out in zip(rp, roman_out):
                roman_items.append(
                    {
                        "q": q,
                        "a": out,
                        "loop": _detect_repetition_loop(out),
                        "mojibake": bool(MOJIBAKE_RE.search(out)),
                        "empty": not out.strip(),
                    }
                )

            wrong_prompts = [
                (SYSTEM_PROMPT, build_user_prompt(it["question"], it.get("candidate_chunks") or []))
                for it in wrong_gold
            ]
            wrong_out = backend.chat_batch(wrong_prompts, decode) if wrong_prompts else []
            wrong_results = [
                score_one(it, out, elapsed_ms=0) for it, out in zip(wrong_gold, wrong_out)
            ]

            rows.append(
                {
                    "checkpoint": ckpt_name,
                    "preset": preset_name,
                    "decode": decode,
                    "elapsed_sec": round(time.time() - t0, 1),
                    "roman": summarize_roman(roman_items),
                    "wrong_subset": summarize_wrong(wrong_results),
                    "roman_items": roman_items,
                    "wrong_subset_results": wrong_results,
                }
            )
    finally:
        backend.close()
    return rows


def write_markdown(rows: list[dict], out_path: Path) -> None:
    def score(row: dict) -> tuple:
        return (
            row["roman"]["n_degen"],
            row["wrong_subset"]["wrongly_refused"],
            -row["wrong_subset"]["chrf_mean"],
            row["roman"]["avg_chars"],
        )

    ranked = sorted(rows, key=score)
    lines = ["# v4b Checkpoint + Decoding Sweep\n"]
    lines.append("Sorted recommendation metric: Roman degen, wrongly-refused subset, chrF, length.\n")
    lines.append("| rank | checkpoint | preset | roman degen | roman loops | wrong refused | wrong chrF | URL recall | avg chars |")
    lines.append("|---:|---|---|---:|---:|---:|---:|---:|---:|")
    for i, row in enumerate(ranked, 1):
        lines.append(
            f"| {i} | {row['checkpoint']} | {row['preset']} | "
            f"{row['roman']['n_degen']}/{row['roman']['n']} | "
            f"{row['roman']['n_loop']} | "
            f"{row['wrong_subset']['wrongly_refused']}/{row['wrong_subset']['n']} | "
            f"{row['wrong_subset']['chrf_mean']:.2f} | "
            f"{row['wrong_subset']['url_recall_mean']:.2f} | "
            f"{row['roman']['avg_chars']:.0f} |"
        )
    lines.append("\n## Top Candidate Details\n")
    for row in ranked[:5]:
        lines.append(
            f"### {row['checkpoint']} / {row['preset']}\n\n"
            f"- Roman: {row['roman']}\n"
            f"- Wrong subset: {row['wrong_subset']}\n"
        )
    out_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="google/gemma-4-E2B-it")
    ap.add_argument("--ckpt-root", type=Path, required=True)
    ap.add_argument("--gold", type=Path, required=True)
    ap.add_argument("--previous-full-gold", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--torch-dtype", default="bfloat16")
    ap.add_argument(
        "--checkpoints",
        default="step200,step400,step600,step800,step1000,step1200,step1400,final,best",
    )
    ap.add_argument(
        "--presets",
        default="baseline_300,short_180,short_rep_180,rep_240,short_rep_trim_180",
    )
    args = ap.parse_args()
    args.presets = [p.strip() for p in args.presets.split(",") if p.strip()]
    bad = [p for p in args.presets if p not in DECODE_PRESETS]
    if bad:
        raise SystemExit(f"unknown decode presets: {bad}")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    wrong_gold = load_wrongly_refused_gold(args.gold, args.previous_full_gold)
    logging.info("loaded %d prior wrongly-refused gold items", len(wrong_gold))

    rows: list[dict] = []
    for ckpt in [c.strip() for c in args.checkpoints.split(",") if c.strip()]:
        adapter = args.ckpt_root / ckpt
        if not (adapter / "adapter_model.safetensors").exists():
            logging.warning("skip missing checkpoint: %s", adapter)
            continue
        rows.extend(run_one(adapter, ckpt, args, wrong_gold))
        (args.out_dir / "sweep_partial.json").write_text(
            json.dumps({"rows": rows}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    result = {"decode_presets": DECODE_PRESETS, "rows": rows}
    (args.out_dir / "sweep.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_markdown(rows, args.out_dir / "SUMMARY.md")
    logging.info("wrote %s", args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
