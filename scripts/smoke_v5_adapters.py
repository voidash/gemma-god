#!/usr/bin/env python3
"""Small behavioral smoke test for Gemma helpdesk adapters.

This is intentionally not a full benchmark. It checks whether a checkpoint can
hold the SpeakGov navigator contract on representative prompts: follow-up
questions, source/contact orientation, non-Hindi language behavior, and
off-domain handling.
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
Do intake first. Ask compact follow-up questions when a service request is
ambiguous. Use plain English/Nepali/Roman Nepali matching the user. Do not
switch to Hindi. Give factual, source-aware guidance, useful contacts when
relevant, uncertainty, and next steps. If a question is outside government
services, answer briefly and say you are mainly built for Nepal government
services."""


PROMPTS = [
    {
        "id": "citizenship_sankhuwasabha",
        "text": "how to get citizenship in Sankhuwasabha?",
        "must": ["municipality", "ward", "case"],
    },
    {
        "id": "manpower_cheated",
        "text": "who to contact when i got cheated by manpower agency?",
        "must": ["foreign", "employment"],
    },
    {
        "id": "jiri_mayor_ne",
        "text": "जिरी नगरपालिकाको नगर प्रमुख को हुन्?",
        "must": ["जिरी"],
    },
    {
        "id": "jiri_birth_cert",
        "text": "birth certificate in Jiri",
        "must": ["birth", "ward"],
    },
    {
        "id": "qatar_passport_roman",
        "text": "ma Qatar ma chu passport renew garna paryo",
        "must": ["passport", "qatar"],
    },
    {
        "id": "offdomain_math",
        "text": "2 + 2 kati ho?",
        "must": ["4"],
    },
]


def _hf_token() -> str | None:
    if token := os.environ.get("HF_TOKEN"):
        return token
    fmw = Path.home() / ".fmw"
    if fmw.exists():
        for line in fmw.read_text().splitlines():
            if line.startswith("HF_TOKEN="):
                return line.split("=", 1)[1].strip()
    return None


def _unwrap_gemma4_clippable_linears(model) -> int:
    n = 0
    for parent in list(model.modules()):
        for child_name, child in list(parent.named_children()):
            if type(child).__name__ == "Gemma4ClippableLinear":
                inner = getattr(child, "linear", None)
                if inner is not None:
                    setattr(parent, child_name, inner)
                    n += 1
    return n


def _has_hindi(text: str) -> bool:
    hindi_terms = [
        "कृपया",
        "आप",
        "आपका",
        "है",
        "हैं",
        "करें",
        "सकते",
        "मैं",
        "नहीं",
        "यदि",
    ]
    return any(term in text for term in hindi_terms)


def _loop_score(text: str) -> int:
    chunks = re.findall(r"[\w\u0900-\u097F]{3,}", text.lower())
    if not chunks:
        return 0
    max_run = 1
    run = 1
    for prev, cur in zip(chunks, chunks[1:]):
        if prev == cur:
            run += 1
            max_run = max(max_run, run)
        else:
            run = 1
    return max_run


def _format_messages(tokenizer, user: str) -> Any:
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    text = tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
    return tokenizer(text, return_tensors="pt", add_special_tokens=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="google/gemma-4-E4B-it")
    ap.add_argument("--adapter", default="")
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-new-tokens", type=int, default=260)
    ap.add_argument("--load-in-4bit", action="store_true")
    args = ap.parse_args()

    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    token = _hf_token()
    tokenizer = AutoTokenizer.from_pretrained(args.base, token=token)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token_id = tokenizer.eos_token_id
    if not tokenizer.chat_template:
        from huggingface_hub import hf_hub_download

        tpl = hf_hub_download(args.base, "chat_template.jinja", token=token)
        tokenizer.chat_template = Path(tpl).read_text(encoding="utf-8")

    t0 = time.time()
    load_kwargs: dict[str, Any] = {
        "token": token,
        "torch_dtype": torch.bfloat16,
        "device_map": "cuda",
        "attn_implementation": "sdpa",
    }
    if args.load_in_4bit:
        load_kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )
    model = AutoModelForCausalLM.from_pretrained(args.base, **load_kwargs)
    model.config.use_cache = True
    unwrapped = _unwrap_gemma4_clippable_linears(model)
    if args.adapter:
        model = PeftModel.from_pretrained(model, args.adapter)
    model.eval()
    load_seconds = round(time.time() - t0, 2)

    rows = []
    for prompt in PROMPTS:
        encoded = _format_messages(tokenizer, prompt["text"])
        input_ids = encoded["input_ids"].to(model.device)
        attention_mask = encoded["attention_mask"].to(model.device)
        t1 = time.time()
        with torch.inference_mode():
            output = model.generate(
                input_ids=input_ids,
                attention_mask=attention_mask,
                max_new_tokens=args.max_new_tokens,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
        elapsed_ms = int((time.time() - t1) * 1000)
        text = tokenizer.decode(output[0, input_ids.shape[1] :], skip_special_tokens=True).strip()
        lower = text.lower()
        must_hits = [m for m in prompt["must"] if m.lower() in lower or m in text]
        rows.append(
            {
                "label": args.label,
                "adapter": args.adapter or None,
                "prompt_id": prompt["id"],
                "prompt": prompt["text"],
                "answer": text,
                "elapsed_ms": elapsed_ms,
                "chars": len(text),
                "must_hits": must_hits,
                "has_hindi": _has_hindi(text),
                "loop_score": _loop_score(text),
                "empty": not bool(text),
            }
        )

    report = {
        "label": args.label,
        "adapter": args.adapter or None,
        "base": args.base,
        "load_seconds": load_seconds,
        "unwrapped": unwrapped,
        "rows": rows,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
