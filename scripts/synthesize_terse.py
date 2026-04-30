#!/usr/bin/env python3
"""Synthesize the anti-verbosity slice for SFT v3.

Why: v2 went *more* verbose than v1 (chrF on grounded dropped 22.09 → 13.42).
The new slices that v2 added (translation, mc, brief_qa) didn't fully
counter the grounded slice's "structured grounded answer" output style. The
demo deploy on k2 confirmed v2 outputs 70% more chars than v1 for the same
query.

This slice teaches: when the question is open-ended OR concise, the answer
should be 1–3 sentences, no preamble, no over-explanation. The format is
explicitly "produce a brief, on-point answer".

We mix two flavors:
  - 70% open-ended general questions ("tell me about X", "explain Y") with
    terse 1–3 sentence answers. No chunks.
  - 30% grounded-style questions where the gold answer cites a source
    inline but stays under 3 sentences. Has a single chunk in prompt.

Output schema matches the other slices (compatible with format_sft_v2.py
formatter):
    {
      "id": "sft_terse_00001",
      "source": "terse_distilled",
      "question": "...",
      "question_lang": "devanagari" | "roman_nepali" | "english",
      "category": "open_ended" | "grounded_terse",
      "chunks": [],   # or one chunk for grounded_terse
      "answer": "...",
      "skip": false
    }

Usage:
    python scripts/synthesize_terse.py --n 30   # smoke
    python scripts/synthesize_terse.py --n 200  # full
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
_DEVA_RE = re.compile(r"[ऀ-ॿ]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_ROMAN_NE_MARKERS = re.compile(
    r"\b(kasari|kun|kaha|ke|chha|cha|garna|garne|parcha|huncha|chaina|"
    r"hos|janu|garnu|hami|tapai|mero|tyo|yo|hoina|ho|nai|paryo|bhayo)\b",
    re.I,
)


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
    "devanagari": "Devanagari Nepali (देवनागरी). Both Q and A in Devanagari script — no Roman letters.",
    "roman_nepali":
        "Roman-Nepali (Nepali in Latin script with words like 'kasari', 'kun', 'kaha', "
        "'ke', 'parcha', 'huncha'). Both Q and A in Roman script.",
    "english": "English. Both Q and A in English.",
}


SYSTEM_GENERATOR_OPEN = (
    "You generate (question, terse-answer) pairs for an LLM training set. "
    "The questions are deliberately open-ended or invite verbose responses. "
    "The answer must be SHORT — 1 to 3 sentences max, no preamble, no "
    "list-style elaboration. Direct, on-point. Reply with JSON only."
)


def build_prompt_open(lang: str, n_per_call: int) -> str:
    return f"""\
Generate exactly {n_per_call} (question, terse-answer) pairs.

Language: {_LANG_INSTR[lang]}

Question style — pick from these patterns:
  - "Tell me all about X"
  - "Explain Y in detail"
  - "What do I need to know about Z"
  - "Can you describe how X works"
  - "I want to learn everything about Y"
  - "Walk me through X"

Topics — diverse, NOT government/legal/formal: cooking, weather, hobbies,
local customs, travel, sports, music, daily life, simple science, history,
casual learning.

Answer style — STRICT REQUIREMENTS:
  - 1 to 3 sentences total. Never more.
  - No preamble like "Sure!", "Of course", "Great question".
  - No bullet lists, no numbered steps.
  - No headers, no markdown.
  - Direct, factual, conversational.

Diverse topics, no near-duplicate questions.

Reply with JSON ONLY:
{{"pairs": [
  {{"question": "...", "answer": "..."}},
  ...
]}}
"""


SYSTEM_GENERATOR_GROUNDED_TERSE = (
    "You generate (chunk, question, terse-grounded-answer) tuples for an LLM "
    "training set. The chunk is a fictitious gov.np page snippet; the answer "
    "must cite the chunk's URL inline but stay under 3 sentences. Reply with JSON only."
)


def build_prompt_grounded_terse(lang: str, n_per_call: int) -> str:
    return f"""\
Generate exactly {n_per_call} (chunk, question, terse-grounded-answer) tuples.

Language: {_LANG_INSTR[lang]}

For each tuple:

CHUNK — a 100–200 character snippet that looks like content from a Nepali \
gov.np page about a real public service (citizenship, passport, PAN, VAT, \
license, marriage, birth cert, business reg, etc). Include a fictitious but \
realistic URL like https://moha.gov.np/citizenship-replacement.

QUESTION — a citizen asking specifically about what the chunk covers. \
Keep it natural, in the question_lang.

ANSWER — STRICT REQUIREMENTS:
  - 1 to 3 sentences. Cite the chunk URL in [square brackets] inline.
  - No preamble. No "Based on the source...".
  - No multi-paragraph elaboration.
  - Direct procedural answer.

Reply with JSON ONLY:
{{"pairs": [
  {{
    "chunk_url": "https://...",
    "chunk_text": "...",
    "question": "...",
    "answer": "..."
  }},
  ...
]}}
"""


def _validate_open_pair(pair: dict, expect_lang: str) -> tuple[bool, str]:
    q = (pair.get("question") or "").strip()
    a = (pair.get("answer") or "").strip()
    if not q or not a:
        return False, "missing"
    if len(q) < 8 or len(a) < 8:
        return False, "too short"
    # Strict length cap on answer — 350 chars ≈ 60-80 words ≈ 3 sentences
    if len(a) > 350:
        return False, f"answer too long ({len(a)} chars)"
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
            return False, "no roman-NE markers"
    elif expect_lang == "english":
        if deva / tot > 0.05:
            return False, "expected english"
    # Anti-list / anti-preamble
    if re.match(r"^\s*(sure|of course|absolutely|great question|i'd be happy)", a, re.I):
        return False, "preamble detected"
    if a.count("\n") > 3:
        return False, "too many lines"
    return True, ""


def _validate_grounded_terse(t: dict, expect_lang: str) -> tuple[bool, str]:
    url = (t.get("chunk_url") or "").strip()
    text = (t.get("chunk_text") or "").strip()
    q = (t.get("question") or "").strip()
    a = (t.get("answer") or "").strip()
    if not (url and text and q and a):
        return False, "missing field"
    if len(a) > 400:
        return False, f"answer too long ({len(a)} chars)"
    if not re.search(r"https?://", url):
        return False, "bad url"
    # Answer must cite the URL
    if url not in a and not re.search(r"\[https?://[^\]]+\]", a):
        return False, "answer doesn't cite url"
    return True, ""


def generate_open_batch(lang: str, n_per_call: int = 10) -> list[dict]:
    prompt = build_prompt_open(lang, n_per_call)
    try:
        resp = deepseek_chat(SYSTEM_GENERATOR_OPEN, prompt, max_tokens=2400, temperature=0.9)
    except Exception as e:
        logging.warning("open %s: %s", lang, str(e)[:120])
        return []
    parsed = _try_parse_json(resp)
    if not parsed or "pairs" not in parsed:
        logging.warning("open parse fail %s: %s", lang, resp[:160])
        return []
    out: list[dict] = []
    for p in parsed["pairs"]:
        ok, why = _validate_open_pair(p, lang)
        if not ok:
            logging.debug("rejected open (%s): %s", lang, why)
            continue
        out.append({"question": p["question"].strip(), "answer": p["answer"].strip()})
    return out


def generate_grounded_terse_batch(lang: str, n_per_call: int = 10) -> list[dict]:
    prompt = build_prompt_grounded_terse(lang, n_per_call)
    try:
        resp = deepseek_chat(SYSTEM_GENERATOR_GROUNDED_TERSE, prompt, max_tokens=2400, temperature=0.85)
    except Exception as e:
        logging.warning("grounded_terse %s: %s", lang, str(e)[:120])
        return []
    parsed = _try_parse_json(resp)
    if not parsed or "pairs" not in parsed:
        logging.warning("grounded_terse parse fail %s: %s", lang, resp[:160])
        return []
    out: list[dict] = []
    for t in parsed["pairs"]:
        ok, why = _validate_grounded_terse(t, lang)
        if not ok:
            logging.debug("rejected grounded_terse (%s): %s", lang, why)
            continue
        out.append({
            "chunk_url": t["chunk_url"].strip(),
            "chunk_text": t["chunk_text"].strip(),
            "question": t["question"].strip(),
            "answer": t["answer"].strip(),
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--output", default="corpora/sft_v3_terse.jsonl")
    ap.add_argument("--n-per-call", type=int, default=10)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--open-frac", type=float, default=0.7,
                    help="fraction of items that are open-ended (vs grounded_terse)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    n_open = int(args.n * args.open_frac)
    n_grounded_terse = args.n - n_open
    targets = {
        ("open", "devanagari"): int(n_open * 0.34),
        ("open", "roman_nepali"): int(n_open * 0.33),
        ("open", "english"): int(n_open * 0.33),
        ("grounded_terse", "devanagari"): int(n_grounded_terse * 0.34),
        ("grounded_terse", "roman_nepali"): int(n_grounded_terse * 0.33),
        ("grounded_terse", "english"): int(n_grounded_terse * 0.33),
    }
    total_target = sum(targets.values())
    logging.info("targets: %s (total %d)", targets, total_target)

    bucket: dict = {k: [] for k in targets}
    write_lock = Lock()
    n_calls = 0
    t0 = time.time()

    def call_for(cat, lang):
        nonlocal n_calls
        with write_lock:
            n_calls += 1
        if cat == "open":
            return cat, lang, generate_open_batch(lang, args.n_per_call)
        else:
            return cat, lang, generate_grounded_terse_batch(lang, args.n_per_call)

    rng = random.Random(args.seed)
    initial: list = []
    for (cat, lang), t in targets.items():
        initial.extend([(cat, lang)] * max(1, int(t / args.n_per_call / 0.8) + 1))
    rng.shuffle(initial)

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futs = {pool.submit(call_for, c, l): (c, l) for (c, l) in initial}
        while futs:
            done = next(as_completed(futs))
            cat, lang = futs.pop(done)
            try:
                _, _, items = done.result()
            except Exception as e:
                logging.warning("call exc %s/%s: %s", cat, lang, str(e)[:120])
                continue
            with write_lock:
                bucket[(cat, lang)].extend(items)
                progress = sum(min(len(v), targets[k]) for k, v in bucket.items())
                logging.info("calls=%d progress=%d/%d (%.1fs)",
                             n_calls, progress, total_target, time.time() - t0)
            if len(bucket[(cat, lang)]) < targets[(cat, lang)]:
                futs[pool.submit(call_for, cat, lang)] = (cat, lang)

    seen_qs: set[str] = set()
    final: list[dict] = []
    n_id = 0
    for (cat, lang), items in bucket.items():
        rng.shuffle(items)
        kept = 0
        for it in items:
            if kept >= targets[(cat, lang)]:
                break
            q_norm = it["question"].lower().strip()
            if q_norm in seen_qs:
                continue
            seen_qs.add(q_norm)
            n_id += 1
            if cat == "open":
                rec = {
                    "id": f"sft_terse_{n_id:05d}",
                    "source": "terse_distilled",
                    "question": it["question"],
                    "question_lang": lang,
                    "category": "open_ended",
                    "chunks": [],
                    "answer": it["answer"],
                    "skip": False,
                    "skip_reason": None,
                    "gold_chunk_id": None,
                }
            else:
                rec = {
                    "id": f"sft_terse_{n_id:05d}",
                    "source": "terse_distilled",
                    "question": it["question"],
                    "question_lang": lang,
                    "category": "grounded_terse",
                    "chunks": [{
                        "rank": 1,
                        "url": it["chunk_url"],
                        "text": it["chunk_text"],
                    }],
                    "answer": it["answer"],
                    "skip": False,
                    "skip_reason": None,
                    "gold_chunk_id": None,
                }
            final.append(rec)
            kept += 1

    rng.shuffle(final)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for r in final:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n=== terse summary ===", file=sys.stderr)
    print(f"  total: {len(final)} / {total_target}", file=sys.stderr)
    print(f"  calls: {n_calls}", file=sys.stderr)
    print(f"  wall: {time.time() - t0:.1f}s", file=sys.stderr)
    print(f"  output: {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
