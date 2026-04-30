#!/usr/bin/env python3
"""Comprehensive SFT v1 eval — runs after a checkpoint to decide if it's
publishable / demoable / shippable.

Six parts:
  1. Full 167-item gold set (URL recall + refusal correctness + chrF) — the
     primary metric. Reuses eval_groundedness helpers.
  2. LLM-as-judge groundedness on a 50-item subset, scored by DeepSeek V4-Flash.
     Catches the "high chrF but factually wrong" case the surface metrics miss.
  3. Belebele 50 (Nepali MC reading) — regression vs. base Gemma 4 IT.
  4. GSM8K-en 30 — English replay regression check (catastrophic forgetting).
  5. Roman-NE degen 10 — repetition / language-switch / mojibake detection.
  6. Side-by-side: 10 grounded items, baseline-vs-SFT, written to markdown
     for human review + a DeepSeek pairwise verdict.

The HF-transformers backend loads the base Gemma 4 IT model + a PEFT LoRA
adapter and exposes `chat(system, user)` so existing eval logic just works.

Output:
  eval/reports/<label>/full_gold.json
  eval/reports/<label>/llm_judge.json
  eval/reports/<label>/belebele.json
  eval/reports/<label>/gsm8k.json
  eval/reports/<label>/roman_ne.json
  eval/reports/<label>/side_by_side.md
  eval/reports/<label>/SUMMARY.md     (one-page summary, the demoability call)

Usage:
  # Full eval of an SFT adapter
  python scripts/eval_sft_v1.py \
      --base mlx-community/gemma-4-e4b-it-bf16 \
      --adapter checkpoints/sft_v1/seed42/best \
      --label sft_v1_seed42_best

  # Baseline (no adapter)
  python scripts/eval_sft_v1.py \
      --base mlx-community/gemma-4-e4b-it-bf16 \
      --no-adapter \
      --label gemma4_baseline

  # Skip parts (e.g. fast iteration)
  python scripts/eval_sft_v1.py ... --skip belebele,gsm8k,judge

The script imports from eval_groundedness.py — keep them next to each other.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import re
import sys
import time
from collections import Counter
from pathlib import Path

# Reuse existing primitives. eval_groundedness lives next door.
sys.path.insert(0, str(Path(__file__).parent))
from eval_groundedness import (  # noqa: E402
    SYSTEM_PROMPT,
    AnthropicShapeBackend,
    aggregate as ground_aggregate,
    eval_one as ground_eval_one,
    load_gold,
)


# ---- Gemma 4 PEFT-compatibility shim ---------------------------------------


def _unwrap_gemma4_clippable_linears(model) -> int:
    """Replace `Gemma4ClippableLinear` wrappers with their inner `nn.Linear`.

    Mirrors the same function in train_sft_v1.py — Gemma 4 wraps every Linear
    in a custom clipping module that PEFT doesn't recognise. We unwrap before
    LoRA injection / adapter loading.
    """
    import torch.nn as nn  # type: ignore[import-not-found]

    n_replaced = 0
    for parent in list(model.modules()):
        for child_name, child in list(parent.named_children()):
            if type(child).__name__ == "Gemma4ClippableLinear":
                inner = getattr(child, "linear", None)
                if isinstance(inner, nn.Linear):
                    setattr(parent, child_name, inner)
                    n_replaced += 1
    return n_replaced


# ---- HF transformers backend (loads on demand) -----------------------------


class HFTransformersBackend:
    """Loads base Gemma 4 IT + (optional) PEFT LoRA adapter via HF transformers.

    Single GPU, BF16. Lazy-imports torch/transformers/peft so non-eval
    invocations don't pay the import cost. `chat(system, user)` mirrors the
    Anthropic-shape backend so existing eval_groundedness logic just works.
    """

    def __init__(
        self,
        base_model_id: str,
        adapter_path: str | None,
        max_new_tokens: int = 800,
        device: str = "cuda",
        torch_dtype: str = "bfloat16",
        chat_template_repo_id: str | None = None,
    ):
        import torch  # type: ignore[import-not-found]
        from transformers import AutoModelForCausalLM, AutoTokenizer  # type: ignore[import-not-found]

        self.base_model_id = base_model_id
        self.adapter_path = adapter_path
        self.max_new_tokens = max_new_tokens
        self.label = (
            f"hf:{base_model_id}+{adapter_path}" if adapter_path else f"hf:{base_model_id}"
        )

        dtype = getattr(torch, torch_dtype)
        logging.info("loading tokenizer %s …", base_model_id)
        self.tokenizer = AutoTokenizer.from_pretrained(base_model_id, trust_remote_code=True)
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        # Gemma 4 ships its chat template in a separate `chat_template.jinja`
        # file (HF transformers issue #45205). If the tokenizer didn't pick
        # it up, fetch and inject manually.
        if not self.tokenizer.chat_template:
            tpl_repo = chat_template_repo_id or base_model_id
            try:
                from huggingface_hub import hf_hub_download  # type: ignore[import-not-found]
                tpl_path = hf_hub_download(
                    repo_id=tpl_repo,
                    filename="chat_template.jinja",
                    token=os.environ.get("HF_TOKEN"),
                )
                self.tokenizer.chat_template = Path(tpl_path).read_text(encoding="utf-8")
                logging.info("injected chat_template.jinja from %s", tpl_repo)
            except Exception as e:
                logging.warning(
                    "failed to fetch chat_template.jinja from %s (%s); "
                    "messages may format incorrectly", tpl_repo, e,
                )

        logging.info("loading base model %s (%s) …", base_model_id, torch_dtype)
        t0 = time.time()
        self.model = AutoModelForCausalLM.from_pretrained(
            base_model_id,
            torch_dtype=dtype,
            device_map=device,
            trust_remote_code=True,
        )
        logging.info("base model loaded in %.1fs", time.time() - t0)

        if adapter_path:
            # Same Gemma 4 quirk as the trainer: PEFT can't inject into the
            # `Gemma4ClippableLinear` wrappers, so we unwrap them to plain
            # `nn.Linear` before loading the adapter. The adapter was trained
            # against this same unwrapped structure (the trainer does it too).
            n_unwrapped = _unwrap_gemma4_clippable_linears(self.model)
            if n_unwrapped:
                logging.info(
                    "unwrapped %d Gemma4ClippableLinear → nn.Linear before adapter load",
                    n_unwrapped,
                )
            from peft import PeftModel  # type: ignore[import-not-found]
            logging.info("loading adapter %s …", adapter_path)
            t0 = time.time()
            self.model = PeftModel.from_pretrained(self.model, adapter_path)
            self.model.eval()
            logging.info("adapter loaded in %.1fs", time.time() - t0)
        else:
            self.model.eval()

        self.device = next(self.model.parameters()).device
        logging.info("backend ready on %s", self.device)

    def chat(self, system: str, user: str, max_tokens: int | None = None) -> str:
        import torch  # type: ignore[import-not-found]

        max_new = max_tokens if max_tokens is not None else self.max_new_tokens
        msgs: list[dict] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.append({"role": "user", "content": user})
        # Format to text first, then encode. apply_chat_template(tokenize=True)
        # has version-dependent return shapes (tensor / dict / list) and
        # sometimes returns a dict where `.to(device)` fails. Going through
        # text + encode is robust across HF versions.
        prompt_text = self.tokenizer.apply_chat_template(
            msgs, tokenize=False, add_generation_prompt=True
        )
        encoded = self.tokenizer(prompt_text, return_tensors="pt", add_special_tokens=False)
        prompt_ids = encoded["input_ids"].to(self.device)
        attention_mask = encoded["attention_mask"].to(self.device)
        with torch.no_grad():
            out_ids = self.model.generate(
                prompt_ids,
                attention_mask=attention_mask,
                max_new_tokens=max_new,
                do_sample=False,
                temperature=1.0,
                pad_token_id=self.tokenizer.pad_token_id or self.tokenizer.eos_token_id,
                eos_token_id=self.tokenizer.eos_token_id,
            )
        new_ids = out_ids[0, prompt_ids.size(1) :]
        text = self.tokenizer.decode(new_ids, skip_special_tokens=True)
        return text.strip()


# ---- DeepSeek judge backend (Anthropic-shape) ------------------------------


def _deepseek_backend() -> AnthropicShapeBackend:
    """Read DeepSeek key from ~/.fmw/deepseek (or env var) and return
    an AnthropicShapeBackend pointed at DeepSeek's anthropic-compat endpoint.

    Token resolution order:
      1. $DEEPSEEK_API_KEY
      2. ~/.fmw/deepseek (single-line file)
      3. ~/.config/brush/brush.json provider id "deepseek"
    """
    base_url = os.environ.get(
        "DEEPSEEK_BASE_URL", "https://api.deepseek.com/anthropic"
    )
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        fmw_path = Path.home() / ".fmw" / "deepseek"
        if fmw_path.exists():
            key = fmw_path.read_text().strip()
    if not key:
        brush_path = Path.home() / ".config" / "brush" / "brush.json"
        if brush_path.exists():
            cfg = json.loads(brush_path.read_text())
            prov = cfg.get("providers", {}).get("deepseek")
            if prov:
                key = prov.get("api_key")
                base_url = prov.get("base_url", base_url)
    if not key:
        raise RuntimeError(
            "DeepSeek API key not found. Set $DEEPSEEK_API_KEY, write to "
            "~/.fmw/deepseek, or add to ~/.config/brush/brush.json"
        )
    return AnthropicShapeBackend(
        base_url=base_url,
        api_key=key,
        model_id=os.environ.get("DEEPSEEK_JUDGE_MODEL", "deepseek-v4-flash"),
        label="deepseek-judge",
    )


# ---- Part 1: full 167 gold -------------------------------------------------


def run_full_gold(
    backend, gold_path: Path, out_path: Path, limit: int = 0
) -> dict:
    """Run model on all gold items, score, write report. Returns summary."""
    items = load_gold(gold_path)
    if limit > 0:
        items = items[:limit]

    type_counts = Counter(r["type"] for r in items)
    logging.info("[full-gold] %d items %s", len(items), dict(type_counts))

    results: list[dict] = []
    t0 = time.time()
    for i, item in enumerate(items, 1):
        res = ground_eval_one(item, backend)
        results.append(res)
        if i % 10 == 0 or i == len(items):
            n_err = sum(1 for r in results if r.get("error"))
            logging.info(
                "[full-gold] %d/%d err=%d (%.1fs)", i, len(items), n_err, time.time() - t0
            )

    summary = ground_aggregate(results)
    summary["wall_seconds"] = round(time.time() - t0, 1)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results}, f, ensure_ascii=False, indent=2)
    logging.info("[full-gold] wrote %s", out_path)
    return summary


# ---- Part 2: LLM-as-judge groundedness --------------------------------------


JUDGE_SYSTEM = """\
You are an expert evaluator for a Nepal-government helpdesk. Score the model's \
answer against the question, the gold answer, and the available source chunks. \
Return JSON only — no prose."""


JUDGE_USER_TEMPLATE = """\
Question:
{question}

Available source chunks:
{chunks}

Gold (reference) answer:
{gold}

Model's answer:
{model_answer}

Score the model's answer (integers 1-5):
- groundedness: every factual claim cited from the sources? (5=all cited, 1=fabricated)
- citation_correctness: cited URLs match the source list? (5=all match, 1=fabricated)
- helpfulness: actually answers the user's question? (5=perfect, 1=nothing useful)

Verdict: one of CORRECT, PARTIAL, INCORRECT.

Reply with JSON only:
{{"groundedness": 1-5, "citation_correctness": 1-5, "helpfulness": 1-5, "verdict": "CORRECT"|"PARTIAL"|"INCORRECT", "reason": "one short sentence"}}
"""


def _format_chunks_for_judge(chunks: list, max_chunks: int = 5, max_chars: int = 800) -> str:
    if not chunks:
        return "(no candidate sources)"
    parts = []
    for i, c in enumerate(chunks[:max_chunks], 1):
        url = c.get("url", "")
        text = (c.get("text") or "")[:max_chars]
        parts.append(f"[{i}] {url}\n{text}")
    return "\n\n".join(parts)


def _parse_judge_response(text: str) -> dict | None:
    """Try to find a JSON object in the judge's response. Returns None on parse fail."""
    if not text:
        return None
    # Try the easy cases first.
    text = text.strip()
    # Strip code fences.
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Fallback: regex out the JSON object.
    m = re.search(r"\{[^{}]*\}", text, flags=re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return None


def run_llm_judge(
    full_gold_results: list[dict],
    gold_items_by_id: dict[str, dict],
    judge_backend,
    out_path: Path,
    n_subset: int = 50,
    seed: int = 42,
) -> dict:
    """Pick a subset of grounded results, ask DeepSeek to score them."""
    grounded = [r for r in full_gold_results if r.get("type") == "grounded" and not r.get("error")]
    if not grounded:
        logging.warning("[judge] no grounded results to score")
        return {"n": 0, "skipped": "no grounded results"}
    rng = random.Random(seed)
    rng.shuffle(grounded)
    sample = grounded[: min(n_subset, len(grounded))]

    judge_results: list[dict] = []
    t0 = time.time()
    for i, r in enumerate(sample, 1):
        gold_item = gold_items_by_id.get(r["id"])
        if not gold_item:
            continue
        chunks = gold_item.get("candidate_chunks") or []
        user_prompt = JUDGE_USER_TEMPLATE.format(
            question=gold_item["question"],
            chunks=_format_chunks_for_judge(chunks),
            gold=r.get("gold_answer", "")[:1500],
            model_answer=r.get("model_output", "")[:1500],
        )
        try:
            resp = judge_backend.chat(JUDGE_SYSTEM, user_prompt, max_tokens=400)
        except Exception as e:
            judge_results.append({"id": r["id"], "error": f"{type(e).__name__}: {str(e)[:200]}"})
            continue
        parsed = _parse_judge_response(resp)
        if parsed is None:
            judge_results.append({"id": r["id"], "error": "parse_fail", "raw": resp[:300]})
            continue
        judge_results.append(
            {
                "id": r["id"],
                "category": r.get("category"),
                "lang": r.get("lang"),
                "groundedness": parsed.get("groundedness"),
                "citation_correctness": parsed.get("citation_correctness"),
                "helpfulness": parsed.get("helpfulness"),
                "verdict": parsed.get("verdict"),
                "reason": parsed.get("reason"),
            }
        )
        if i % 10 == 0 or i == len(sample):
            logging.info("[judge] %d/%d (%.1fs)", i, len(sample), time.time() - t0)

    valid = [j for j in judge_results if not j.get("error")]
    summary: dict = {
        "n": len(valid),
        "n_errors": len(judge_results) - len(valid),
    }
    if valid:
        for k in ("groundedness", "citation_correctness", "helpfulness"):
            vs = [j[k] for j in valid if isinstance(j.get(k), (int, float))]
            summary[k + "_mean"] = sum(vs) / len(vs) if vs else None
        verdicts = Counter(j.get("verdict") for j in valid if j.get("verdict"))
        summary["verdicts"] = dict(verdicts)
        n_correct = verdicts.get("CORRECT", 0)
        summary["correct_pct"] = 100 * n_correct / len(valid) if valid else 0

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": judge_results}, f, ensure_ascii=False, indent=2)
    logging.info("[judge] wrote %s", out_path)
    return summary


# ---- Part 3: Belebele 50 ---------------------------------------------------


BELEBELE_SYSTEM = ""  # MC task; no system prompt
BELEBELE_USER_TEMPLATE = (
    "Read the passage in Nepali and answer the question by choosing the "
    "single best option (A, B, C, or D). Reply with only the letter.\n\n"
    "Passage: {passage}\n\n"
    "Question: {question}\n\n"
    "A) {a}\nB) {b}\nC) {c}\nD) {d}\n\nAnswer:"
)


def run_belebele(backend, out_path: Path, n: int = 50, seed: int = 42) -> dict:
    try:
        from datasets import load_dataset  # type: ignore[import-not-found]
    except ImportError:
        return {"skipped": "datasets not installed"}
    rng = random.Random(seed)
    logging.info("[belebele] loading npi_Deva test split …")
    ds = load_dataset(
        "facebook/belebele", "npi_Deva", split="test", token=os.environ.get("HF_TOKEN")
    )
    idxs = rng.sample(range(len(ds)), min(n, len(ds)))
    correct = 0
    items: list[dict] = []
    t0 = time.time()
    for i, idx in enumerate(idxs, 1):
        ex = ds[idx]
        prompt = BELEBELE_USER_TEMPLATE.format(
            passage=ex["flores_passage"],
            question=ex["question"],
            a=ex["mc_answer1"],
            b=ex["mc_answer2"],
            c=ex["mc_answer3"],
            d=ex["mc_answer4"],
        )
        try:
            resp = backend.chat(BELEBELE_SYSTEM, prompt, max_tokens=20)
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
            logging.info("[belebele] %d/%d acc=%.2f (%.1fs)", i, len(idxs), correct / i, time.time() - t0)

    summary = {
        "n": len(idxs),
        "correct": correct,
        "accuracy": round(correct / max(1, len(idxs)), 4),
        "elapsed_sec": round(time.time() - t0, 1),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump({"summary": summary, "items": items}, f, ensure_ascii=False, indent=2)
    logging.info("[belebele] wrote %s", out_path)
    return summary


# ---- Part 4: GSM8K-en 30 (English replay regression) -----------------------


GSM8K_SYSTEM = ""
GSM8K_USER_TEMPLATE = (
    "Solve the following grade-school math problem. After showing your "
    "reasoning, conclude with a line of the form: '#### <number>' where "
    "<number> is the final numerical answer.\n\n"
    "Problem: {q}\n\nSolution:"
)


def _gsm8k_extract_answer(text: str) -> str | None:
    if not text:
        return None
    # Standard GSM8K format: '#### <number>'
    m = re.search(r"####\s*([-\d,\.]+)", text)
    if m:
        return m.group(1).replace(",", "").rstrip(".")
    # Fallback: last number in the text.
    nums = re.findall(r"[-]?\d[\d,]*\.?\d*", text)
    if nums:
        return nums[-1].replace(",", "").rstrip(".")
    return None


def _gsm8k_normalize(s: str | None) -> str | None:
    if s is None:
        return None
    try:
        return str(int(float(s)))
    except (ValueError, TypeError):
        return s.strip()


def run_gsm8k(backend, out_path: Path, n: int = 30, seed: int = 42) -> dict:
    try:
        from datasets import load_dataset  # type: ignore[import-not-found]
    except ImportError:
        return {"skipped": "datasets not installed"}
    rng = random.Random(seed)
    logging.info("[gsm8k] loading main/test split …")
    ds = load_dataset("openai/gsm8k", "main", split="test", token=os.environ.get("HF_TOKEN"))
    idxs = rng.sample(range(len(ds)), min(n, len(ds)))
    correct = 0
    items: list[dict] = []
    t0 = time.time()
    for i, idx in enumerate(idxs, 1):
        ex = ds[idx]
        gold_str = ex["answer"].split("####")[-1].strip().replace(",", "")
        gold = _gsm8k_normalize(gold_str)
        prompt = GSM8K_USER_TEMPLATE.format(q=ex["question"])
        try:
            resp = backend.chat(GSM8K_SYSTEM, prompt, max_tokens=400)
        except Exception as e:
            items.append({"idx": idx, "error": f"{type(e).__name__}: {str(e)[:120]}"})
            continue
        pred = _gsm8k_normalize(_gsm8k_extract_answer(resp))
        ok = pred is not None and pred == gold
        if ok:
            correct += 1
        items.append({"idx": idx, "gold": gold, "pred": pred, "ok": ok, "resp": resp[:200]})
        if i % 10 == 0 or i == len(idxs):
            logging.info("[gsm8k] %d/%d acc=%.2f (%.1fs)", i, len(idxs), correct / i, time.time() - t0)

    summary = {
        "n": len(idxs),
        "correct": correct,
        "accuracy": round(correct / max(1, len(idxs)), 4),
        "elapsed_sec": round(time.time() - t0, 1),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump({"summary": summary, "items": items}, f, ensure_ascii=False, indent=2)
    logging.info("[gsm8k] wrote %s", out_path)
    return summary


# ---- Part 5: Roman-NE degeneration check -----------------------------------


ROMAN_PROMPTS = [
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

# A token mixing Latin and Devanagari letters with no boundary is mojibake
# (e.g., "bhएको", "kaहाँ"). Real Devanagari and Roman never co-occur within
# a single word in correct output.
MOJIBAKE_RE = re.compile(r"[A-Za-z][ऀ-ॿ]|[ऀ-ॿ][A-Za-z]")


def _detect_repetition_loop(text: str) -> bool:
    if not text.strip():
        return True
    words = text.split()
    if len(words) < 5:
        return False
    # Repeating same 5-word phrase >=3 times is a loop.
    first_5 = " ".join(words[:5])
    rest = text[len(first_5) :]
    if rest.count(first_5) >= 3:
        return True
    # Or any 3-token sub-sequence repeating >=4 times.
    from collections import Counter as C
    triples = [" ".join(words[i : i + 3]) for i in range(len(words) - 2)]
    if triples:
        most = C(triples).most_common(1)[0]
        if most[1] >= 4:
            return True
    return False


def run_roman_ne(backend, out_path: Path) -> dict:
    items: list[dict] = []
    n_degen = 0
    n_mojibake = 0
    n_loop = 0
    n_empty = 0
    t0 = time.time()
    # Use the SFT system prompt — these prompts arrive without retrieved chunks
    # but the model should still try to answer (or refuse cleanly).
    for i, p in enumerate(ROMAN_PROMPTS, 1):
        try:
            resp = backend.chat(SYSTEM_PROMPT, f"Question: {p}\n\nSources:\n(no candidate sources surfaced)", max_tokens=300)
        except Exception as e:
            items.append({"q": p, "error": f"{type(e).__name__}: {str(e)[:120]}"})
            n_degen += 1
            continue
        is_loop = _detect_repetition_loop(resp)
        is_moj = bool(MOJIBAKE_RE.search(resp))
        is_empty = not resp.strip()
        if is_loop:
            n_loop += 1
        if is_moj:
            n_mojibake += 1
        if is_empty:
            n_empty += 1
        if is_loop or is_moj or is_empty:
            n_degen += 1
        items.append(
            {
                "q": p,
                "a": resp,
                "loop": is_loop,
                "mojibake": is_moj,
                "empty": is_empty,
            }
        )
        logging.info("[roman-ne] %d/%d", i, len(ROMAN_PROMPTS))

    summary = {
        "n": len(ROMAN_PROMPTS),
        "n_degen": n_degen,
        "n_loop": n_loop,
        "n_mojibake": n_mojibake,
        "n_empty": n_empty,
        "elapsed_sec": round(time.time() - t0, 1),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        json.dump({"summary": summary, "items": items}, f, ensure_ascii=False, indent=2)
    logging.info("[roman-ne] wrote %s", out_path)
    return summary


# ---- Part 6: side-by-side baseline-vs-SFT ----------------------------------


PAIRWISE_SYSTEM = (
    "You are an expert evaluator. Compare two answers (A vs B) to a "
    "Nepal-gov-helpdesk question. Pick the one that is more grounded, more "
    "helpful, and matches the gold better. Reply with JSON only."
)
PAIRWISE_USER_TEMPLATE = """\
Question:
{question}

Sources available:
{chunks}

Gold (reference) answer:
{gold}

Answer A:
{a}

Answer B:
{b}

Pick the better answer. Reply JSON only:
{{"winner": "A"|"B"|"TIE", "reason": "one short sentence"}}
"""


def _pairwise_judge(judge_backend, question: str, chunks: list, gold: str, a: str, b: str) -> dict:
    user = PAIRWISE_USER_TEMPLATE.format(
        question=question,
        chunks=_format_chunks_for_judge(chunks),
        gold=gold[:1500],
        a=a[:1500],
        b=b[:1500],
    )
    try:
        resp = judge_backend.chat(PAIRWISE_SYSTEM, user, max_tokens=200)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:200]}"}
    parsed = _parse_judge_response(resp)
    return parsed or {"error": "parse_fail", "raw": resp[:300]}


def run_side_by_side(
    baseline_label: str,
    full_gold_results: list[dict],
    gold_items_by_id: dict[str, dict],
    judge_backend,
    out_path: Path,
    n: int = 10,
    seed: int = 42,
) -> dict:
    """Pick 10 grounded items, compare SFT answers (already in full_gold_results)
    against a previously saved baseline. Writes a markdown file for human
    review + a DeepSeek pairwise verdict.

    The "baseline" answers come from a prior eval report we read from
    eval/reports/<baseline_label>.json (e.g. sonnet-4-6-baseline or
    gemma4_baseline). If no such file, we skip baseline and just dump SFT
    outputs.
    """
    grounded = [r for r in full_gold_results if r.get("type") == "grounded" and not r.get("error")]
    if not grounded:
        return {"n": 0, "skipped": "no grounded results"}
    rng = random.Random(seed)
    rng.shuffle(grounded)
    sample = grounded[: min(n, len(grounded))]

    baseline_path = Path(f"eval/reports/{baseline_label}.json")
    baseline_by_id: dict[str, dict] = {}
    if baseline_path.exists():
        try:
            data = json.loads(baseline_path.read_text())
            for r in data.get("results", []):
                baseline_by_id[r["id"]] = r
            logging.info("[side-by-side] loaded baseline %s (%d items)", baseline_path, len(baseline_by_id))
        except Exception as e:
            logging.warning("[side-by-side] failed to load baseline %s: %s", baseline_path, e)
    else:
        logging.warning("[side-by-side] baseline file %s not found — skipping pairwise judge", baseline_path)

    sft_results: list[dict] = []
    pairwise: list[dict] = []
    md_lines: list[str] = [f"# Side-by-side: SFT vs {baseline_label}\n"]
    for i, r in enumerate(sample, 1):
        gold_item = gold_items_by_id.get(r["id"])
        if not gold_item:
            continue
        sft_answer = r["model_output"]
        sft_results.append({"id": r["id"], "model_output": sft_answer})
        baseline_r = baseline_by_id.get(r["id"]) or {}
        baseline_answer = baseline_r.get("model_output", "")

        md_lines.append(f"\n---\n\n## {i}. {r['id']}  (`{r.get('category')}` / `{r.get('lang')}`)\n")
        md_lines.append(f"**Question**: {gold_item['question']}\n")
        md_lines.append(f"\n### Gold\n```\n{r.get('gold_answer', '')[:600]}\n```\n")
        md_lines.append(f"\n### Baseline ({baseline_label})\n```\n{baseline_answer[:600]}\n```\n")
        md_lines.append(f"\n### SFT\n```\n{sft_answer[:600]}\n```\n")

        if baseline_answer and judge_backend is not None:
            verdict = _pairwise_judge(
                judge_backend,
                gold_item["question"],
                gold_item.get("candidate_chunks") or [],
                r.get("gold_answer", ""),
                a=baseline_answer,
                b=sft_answer,
            )
            pairwise.append({"id": r["id"], "baseline_label": baseline_label, **verdict})
            md_lines.append(f"\n**DeepSeek pairwise verdict**: `{verdict.get('winner', verdict.get('error', '?'))}`")
            if verdict.get("reason"):
                md_lines.append(f" — {verdict['reason']}\n")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(md_lines), encoding="utf-8")
    json_path = out_path.with_suffix(".json")
    json_path.write_text(
        json.dumps({"sft_results": sft_results, "pairwise": pairwise}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logging.info("[side-by-side] wrote %s + %s", out_path, json_path)

    summary: dict = {"n": len(sample), "n_pairwise": len(pairwise)}
    if pairwise:
        valid = [p for p in pairwise if not p.get("error")]
        if valid:
            winners = Counter(p.get("winner") for p in valid)
            summary["winners"] = dict(winners)
            sft_wins = winners.get("B", 0)
            ties = winners.get("TIE", 0)
            summary["sft_winrate_pct"] = round(100 * (sft_wins + 0.5 * ties) / len(valid), 1)
    return summary


# ---- Pass/fail gates and SUMMARY.md ----------------------------------------


def write_summary_markdown(
    label: str,
    out_path: Path,
    full_gold: dict,
    judge: dict,
    belebele: dict,
    gsm8k: dict,
    roman: dict,
    side_by_side: dict,
    args,
) -> None:
    """One-page summary: the demoability call. Compares against published
    Sonnet baseline (URL recall 84%, refusal correct 99%, hallucinated 1%)
    and the Gemma 4 IT baseline numbers."""
    lines: list[str] = [f"# SFT v1 Eval Summary — {label}\n"]
    lines.append(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append(f"Base: `{args.base}`")
    lines.append(f"Adapter: `{args.adapter or 'NONE (baseline)'}`\n")

    def fmt(v, fmt_str=".2f"):
        if v is None:
            return "n/a"
        if isinstance(v, float):
            return f"{v:{fmt_str}}"
        return str(v)

    # 1. Full gold
    lines.append("\n## 1. Full Gold (167 items)")
    bt = full_gold.get("by_type", {})
    g = bt.get("grounded", {})
    rf = bt.get("refusal", {})
    lines.append(f"- grounded n={g.get('n', 0)}  chrF={fmt(g.get('chrf_mean'))}  url_recall={fmt(g.get('url_recall_mean'))}  wrongly_refused={g.get('wrongly_refused', '?')}  ({fmt(g.get('wrongly_refused_pct'), '.1f')}%)")
    lines.append(f"- refusal  n={rf.get('n', 0)}  correct_pct={fmt(rf.get('correct_pct'), '.1f')}%  hallucinated={rf.get('hallucinated', '?')}")

    # 2. LLM judge
    lines.append("\n## 2. LLM-as-judge (DeepSeek)")
    if judge.get("n"):
        lines.append(f"- n={judge['n']}")
        lines.append(f"- groundedness mean: {fmt(judge.get('groundedness_mean'))}/5")
        lines.append(f"- citation_correctness mean: {fmt(judge.get('citation_correctness_mean'))}/5")
        lines.append(f"- helpfulness mean: {fmt(judge.get('helpfulness_mean'))}/5")
        lines.append(f"- correct%: {fmt(judge.get('correct_pct'), '.1f')}%")
        lines.append(f"- verdicts: {judge.get('verdicts', {})}")
    else:
        lines.append(f"- skipped: {judge.get('skipped', 'no data')}")

    # 3. Belebele
    lines.append("\n## 3. Belebele (50 NE MC) — regression check")
    if "accuracy" in belebele:
        lines.append(f"- accuracy: {belebele['accuracy'] * 100:.1f}%  ({belebele['correct']}/{belebele['n']})")
        lines.append("- Gemma 4 IT baseline: see `eval/gemma3_nepali_baseline.md`")
    else:
        lines.append(f"- skipped: {belebele.get('skipped', 'unknown')}")

    # 4. GSM8K
    lines.append("\n## 4. GSM8K-en (30) — English replay regression")
    if "accuracy" in gsm8k:
        lines.append(f"- accuracy: {gsm8k['accuracy'] * 100:.1f}%  ({gsm8k['correct']}/{gsm8k['n']})")
    else:
        lines.append(f"- skipped: {gsm8k.get('skipped', 'unknown')}")

    # 5. Roman-NE degen
    lines.append("\n## 5. Roman-NE qualitative (10 prompts)")
    lines.append(f"- n_degen: {roman.get('n_degen', '?')}/{roman.get('n', 10)}")
    lines.append(f"- loops: {roman.get('n_loop', '?')}, mojibake: {roman.get('n_mojibake', '?')}, empty: {roman.get('n_empty', '?')}")
    lines.append("- target: ≤1 degen (was 3 with base Gemma 4 IT)")

    # 6. Side-by-side
    lines.append("\n## 6. Side-by-side vs baseline")
    if side_by_side.get("n_pairwise"):
        lines.append(f"- pairwise judged: {side_by_side['n_pairwise']}")
        lines.append(f"- SFT win-rate: {fmt(side_by_side.get('sft_winrate_pct'), '.1f')}%")
        lines.append(f"- winners: {side_by_side.get('winners', {})}")
    else:
        lines.append(f"- skipped: {side_by_side.get('skipped', 'no baseline file')}")

    # Pass/fail call
    lines.append("\n## Demoability call")
    pass_signals: list[str] = []
    fail_signals: list[str] = []
    if g.get("url_recall_mean") is not None:
        if g["url_recall_mean"] >= 0.7:
            pass_signals.append(f"url_recall {g['url_recall_mean']:.2f} ≥ 0.70")
        else:
            fail_signals.append(f"url_recall {g['url_recall_mean']:.2f} < 0.70")
    if rf.get("correct_pct") is not None:
        if rf["correct_pct"] >= 90:
            pass_signals.append(f"refusal_correct {rf['correct_pct']:.0f}% ≥ 90%")
        else:
            fail_signals.append(f"refusal_correct {rf['correct_pct']:.0f}% < 90%")
    if g.get("wrongly_refused_pct") is not None:
        if g["wrongly_refused_pct"] <= 10:
            pass_signals.append(f"wrongly_refused {g['wrongly_refused_pct']:.0f}% ≤ 10%")
        else:
            fail_signals.append(f"wrongly_refused {g['wrongly_refused_pct']:.0f}% > 10%")
    if "n_degen" in roman:
        if roman["n_degen"] <= 1:
            pass_signals.append(f"roman_degen {roman['n_degen']}/10 ≤ 1")
        else:
            fail_signals.append(f"roman_degen {roman['n_degen']}/10 > 1")
    if "accuracy" in belebele:
        if belebele["accuracy"] >= 0.55:
            pass_signals.append(f"belebele {belebele['accuracy']:.2f} ≥ 0.55")
        else:
            fail_signals.append(f"belebele {belebele['accuracy']:.2f} < 0.55")

    lines.append(f"\n**PASS signals**: {len(pass_signals)}\n")
    for s in pass_signals:
        lines.append(f"- ✓ {s}")
    lines.append(f"\n**FAIL signals**: {len(fail_signals)}\n")
    for s in fail_signals:
        lines.append(f"- ✗ {s}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    logging.info("wrote %s", out_path)


# ---- Main ------------------------------------------------------------------


PARTS = ["full_gold", "judge", "belebele", "gsm8k", "roman", "side_by_side"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="google/gemma-4-e4b-it", help="HF base model id (or repo path)")
    ap.add_argument("--adapter", default=None, help="PEFT adapter dir (omit for baseline)")
    ap.add_argument("--no-adapter", action="store_true", help="run baseline (no adapter)")
    ap.add_argument("--label", required=True, help="run label, used for the output dir")
    ap.add_argument("--out-root", default="eval/reports")
    ap.add_argument("--gold", default="eval/gov_helpdesk_gold_v1.jsonl")
    ap.add_argument("--limit", type=int, default=0, help="limit gold items (0 = all)")
    ap.add_argument("--judge-n", type=int, default=50)
    ap.add_argument("--belebele-n", type=int, default=50)
    ap.add_argument("--gsm8k-n", type=int, default=30)
    ap.add_argument("--side-by-side-n", type=int, default=10)
    ap.add_argument("--baseline-label", default="sonnet-4-6-baseline")
    ap.add_argument("--skip", default="", help="comma-separated parts to skip")
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--torch-dtype", default="bfloat16")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    bad = skip - set(PARTS)
    if bad:
        print(f"unknown skip parts: {bad}; valid: {PARTS}", file=sys.stderr)
        return 1

    if args.no_adapter:
        args.adapter = None

    out_dir = Path(args.out_root) / args.label
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load HF backend only if any model-using part is enabled. Skipping all of
    # them is useful when re-running just side-by-side from saved full_gold.json.
    needs_model = bool({"full_gold", "belebele", "gsm8k", "roman"} - skip)
    sft_backend = None
    if needs_model:
        sft_backend = HFTransformersBackend(
            base_model_id=args.base,
            adapter_path=args.adapter,
            device=args.device,
            torch_dtype=args.torch_dtype,
        )

    judge_backend = None
    if "judge" not in skip or "side_by_side" not in skip:
        try:
            judge_backend = _deepseek_backend()
            logging.info("DeepSeek judge backend ready")
        except Exception as e:
            logging.warning("DeepSeek judge unavailable (%s); skipping judge + pairwise", e)

    # ---- Run parts ----
    full_gold_summary: dict = {}
    full_gold_results: list[dict] = []
    gold_items_by_id: dict[str, dict] = {}

    if "full_gold" not in skip:
        # We need full_gold_results in memory for parts 2 + 6, so we re-read.
        gold_items = load_gold(Path(args.gold))
        if args.limit > 0:
            gold_items = gold_items[: args.limit]
        gold_items_by_id = {r["id"]: r for r in gold_items}

        full_gold_summary = run_full_gold(
            sft_backend, Path(args.gold), out_dir / "full_gold.json", limit=args.limit
        )
        # Reload the results from disk so downstream parts can use them.
        with (out_dir / "full_gold.json").open() as f:
            full_gold_results = json.load(f)["results"]
    else:
        # Load gold items only for downstream parts that need them.
        if "judge" not in skip or "side_by_side" not in skip:
            gold_items = load_gold(Path(args.gold))
            gold_items_by_id = {r["id"]: r for r in gold_items}
            existing = out_dir / "full_gold.json"
            if existing.exists():
                with existing.open() as f:
                    data = json.load(f)
                full_gold_results = data.get("results", [])
                full_gold_summary = data.get("summary", {})
                logging.info("[full-gold] reloaded existing %s", existing)

    judge_summary: dict = {}
    if "judge" not in skip and judge_backend and full_gold_results:
        judge_summary = run_llm_judge(
            full_gold_results,
            gold_items_by_id,
            judge_backend,
            out_dir / "llm_judge.json",
            n_subset=args.judge_n,
            seed=args.seed,
        )
    elif "judge" in skip:
        judge_summary = {"skipped": "user-requested"}
    else:
        judge_summary = {"skipped": "no judge backend or no gold results"}

    belebele_summary: dict = {}
    if "belebele" not in skip:
        belebele_summary = run_belebele(
            sft_backend, out_dir / "belebele.json", n=args.belebele_n, seed=args.seed
        )
    else:
        belebele_summary = {"skipped": "user-requested"}

    gsm8k_summary: dict = {}
    if "gsm8k" not in skip:
        gsm8k_summary = run_gsm8k(
            sft_backend, out_dir / "gsm8k.json", n=args.gsm8k_n, seed=args.seed
        )
    else:
        gsm8k_summary = {"skipped": "user-requested"}

    roman_summary: dict = {}
    if "roman" not in skip:
        roman_summary = run_roman_ne(sft_backend, out_dir / "roman_ne.json")
    else:
        roman_summary = {"skipped": "user-requested"}

    sbs_summary: dict = {}
    if "side_by_side" not in skip and full_gold_results:
        sbs_summary = run_side_by_side(
            args.baseline_label,
            full_gold_results,
            gold_items_by_id,
            judge_backend,
            out_dir / "side_by_side.md",
            n=args.side_by_side_n,
            seed=args.seed,
        )
    else:
        sbs_summary = {"skipped": "user-requested or no gold results"}

    # ---- Final SUMMARY.md ----
    write_summary_markdown(
        args.label,
        out_dir / "SUMMARY.md",
        full_gold_summary,
        judge_summary,
        belebele_summary,
        gsm8k_summary,
        roman_summary,
        sbs_summary,
        args,
    )

    print(f"\n=== eval done ===")
    print(f"  reports: {out_dir}/")
    print(f"  summary: {out_dir / 'SUMMARY.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
