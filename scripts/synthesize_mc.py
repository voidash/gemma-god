#!/usr/bin/env python3
"""Synthesize MC short-answer items for SFT v2's capability-preservation slice.

Why: SFT v1 wrote option *text* instead of just the *letter* on Belebele
and INCLUDE. e.g. asked 'Reply with only the letter (A/B/C/D)', the v1
model produced 'Taizicheng ski क्षेत्रका कार्यक्रम...' (option B's text)
and the regex extractor `\\b([ABCD])\\b` matched nothing → counted wrong.

This slice teaches the model: when the prompt asks for a single letter,
produce a single letter. We mix two answer formats so the model can
handle both styles:
  - 70% bare letter: 'B'
  - 30% letter + option text: 'B) <option text>'

DeepSeek synthesizes trivia-style MC questions in three languages with
diverse topics (Nepali geography, history, vocabulary, basic math, etc.).
We deliberately don't reuse Belebele or INCLUDE items to avoid eval
contamination.

Output schema:
    {
      "id": "sft_mc_00001",
      "source": "mc_distilled",
      "question": "Read the question and answer with the single best option (A/B/C/D)...",
      "question_lang": "devanagari" | "roman_nepali" | "english",
      "category": "mc_short",
      "chunks": [],
      "answer": "B" or "B) text",
      "skip": false
    }

Usage:
    python scripts/synthesize_mc.py --n 30   # smoke
    python scripts/synthesize_mc.py --n 500  # full
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


SYSTEM_GENERATOR = (
    "You generate multiple-choice trivia questions for an LLM training set. "
    "Each question has exactly 4 options (A, B, C, D) where exactly ONE is "
    "correct. Topics should be diverse — Nepali geography, history, "
    "vocabulary, basic math, science, common knowledge, world capitals, etc. "
    "Avoid copying any Belebele or INCLUDE benchmark items (this is a fresh "
    "synthesis). Reply with JSON ONLY, no preamble."
)


_LANG_INSTR = {
    "devanagari": "Question, options, and reply text MUST be in Devanagari Nepali (देवनागरी). Use realistic Nepali topics.",
    "roman_nepali":
        "Question, options, and reply text MUST be in Roman-Nepali (Nepali in Latin script — words like 'kasari', 'kun', "
        "'kaha', 'ke', 'parcha', 'huncha'). Avoid pure English topics that wouldn't make sense in Roman-Nepali — pick "
        "Nepali-relevant trivia.",
    "english": "Question, options, and reply text MUST be in English. Mix Nepal-related and general world trivia.",
}


def build_prompt(lang: str, n_per_call: int) -> str:
    return f"""\
Generate exactly {n_per_call} multiple-choice questions.

Language: {_LANG_INSTR[lang]}

Rules:
- Exactly 4 options labeled A, B, C, D.
- Exactly one option is correct.
- Options should be plausible (not obviously wrong) — but only one truly correct.
- Diverse topics, no two near-duplicates.
- Keep each option short (under 60 chars).

Reply with JSON ONLY:
{{"items": [
  {{
    "question": "...",
    "options": {{"A": "...", "B": "...", "C": "...", "D": "..."}},
    "correct": "A"
  }},
  ...
]}}"""


# ---- Validation -----------------------------------------------------------


_DEVA_RE = re.compile(r"[ऀ-ॿ]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_ROMAN_NE_MARKERS = re.compile(
    r"\b(kasari|kun|kaha|ke|chha|cha|garna|garne|parcha|huncha|chaina|"
    r"hos|janu|garnu|hami|tapai|mero|tyo|yo|hoina|ho|nai|paryo|bhayo|"
    r"bhanne|bata|ma|sanga|lai|ko|ka|ki)\b",
    re.I,
)


def _validate_item(item: dict, expect_lang: str) -> tuple[bool, str]:
    q = (item.get("question") or "").strip()
    opts = item.get("options") or {}
    correct = (item.get("correct") or "").strip().upper()
    if not q or len(q) < 8:
        return False, "missing/short question"
    if not all(k in opts for k in ("A", "B", "C", "D")):
        return False, "missing options"
    if correct not in ("A", "B", "C", "D"):
        return False, f"bad correct: {correct!r}"
    text_blob = q + " " + " ".join(opts.values())
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


# ---- Main ------------------------------------------------------------------


_PROMPT_FORMAT = (
    "Read the question and answer by choosing the single best option "
    "(A, B, C, or D). Reply with only the letter.\n\n"
    "Question: {question}\n\n"
    "A) {a}\nB) {b}\nC) {c}\nD) {d}\n\n"
    "Answer:"
)


def generate_batch(lang: str, n_per_call: int = 10) -> list[dict]:
    prompt = build_prompt(lang, n_per_call)
    try:
        resp = deepseek_chat(SYSTEM_GENERATOR, prompt, max_tokens=2400, temperature=0.85)
    except Exception as e:
        logging.warning("deepseek %s: %s", lang, str(e)[:120])
        return []
    parsed = _try_parse_json(resp)
    if not parsed or "items" not in parsed:
        logging.warning("parse fail %s: %s", lang, resp[:160])
        return []
    out: list[dict] = []
    for it in parsed["items"]:
        ok, why = _validate_item(it, lang)
        if not ok:
            logging.debug("rejected mc (%s): %s", lang, why)
            continue
        out.append(it)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--output", default="corpora/sft_v2_mc.jsonl")
    ap.add_argument("--n-per-call", type=int, default=10)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--bare-letter-frac", type=float, default=0.7,
                    help="fraction of training answers that are JUST the letter (vs 'B) text')")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    # ~33% per language
    targets = {
        "devanagari": int(args.n * 0.34),
        "roman_nepali": int(args.n * 0.33),
        "english": int(args.n * 0.33),
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
    initial_calls: list[str] = []
    for lang, t in targets.items():
        initial_calls.extend([lang] * max(1, int(t / args.n_per_call / 0.8) + 1))
    rng.shuffle(initial_calls)

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futs = {pool.submit(call_for, lang): lang for lang in initial_calls}
        while futs:
            done = next(as_completed(futs))
            lang = futs.pop(done)
            try:
                _, items = done.result()
            except Exception as e:
                logging.warning("call exc %s: %s", lang, str(e)[:120])
                continue
            with write_lock:
                bucket[lang].extend(items)
                progress = sum(min(len(v), targets[k]) for k, v in bucket.items())
                logging.info("calls=%d %s progress=%d/%d (%.1fs)",
                             n_calls, {k: len(v) for k, v in bucket.items()},
                             progress, total_target, time.time() - t0)
            if len(bucket[lang]) < targets[lang]:
                futs[pool.submit(call_for, lang)] = lang

    # Format final records
    seen_qs: set[str] = set()
    final: list[dict] = []
    n_id = 0
    for lang, items in bucket.items():
        rng.shuffle(items)
        kept = 0
        for it in items:
            if kept >= targets[lang]:
                break
            q_norm = it["question"].lower().strip()
            if q_norm in seen_qs:
                continue
            seen_qs.add(q_norm)
            n_id += 1
            opts = it["options"]
            correct = it["correct"].upper()
            user_q = _PROMPT_FORMAT.format(
                question=it["question"],
                a=opts["A"], b=opts["B"], c=opts["C"], d=opts["D"],
            )
            # Mix answer format: bare letter vs "B) text"
            if rng.random() < args.bare_letter_frac:
                answer = correct
            else:
                answer = f"{correct}) {opts[correct]}"
            final.append({
                "id": f"sft_mc_{n_id:05d}",
                "source": "mc_distilled",
                "question": user_q,
                "question_lang": lang,
                "category": "mc_short",
                "chunks": [],
                "answer": answer,
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

    print(f"\n=== mc synthesis summary ===", file=sys.stderr)
    print(f"  total: {len(final)} / {total_target}", file=sys.stderr)
    print(f"  calls: {n_calls}", file=sys.stderr)
    print(f"  wall: {time.time() - t0:.1f}s", file=sys.stderr)
    print(f"  output: {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
