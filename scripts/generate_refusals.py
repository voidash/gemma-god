#!/usr/bin/env python3
"""Generate the SFT v2 refusal slice.

The v1 SFT mix had zero refusal examples — the model learned "given chunks,
always write a grounded answer." On the 91 refusal items in the gold eval,
v1 hallucinated 100% of the time. v2 fixes this by adding a refusal slice
to the training mix.

The slice teaches three flavours of "I cannot find an authoritative source":

  - empty   (~60%): gov-domain question + "Sources: (no candidate sources surfaced)"
  - partial (~25%): gov-domain question + chunks that are gov-related but
                    don't answer the specific question (the chunks come from
                    a *different* gov page than the one that would answer)
  - off_domain (~15%): non-gov question (sports, recipes, foreign news,
                       etc.) + maybe some chunks → refusal

Languages are explicitly mixed: ~40% Devanagari, ~30% Roman-Nepali, ~30%
English. Refusal phrasings are diverse (not templated) — DeepSeek generates
both the questions and the refusals so the model sees variation, not a
single regex pattern.

The output schema matches `generate_sft_grounded.py` so `format_sft_v2.py`
can reuse the existing formatter:

    {
      "id": "sft_refusal_00001",
      "source": "refusal_distilled",
      "question": "...",
      "question_lang": "devanagari" | "roman_nepali" | "english",
      "category": "empty" | "partial" | "off_domain",
      "chunks": [],            # may have 1-2 mismatched chunks for partial/off_domain
      "answer": "...",         # the refusal, in question's language
      "skip": false,
    }

Usage:
    # Smoke run — 30 items
    python scripts/generate_refusals.py --n 30

    # Full run — 1100 items, ~$1 of DeepSeek
    python scripts/generate_refusals.py --n 1100
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


# ---- DeepSeek backend (Anthropic-shape) ------------------------------------


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
    raise RuntimeError("DeepSeek API key not found in env or ~/.fmw (DEEPSEEK=)")


def deepseek_chat(system: str, user: str, max_tokens: int = 600, temperature: float = 0.8) -> str:
    """Call DeepSeek's anthropic-compat endpoint. Returns the assistant text."""
    payload = json.dumps({
        "model": DEEPSEEK_MODEL,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        # disable thinking-on which costs tokens for our generation use case
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
    raise RuntimeError(f"deepseek failed after {MAX_RETRIES} retries: {last_err}")


# ---- Question + refusal generation prompts --------------------------------


_LANG_INSTRUCTIONS = {
    "devanagari":
        "Devanagari Nepali (देवनागरी, e.g. 'मेरो नागरिकता प्रमाणपत्र हराएमा के गर्ने?'). "
        "DO NOT use Roman/English script — every word must be in Devanagari.",
    "roman_nepali":
        "Roman-Nepali (Nepali written in Latin/English script, e.g. 'Mero nagarikta hareko cha, kaha janu parcha?'). "
        "Use Roman script, no Devanagari. Use words like 'kasari', 'kun', 'kaha', 'ke garne', 'parcha'.",
    "english": "English",
}

_TOPIC_HINTS = {
    "empty": (
        "real Nepal government / public-services questions a citizen would ask "
        "(citizenship, passport, PAN, VAT, driving license, marriage registration, "
        "birth certificate, business registration, malpot/land tax, customs, "
        "immigration, voter ID, social security, education boards, court procedures, "
        "police, foreign employment, social benefits, etc.). Make them realistic and specific."
    ),
    "partial": (
        "real Nepal government / public-services questions where a related document "
        "is on the gov.np corpus, but the specific aspect of the question may not be "
        "directly answered (e.g., 'what is the LATEST FEE for a passport?' when the "
        "available source only describes the passport application process)."
    ),
    "off_domain": (
        "completely OUT-OF-DOMAIN questions — NOT about Nepal government, public "
        "services, or law. Mix of: Bollywood/cricket/football, recipes, foreign news, "
        "medical advice, stock prices, programming questions, weather, travel "
        "destinations outside Nepal, philosophical questions, relationship advice, etc."
    ),
}


SYSTEM_GENERATOR = (
    "You are generating training examples for a Nepal-government helpdesk. "
    "Each example is a (question, refusal-answer) pair where the refusal "
    "tells the citizen that no authoritative source covers their question, "
    "and (when applicable) suggests the Hello Sarkar 1111 hotline or a "
    "specific government office. Be diverse in phrasing — do not repeat the "
    "same template. Reply with JSON ONLY, no preamble."
)


_REFUSAL_HINTS = {
    "devanagari": (
        "Sample phrasings (mix and vary, do NOT just copy):\n"
        "  - 'मलाई यो प्रश्नको आधिकारिक स्रोत भेटिनँ। थप जानकारीको लागि हेलो सरकार 1111 मा सम्पर्क गर्नुहोस्।'\n"
        "  - 'यो विषयमा गभ.एनपी मा भरपर्दो स्रोत उपलब्ध छैन।'\n"
        "  - 'क्षमा गर्नुहोस्, मसँग यस प्रश्नको आधिकारिक उत्तर छैन।'\n"
        "Mention the relevant gov office or Hello Sarkar 1111 if it would help. "
        "Be brief (1–3 sentences). Polite, factual."
    ),
    "roman_nepali": (
        "Sample phrasings (mix and vary, do NOT just copy):\n"
        "  - 'Mafgarnu, yo prashnako adhikarik srot bhetina. Thap jankari ko lagi Hello Sarkar 1111 ma sampark garnuhos.'\n"
        "  - 'Yo bishaya ma gov.np corpus ma reliable source upalabdha chaina.'\n"
        "  - 'Yo prashnako adhikarik jawaph mero saath ma chaina.'\n"
        "Mention the relevant gov office or Hello Sarkar 1111 if it would help. "
        "Be brief (1–3 sentences). Polite, factual. Use Roman script throughout."
    ),
    "english": (
        "Sample phrasings (mix and vary, do NOT just copy):\n"
        "  - 'I cannot find an authoritative source for this on the available gov.np pages. "
        "For more information, please contact Hello Sarkar 1111.'\n"
        "  - 'No reliable Nepal-government source covers this question.'\n"
        "  - 'I do not have an authoritative answer for this. Please consult the relevant ministry directly.'\n"
        "Mention the relevant gov office or Hello Sarkar 1111 if it would help. "
        "Be brief (1–3 sentences). Polite, factual."
    ),
}


def build_user_prompt(category: str, lang: str, n_per_call: int) -> str:
    """Build the prompt asking DeepSeek for n_per_call (question, refusal) pairs."""
    return f"""\
Generate exactly {n_per_call} (question, refusal-answer) pairs for the Nepal-gov helpdesk.

Question language for ALL {n_per_call} pairs: {_LANG_INSTRUCTIONS[lang]}

Question topic: {_TOPIC_HINTS[category]}

Refusal-answer language: same as the question.

{_REFUSAL_HINTS[lang]}

Reply with a JSON object ONLY. Schema:
{{"pairs": [
  {{"question": "...", "answer": "..."}},
  ...
]}}

The pairs must be DIVERSE — different topics, different sentence structures, different refusal phrasings. No two questions should be near-duplicates."""


# ---- Parsing + validation --------------------------------------------------


_DEVA_RE = re.compile(r"[ऀ-ॿ]")
_LATIN_RE = re.compile(r"[A-Za-z]")
_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.M)


def _try_parse_json(text: str) -> dict | None:
    if not text:
        return None
    text = text.strip()
    text = _FENCE_RE.sub("", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # try to find the first {...} block
        m = re.search(r"\{.*\}", text, flags=re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


def _validate_pair(pair: dict, expect_lang: str) -> tuple[bool, str]:
    q = (pair.get("question") or "").strip()
    a = (pair.get("answer") or "").strip()
    if not q or not a:
        return False, "missing question or answer"
    if len(q) < 8 or len(a) < 8:
        return False, "too short"
    deva_q = len(_DEVA_RE.findall(q))
    latin_q = len(_LATIN_RE.findall(q))
    deva_a = len(_DEVA_RE.findall(a))
    latin_a = len(_LATIN_RE.findall(a))
    total_q = deva_q + latin_q
    total_a = deva_a + latin_a
    if total_q == 0 or total_a == 0:
        return False, "no letters"
    if expect_lang == "devanagari":
        if deva_q / total_q < 0.6 or deva_a / total_a < 0.4:
            return False, "expected devanagari, got mixed/latin"
    elif expect_lang == "roman_nepali":
        if latin_q / total_q < 0.7 or latin_a / total_a < 0.6:
            return False, "expected roman, got too much devanagari"
        # roman-NE marker: needs SOME romanized-NE words, not pure English
        # heuristic: contains common roman-NE function words
        roman_ne_markers = re.compile(
            r"\b(kasari|kun|kaha|ke|chha|cha|garna|garne|parcha|huncha|cha|chaina|"
            r"hos|janu|garnu|hami|tapai|mero|tyo|yo|hoina|ho|nai)\b",
            re.I,
        )
        if not roman_ne_markers.search(q + " " + a):
            return False, "expected roman_nepali but no NE markers"
    elif expect_lang == "english":
        if deva_q / total_q > 0.05 or deva_a / total_a > 0.05:
            return False, "expected english, got devanagari"
    return True, ""


# ---- Main generator loop --------------------------------------------------


def generate_batch(
    category: str, lang: str, n_per_call: int = 10
) -> list[dict]:
    """One DeepSeek call → up to n_per_call validated (question, answer) pairs."""
    user_prompt = build_user_prompt(category, lang, n_per_call)
    try:
        resp = deepseek_chat(SYSTEM_GENERATOR, user_prompt, max_tokens=2400, temperature=0.85)
    except Exception as e:
        logging.warning("deepseek call failed for %s/%s: %s", category, lang, str(e)[:120])
        return []
    parsed = _try_parse_json(resp)
    if not parsed or "pairs" not in parsed:
        logging.warning("parse fail for %s/%s: %s", category, lang, resp[:200])
        return []
    out: list[dict] = []
    for p in parsed["pairs"]:
        ok, why = _validate_pair(p, lang)
        if not ok:
            logging.debug("rejected pair (%s/%s): %s", category, lang, why)
            continue
        out.append({"question": p["question"].strip(), "answer": p["answer"].strip()})
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1100, help="target number of refusal records")
    ap.add_argument("--output", default="corpora/sft_v2_refusals.jsonl")
    ap.add_argument("--n-per-call", type=int, default=10, help="how many pairs per DeepSeek call")
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    # Allocation
    cat_split = {"empty": 0.60, "partial": 0.25, "off_domain": 0.15}
    lang_split = {"devanagari": 0.40, "roman_nepali": 0.30, "english": 0.30}

    targets: dict[tuple[str, str], int] = {}
    for cat, c_frac in cat_split.items():
        for lang, l_frac in lang_split.items():
            targets[(cat, lang)] = max(1, round(args.n * c_frac * l_frac))
    total_target = sum(targets.values())
    logging.info("targets per (category, lang): %s (total=%d)", targets, total_target)

    # Plan: each call returns up to n_per_call. We need ceil(target / n_per_call)
    # successful calls per (cat, lang); over-issue to account for validation losses.
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Per-bucket accumulators
    bucket: dict[tuple[str, str], list[dict]] = {k: [] for k in targets}
    write_lock = Lock()
    n_calls_made = 0

    def call_for(cat: str, lang: str):
        nonlocal n_calls_made
        with write_lock:
            n_calls_made += 1
        pairs = generate_batch(cat, lang, args.n_per_call)
        return cat, lang, pairs

    # Submit waves until each bucket meets its target.
    rng = random.Random(args.seed)
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        # Initial wave: enough calls to hit target with ~80% validation rate
        initial_calls: list[tuple[str, str]] = []
        for (cat, lang), target in targets.items():
            calls_needed = max(1, int(target / args.n_per_call / 0.8) + 1)
            initial_calls.extend([(cat, lang)] * calls_needed)
        rng.shuffle(initial_calls)

        futs = {pool.submit(call_for, cat, lang): (cat, lang) for (cat, lang) in initial_calls}
        while futs:
            done = next(as_completed(futs))
            cat, lang = futs.pop(done)
            try:
                _, _, pairs = done.result()
            except Exception as e:
                logging.warning("call exc %s/%s: %s", cat, lang, str(e)[:120])
                continue
            with write_lock:
                bucket[(cat, lang)].extend(pairs)
                progress = sum(min(len(v), targets[k]) for k, v in bucket.items())
                logging.info(
                    "calls=%d buckets=%s progress=%d/%d (%.1fs)",
                    n_calls_made,
                    {k: len(v) for k, v in bucket.items()},
                    progress, total_target, time.time() - t0,
                )
            # If this bucket still under target, queue another call
            if len(bucket[(cat, lang)]) < targets[(cat, lang)]:
                futs[pool.submit(call_for, cat, lang)] = (cat, lang)

    # Cap to target per bucket, dedupe by question
    seen_qs: set[str] = set()
    final: list[dict] = []
    n_id = 0
    for (cat, lang), records in bucket.items():
        rng.shuffle(records)
        kept = 0
        for r in records:
            if kept >= targets[(cat, lang)]:
                break
            q_norm = r["question"].lower().strip()
            if q_norm in seen_qs:
                continue
            seen_qs.add(q_norm)
            n_id += 1
            final.append({
                "id": f"sft_refusal_{n_id:05d}",
                "source": "refusal_distilled",
                "question": r["question"],
                "question_lang": lang,
                "category": cat,
                "chunks": [],  # always empty for refusal items in v2
                "answer": r["answer"],
                "skip": False,
                "skip_reason": None,
                "gold_chunk_id": None,
            })
            kept += 1

    rng.shuffle(final)
    with out_path.open("w", encoding="utf-8") as f:
        for r in final:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n=== refusal generation summary ===", file=sys.stderr)
    print(f"  total kept: {len(final)} / target {total_target}", file=sys.stderr)
    print(f"  deepseek calls: {n_calls_made}", file=sys.stderr)
    print(f"  wall time: {time.time() - t0:.1f}s", file=sys.stderr)
    print(f"  output: {out_path}", file=sys.stderr)
    from collections import Counter
    print(f"  by (category, lang):", file=sys.stderr)
    by_cat_lang = Counter((r["category"], r["question_lang"]) for r in final)
    for k, v in sorted(by_cat_lang.items()):
        print(f"    {k}: {v}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
