#!/usr/bin/env python3
"""Synthesize brief conversational Q&A pairs (no chunks, no citations)
in three languages, with emphasis on Roman-Nepali, for SFT v2.

Why: SFT v1 had ~989 Roman-Nepali items in the grounded slice but they
all came in the format "Question: X\\n\\nSources: [chunks]" — the model
learned to expect chunks for every Roman-NE input. When eval prompts
arrived as short Roman-NE questions WITHOUT chunks ("passport renew
garna kaha janu parcha?"), the model degenerated into repetition loops.

This slice teaches: short conversational prompt without chunks → brief
helpful answer in matching language. ~50% Roman-NE focus to address the
specific degen issue, with smaller Devanagari + English buckets for
balance.

Topics are intentionally diverse and slightly *off* the gov-helpdesk core
so the model learns "general assistant" mode for non-grounded prompts:
weather small-talk, food/recipe questions, daily life, polite chit-chat,
study tips, basic explanations, etc.

Output schema:
    {
      "id": "sft_brief_qa_00001",
      "source": "brief_qa_distilled",
      "question": "<short question>",
      "question_lang": "...",
      "category": "brief_qa",
      "chunks": [],
      "answer": "<brief answer, 1-3 sentences>",
      "skip": false
    }

Usage:
    python scripts/synthesize_brief_qa.py --n 30   # smoke
    python scripts/synthesize_brief_qa.py --n 300  # full
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
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock


DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/anthropic")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
MAX_RETRIES = 3
TIMEOUT_S = 60


def _deepseek_key() -> str:
    if k := os.environ.get("DEEPSEEK_API_KEY"):
        return k
    fmw = Path.home() / ".fmw"
    if fmw.exists():
        for line in fmw.read_text().splitlines():
            if line.startswith("DEEPSEEK="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("DeepSeek API key not found")


def deepseek_chat(system: str, user: str, max_tokens: int = 2400, temperature: float = 0.85) -> str:
    payload = json.dumps({
        "model": DEEPSEEK_MODEL,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "thinking": {"type": "disabled"},
    }).encode("utf-8")
    api_key = _deepseek_key()
    last_err: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(
                f"{DEEPSEEK_BASE_URL}/v1/messages",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                data = json.loads(resp.read())
            parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
            return "".join(parts).strip()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            last_err = RuntimeError(f"HTTP {e.code}: {body[:200]}")
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            raise last_err
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
            last_err = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"deepseek failed: {last_err}")


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.M)


def _try_parse_json(text: str) -> dict | None:
    if not text:
        return None
    text = _FENCE_RE.sub("", text.strip()).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


_LANG_INSTR = {
    "devanagari":
        "Devanagari Nepali (देवनागरी) — both question and answer in Devanagari script. "
        "DO NOT use Roman letters.",
    "roman_nepali":
        "Roman-Nepali (Nepali in Latin script with English letters). Mix in some real Roman-NE words like "
        "'kasari', 'kun', 'kaha', 'ke', 'parcha', 'huncha', 'cha', 'chha', 'mero', 'tapai', 'hami'. "
        "Both Q and A in Roman script. Avoid pure English.",
    "english": "English — both question and answer.",
}


SYSTEM_GENERATOR = (
    "You generate brief, friendly conversational Q&A pairs for an LLM "
    "training set. Topics are everyday life, casual learning, opinions, "
    "small-talk — NOT government services, NOT formal documents. The "
    "answer should be conversational and brief (1-3 sentences), without "
    "citations or formal structure. Reply with JSON ONLY."
)


def build_prompt(lang: str, n_per_call: int) -> str:
    return f"""\
Generate exactly {n_per_call} brief, conversational Q&A pairs.

Language: {_LANG_INSTR[lang]}

Topics — mix of:
  - daily life questions ("What should I cook tonight?")
  - polite small-talk ("How is the weather?")
  - explanations ("What does X mean?")
  - opinions ("Which festival is your favorite?")
  - study/learning questions ("How can I improve my Nepali?")
  - food, travel, hobbies, family, weather, education
  - generally helpful but NOT government / legal / formal-document topics

Format:
  - Question: short, natural, like someone chatting (under 25 words)
  - Answer: brief, friendly, 1-3 sentences. Conversational tone.
  - NO citations, NO source URLs, NO "Sources:" header. This is casual chat.

Reply with JSON ONLY:
{{"pairs": [
  {{"question": "...", "answer": "..."}},
  ...
]}}

Diverse topics and phrasings — no two questions near-duplicates."""


# ---- Validation -----------------------------------------------------------


_DEVA_RE = re.compile(r"[ऀ-ॿ]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_ROMAN_NE_MARKERS = re.compile(
    r"\b(kasari|kun|kaha|ke|chha|cha|garna|garne|parcha|huncha|chaina|"
    r"hos|janu|garnu|hami|tapai|mero|tyo|yo|hoina|ho|nai|paryo|bhayo|"
    r"bhanne|bata|ma|sanga|lai|ko|ka|ki)\b",
    re.I,
)


def _validate_pair(pair: dict, expect_lang: str) -> tuple[bool, str]:
    q = (pair.get("question") or "").strip()
    a = (pair.get("answer") or "").strip()
    if not q or not a:
        return False, "missing"
    if len(q) < 8 or len(a) < 8:
        return False, "too short"
    if len(q) > 600 or len(a) > 1200:
        return False, "too long"
    text_blob = q + " " + a
    deva = len(_DEVA_RE.findall(text_blob))
    latin = len(_LATIN_RE.findall(text_blob))
    tot = deva + latin
    if tot == 0:
        return False, "no letters"
    if expect_lang == "devanagari":
        if deva / tot < 0.6:
            return False, "expected devanagari"
    elif expect_lang == "roman_nepali":
        if latin / tot < 0.7:
            return False, "expected roman script"
        if not _ROMAN_NE_MARKERS.search(text_blob):
            return False, "expected roman-NE markers"
    elif expect_lang == "english":
        if deva / tot > 0.05:
            return False, "expected english"
    return True, ""


def generate_batch(lang: str, n_per_call: int = 10) -> list[dict]:
    prompt = build_prompt(lang, n_per_call)
    try:
        resp = deepseek_chat(SYSTEM_GENERATOR, prompt, max_tokens=2400, temperature=0.9)
    except Exception as e:
        logging.warning("deepseek %s: %s", lang, str(e)[:120])
        return []
    parsed = _try_parse_json(resp)
    if not parsed or "pairs" not in parsed:
        logging.warning("parse fail %s: %s", lang, resp[:160])
        return []
    out: list[dict] = []
    for p in parsed["pairs"]:
        ok, why = _validate_pair(p, lang)
        if not ok:
            logging.debug("rejected (%s): %s", lang, why)
            continue
        out.append({"question": p["question"].strip(), "answer": p["answer"].strip()})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--output", default="corpora/sft_v2_brief_qa.jsonl")
    ap.add_argument("--n-per-call", type=int, default=10)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    # Roman-NE biased — that's the slice we're underweight on
    targets = {
        "roman_nepali": int(args.n * 0.50),
        "devanagari": int(args.n * 0.25),
        "english": int(args.n * 0.25),
    }
    total_target = sum(targets.values())
    logging.info("targets per lang: %s (total %d)", targets, total_target)

    bucket: dict[str, list[dict]] = {k: [] for k in targets}
    write_lock = Lock()
    n_calls = 0
    t0 = time.time()

    def call_for(lang):
        nonlocal n_calls
        with write_lock:
            n_calls += 1
        return lang, generate_batch(lang, args.n_per_call)

    rng = random.Random(args.seed)
    initial: list[str] = []
    for lang, t in targets.items():
        initial.extend([lang] * max(1, int(t / args.n_per_call / 0.8) + 1))
    rng.shuffle(initial)

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futs = {pool.submit(call_for, lang): lang for lang in initial}
        while futs:
            done = next(as_completed(futs))
            lang = futs.pop(done)
            try:
                _, pairs = done.result()
            except Exception as e:
                logging.warning("call exc %s: %s", lang, str(e)[:120])
                continue
            with write_lock:
                bucket[lang].extend(pairs)
                progress = sum(min(len(v), targets[k]) for k, v in bucket.items())
                logging.info("calls=%d %s progress=%d/%d (%.1fs)",
                             n_calls, {k: len(v) for k, v in bucket.items()},
                             progress, total_target, time.time() - t0)
            if len(bucket[lang]) < targets[lang]:
                futs[pool.submit(call_for, lang)] = lang

    seen_qs: set[str] = set()
    final: list[dict] = []
    n_id = 0
    for lang, pairs in bucket.items():
        rng.shuffle(pairs)
        kept = 0
        for p in pairs:
            if kept >= targets[lang]:
                break
            q_norm = p["question"].lower().strip()
            if q_norm in seen_qs:
                continue
            seen_qs.add(q_norm)
            n_id += 1
            final.append({
                "id": f"sft_brief_qa_{n_id:05d}",
                "source": "brief_qa_distilled",
                "question": p["question"],
                "question_lang": lang,
                "category": "brief_qa",
                "chunks": [],
                "answer": p["answer"],
                "skip": False,
                "skip_reason": None,
                "gold_chunk_id": None,
            })
            kept += 1

    rng.shuffle(final)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for r in final:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n=== brief Q&A summary ===", file=sys.stderr)
    print(f"  total: {len(final)} / {total_target}", file=sys.stderr)
    print(f"  calls: {n_calls}", file=sys.stderr)
    print(f"  wall: {time.time() - t0:.1f}s", file=sys.stderr)
    print(f"  output: {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
