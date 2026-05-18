#!/usr/bin/env python3
"""Small direct decoding sweep for v6.4 Gemma adapters.

The production `/query` path can return deterministic resolver/composer answers
with generation skipped. That is good for serving, but it does not distinguish
adapter checkpoints. This script loads each adapter directly and runs a compact
set of prompts that exercise the SFT behavior itself.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path
from typing import Any


SYSTEM = """You are SpeakGov, a Nepal government-service navigator.
Do resolver/intake first. Ask compact follow-up questions when a government
service request is ambiguous. Use plain English, Nepali, or Roman Nepali to
match the user. Do not switch to Hindi. Give factual, source-aware guidance,
useful contacts when relevant, uncertainty, and next steps. If a question is
outside government services, answer briefly and say you are mainly built for
Nepal government services."""


CASES: list[dict[str, Any]] = [
    {
        "id": "ambiguous_citizenship",
        "prompt": "how to get citizenship in Sankhuwasabha?",
        "must_any": ["municipality", "ward", "case", "first-time", "duplicate"],
        "must_not": ["cannot find an authoritative source"],
    },
    {
        "id": "roman_passport_abroad",
        "prompt": "ma Qatar ma chu passport renew garna paryo",
        "must_any": ["passport", "qatar", "embassy", "consular"],
        "must_not": ["cannot find an authoritative source"],
    },
    {
        "id": "manpower_cheated",
        "prompt": "who to contact when i got cheated by manpower agency?",
        "must_any": ["foreign employment", "department", "complaint", "helpline", "contact"],
        "must_not": ["hindi"],
    },
    {
        "id": "jiri_mayor_ne",
        "prompt": "जिरी नगरपालिकाको नगर प्रमुख को हुन्?",
        "must_any": ["जिरी", "नगर प्रमुख", "स्रोत"],
        "must_not": ["cannot find"],
    },
    {
        "id": "off_domain_math",
        "prompt": "2 + 2 kati ho?",
        "must_any": ["4"],
        "must_not": ["cannot find an authoritative source"],
    },
    {
        "id": "contact_source_prompt",
        "prompt": (
            "Question: Who is the contact person for Jiri Municipality?\n\n"
            "Planner: service=municipality_contact; decision=answerable; expected_domains=jirimun.gov.np\n\n"
            "Sources:\n"
            "[S1] Tacit verified staff note. Man Bahadur Jirel is listed as an information/contact person for general Jiri Municipality helpdesk questions. Source URL: https://jirimun.gov.np\n"
            "[S2] Gov page. Jiri Municipality contact page lists Contact No: +977 071 5555556. Source URL: https://jirimun.gov.np\n\n"
            "Answer using only these sources and cite source ids like [S1]."
        ),
        "must_any": ["Man Bahadur Jirel", "071 5555556", "[S1]", "[S2]"],
        "must_not": ["cannot find"],
    },
]

HINDI_RE = re.compile(r"\b(?:hai|nahi|aap|hamare|kijiye|sakta hai|karna hoga)\b|है|नहीं|कीजिए|करना होगा", re.I)
REFUSAL_RE = re.compile(r"cannot find an authoritative source|आधिकारिक स्रोत भेटिन|srot bhetina", re.I)
MOJIBAKE_RE = re.compile(r"[ÃÂ�]")


def hf_token() -> str | None:
    if token := os.environ.get("HF_TOKEN"):
        return token
    token_file = Path(os.environ.get("HF_TOKEN_FILE", "") or "")
    if token_file.exists():
        return token_file.read_text(encoding="utf-8").strip()
    for path in (Path.home() / ".hf_token", Path.home() / ".fmw"):
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").strip()
        if text.startswith("HF_TOKEN="):
            return text.split("=", 1)[1].strip()
        if text.startswith("hf_"):
            return text
    return None


def unwrap_gemma4_clippable_linears(model: Any) -> int:
    import torch.nn as nn  # type: ignore[import-not-found]

    n = 0
    for parent in list(model.modules()):
        for name, child in list(parent.named_children()):
            if type(child).__name__ == "Gemma4ClippableLinear":
                inner = getattr(child, "linear", None)
                if isinstance(inner, nn.Linear):
                    setattr(parent, name, inner)
                    n += 1
    return n


def choose_device(torch: Any, requested: str) -> str:
    if requested != "auto":
        return requested
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def has_loop(text: str) -> bool:
    words = re.findall(r"[\w\u0900-\u097F]{3,}", text.lower())
    if len(words) < 20:
        return False
    for n in (3, 4, 5, 6):
        grams = [" ".join(words[i : i + n]) for i in range(0, len(words) - n + 1)]
        seen: dict[str, int] = {}
        for gram in grams:
            seen[gram] = seen.get(gram, 0) + 1
            if seen[gram] >= 4:
                return True
    return False


def score_case(case: dict[str, Any], answer: str) -> dict[str, Any]:
    blob = answer.lower()
    issues: list[str] = []
    hits = [t for t in case.get("must_any") or [] if t.lower() in blob or t in answer]
    if case.get("must_any") and not hits:
        issues.append("missing_any")
    for term in case.get("must_not") or []:
        if term.lower() in blob:
            issues.append(f"forbidden:{term}")
    if HINDI_RE.search(answer):
        issues.append("hindi_artifact")
    if REFUSAL_RE.search(answer) and "refusal_allowed" not in case:
        issues.append("refusal_marker")
    if MOJIBAKE_RE.search(answer):
        issues.append("mojibake")
    if has_loop(answer):
        issues.append("loop")
    if not answer.strip():
        issues.append("empty")
    return {
        "ok": not issues,
        "issues": issues,
        "must_hits": hits,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="google/gemma-4-E4B-it")
    ap.add_argument("--ckpt-root", type=Path, required=True)
    ap.add_argument("--checkpoints", default="step210,step270,step330,step420,best,step500,final")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--device", default="auto", choices=["auto", "cuda", "mps", "cpu"])
    ap.add_argument("--max-new-tokens", type=int, default=220)
    ap.add_argument("--repetition-penalty", type=float, default=1.05)
    ap.add_argument("--no-repeat-ngram-size", type=int, default=0)
    args = ap.parse_args()

    import torch  # type: ignore[import-not-found]
    from peft import PeftModel  # type: ignore[import-not-found]
    from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore[import-not-found]

    token = hf_token()
    device = choose_device(torch, args.device)
    dtype = torch.bfloat16 if device in {"cuda", "mps"} else torch.float32
    tokenizer = AutoTokenizer.from_pretrained(args.base, token=token)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
    if not getattr(tokenizer, "chat_template", None):
        from huggingface_hub import hf_hub_download  # type: ignore[import-not-found]

        tpl = hf_hub_download(args.base, "chat_template.jinja", token=token)
        tokenizer.chat_template = Path(tpl).read_text(encoding="utf-8")

    results: list[dict[str, Any]] = []
    checkpoints = [c.strip() for c in args.checkpoints.split(",") if c.strip()]
    for ckpt in checkpoints:
        adapter = args.ckpt_root / ckpt
        if not (adapter / "adapter_model.safetensors").exists():
            print(f"skip missing {adapter}", flush=True)
            continue
        t_load = time.time()
        print(f"loading {ckpt} on {device}", flush=True)
        base = AutoModelForCausalLM.from_pretrained(
            args.base,
            token=token,
            torch_dtype=dtype,
            device_map=device,
            attn_implementation="sdpa",
        )
        base.config.use_cache = True
        unwrapped = unwrap_gemma4_clippable_linears(base)
        model = PeftModel.from_pretrained(base, str(adapter), token=token)
        model.eval()
        load_ms = int((time.time() - t_load) * 1000)

        rows: list[dict[str, Any]] = []
        for case in CASES:
            messages = [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": case["prompt"]},
            ]
            prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            encoded = tokenizer(prompt, return_tensors="pt", add_special_tokens=False)
            input_ids = encoded["input_ids"].to(model.device)
            attention_mask = encoded["attention_mask"].to(model.device)
            kwargs: dict[str, Any] = {
                "input_ids": input_ids,
                "attention_mask": attention_mask,
                "max_new_tokens": args.max_new_tokens,
                "do_sample": False,
                "pad_token_id": tokenizer.pad_token_id or tokenizer.eos_token_id,
                "eos_token_id": tokenizer.eos_token_id,
            }
            if args.repetition_penalty != 1.0:
                kwargs["repetition_penalty"] = args.repetition_penalty
            if args.no_repeat_ngram_size > 0:
                kwargs["no_repeat_ngram_size"] = args.no_repeat_ngram_size
            t_gen = time.time()
            with torch.inference_mode():
                out = model.generate(**kwargs)
            elapsed_ms = int((time.time() - t_gen) * 1000)
            answer = tokenizer.decode(out[0, input_ids.shape[1] :], skip_special_tokens=True).strip()
            scored = score_case(case, answer)
            row = {
                "id": case["id"],
                "prompt": case["prompt"],
                "answer": answer,
                "elapsed_ms": elapsed_ms,
                "chars": len(answer),
                **scored,
            }
            rows.append(row)
            status = "OK" if row["ok"] else "FAIL"
            print(f"{ckpt} {status} {case['id']} {','.join(row['issues'])}", flush=True)

        results.append(
            {
                "checkpoint": ckpt,
                "adapter": str(adapter),
                "base": args.base,
                "device": device,
                "load_ms": load_ms,
                "unwrapped": unwrapped,
                "pass": sum(1 for r in rows if r["ok"]),
                "total": len(rows),
                "avg_gen_ms": int(sum(r["elapsed_ms"] for r in rows) / max(1, len(rows))),
                "max_gen_ms": max((r["elapsed_ms"] for r in rows), default=0),
                "rows": rows,
            }
        )
        del model
        del base
        if device == "cuda":
            torch.cuda.empty_cache()
        elif device == "mps":
            torch.mps.empty_cache()

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"cases": CASES, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
