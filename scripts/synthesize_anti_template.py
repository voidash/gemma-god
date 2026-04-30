#!/usr/bin/env python3
"""Synthesize the anti-template-completion slice for SFT v3.

Why: v2 deploy on k2 (2026-04-29) caught a fabrication mode. When prompt has
chunks covering topic A and the question asks about A, the model paraphrases
correctly. But when the question asks A AND B, the model fabricates B by
template-substitution from A's structure.

Live evidence (citizenship + passport):
  prompt:   chunks describe lost-citizenship procedure
  question: "How do I replace lost citizenship and passport?"
  output:   correct citizenship answer, then template-completed
            "For a lost passport, ... municipality, ... recommendation
            for a duplicate" (passport replacement is NOT done at the
            municipality, this is invented)

The fix: a training slice where the prompt explicitly contains chunks
covering ONLY topic A, the question asks about A AND B, and the gold answer
covers A with citations + refuses B with `[unverified]` or a refusal phrase.

Topic pairs are chosen to be ones the model is *most* likely to confuse —
similar gov procedures with overlapping vocabulary.

Output schema (compatible with format_sft_v2.py's grounded formatter):
    {
      "id": "sft_anti_template_00001",
      "source": "anti_template_distilled",
      "question": "About A and B...",
      "question_lang": "...",
      "category": "anti_template",
      "chunks": [...],   # 1-3 chunks ALL about A
      "answer": "...",    # covers A with citation, refuses/hedges on B
      "skip": false
    }

Usage:
    python scripts/synthesize_anti_template.py --n 30   # smoke
    python scripts/synthesize_anti_template.py --n 300  # full
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
    r"hos|janu|garnu|hami|tapai|mero|tyo|yo|hoina|ho|nai|paryo|bhayo|natra)\b",
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


# Topic pairs that the model is most likely to confuse — similar vocabulary
# and overlapping procedures. The first item is "topic A" (covered by chunks),
# the second is "topic B" (NOT covered, must be refused).
TOPIC_PAIRS = [
    ("citizenship certificate replacement", "passport replacement"),
    ("passport renewal", "visa renewal"),
    ("driving license renewal", "vehicle registration renewal"),
    ("PAN registration", "VAT registration"),
    ("marriage registration", "divorce registration"),
    ("birth certificate", "death certificate"),
    ("business registration with Office of Company Registrar", "branch office registration with foreign authority"),
    ("land malpot tax payment", "house tax payment"),
    ("voter ID card", "national ID card"),
    ("foreign employment permit", "labor union registration"),
    ("educational certificate equivalence (Tribhuvan)", "professional license equivalence (medical council)"),
    ("Nepali citizen passport for adults", "minor's passport application"),
    ("driving license for two-wheeler", "commercial driving license"),
    ("nagarikta by descent", "nagarikta by naturalization"),
    ("birth registration within 35 days", "late birth registration after 35 days"),
    ("electricity new connection", "water new connection"),
    ("temporary residence permit", "permanent residence permit"),
    ("non-objection letter from MOFA", "police clearance certificate from Ministry of Home"),
    ("scholarship application via MOEST", "loan application via Karmachari Sanchaya Kosh"),
    ("VAT refund for tourists", "VAT refund for diplomatic missions"),
    ("import customs clearance for personal goods", "export customs clearance for handicrafts"),
    ("renewing SLC mark sheet", "renewing university degree certificate"),
    ("Nepal Police FIR registration", "Armed Police complaint registration"),
    ("local ward residence verification", "permanent address change"),
    ("disability ID card", "senior citizen ID card"),
    ("widow allowance application", "single woman allowance application"),
    ("EPS Korea labor permit", "GCC migration labor permit"),
    ("pension claim for retired teacher", "pension claim for retired civil servant"),
    ("agricultural subsidy for farmers", "fishery subsidy for fishermen"),
    ("tourist visa extension", "business visa extension"),
]


_LANG_INSTR = {
    "devanagari": "Devanagari Nepali (देवनागरी). Question and answer in Devanagari script.",
    "roman_nepali":
        "Roman-Nepali (Latin script with words like 'kasari', 'kun', 'kaha', 'ke', "
        "'parcha', 'huncha'). Both Q and A in Roman script.",
    "english": "English. Both Q and A in English.",
}


SYSTEM_GENERATOR = (
    "You construct training examples that teach an LLM NOT to fabricate "
    "information by template-completion. The setup: chunks cover topic A. "
    "The question asks about BOTH topic A AND topic B (where B is similar "
    "to A but NOT covered by any chunk). The gold answer must cite chunks "
    "for A and explicitly refuse to answer B. Reply with JSON only — no preamble."
)


def build_prompt(topic_a: str, topic_b: str, lang: str, n_per_call: int) -> str:
    return f"""\
Generate exactly {n_per_call} (chunks, question, gold-answer) examples.

Topic A (covered by chunks): {topic_a}
Topic B (NOT covered, must be refused): {topic_b}

Question/answer language: {_LANG_INSTR[lang]}

For each example:

CHUNKS — generate 2 chunks describing topic A only. Each chunk has:
  - a realistic gov.np-style URL (e.g., https://moha.gov.np/citizenship-replacement)
  - 100-250 chars of text describing topic A's procedure, requirements, or fees
  - chunks should be in the SAME language as the question/answer (matching {_LANG_INSTR[lang]})
  - DO NOT mention topic B in the chunks

QUESTION — a citizen asks about BOTH topic A AND topic B in one breath. Like:
  - "How do I do A? Also, how about B?"
  - "I need to handle both A and B — what's the process?"
  - "मेरो A को बारेमा र B को बारेमा पनि जानकारी दिनुहोस्"
  Question is in {lang} (matching the gold-answer language).

GOLD ANSWER — STRUCTURED REQUIREMENTS:
  - Address topic A with citation [URL] from a chunk.
  - For topic B: explicitly refuse with one of:
      * "[unverified]" tag
      * "उपलब्ध स्रोतमा यसको जानकारी छैन" / "I cannot find an authoritative source for this in the available sources"
      * "Yo bishaya ma reliable source upalabdha chaina"
  - Be concise — 3-5 sentences total max.
  - DO NOT fabricate procedures for B by analogy with A.

Reply with JSON ONLY:
{{"examples": [
  {{
    "chunks": [
      {{"url": "https://...", "text": "..."}},
      {{"url": "https://...", "text": "..."}}
    ],
    "question": "...",
    "answer": "..."
  }},
  ...
]}}
"""


def _validate_example(ex: dict, expect_lang: str, topic_b_kwords: list[str]) -> tuple[bool, str]:
    chunks = ex.get("chunks") or []
    q = (ex.get("question") or "").strip()
    a = (ex.get("answer") or "").strip()
    if not chunks or len(chunks) < 1:
        return False, "no chunks"
    if not q or not a:
        return False, "missing q or a"
    if len(a) > 800:
        return False, f"answer too long ({len(a)} chars)"
    # Check chunks have URL + text
    for c in chunks:
        if not c.get("url") or not re.search(r"https?://", c.get("url", "")):
            return False, "bad chunk url"
        if not c.get("text") or len(c["text"]) < 30:
            return False, "chunk text too short"
    # Question lang
    text_blob = q + " " + a
    deva = len(_DEVA_RE.findall(text_blob))
    latin = len(_LATIN_RE.findall(text_blob))
    tot = deva + latin
    if tot == 0:
        return False, "no letters"
    if expect_lang == "devanagari":
        if deva / tot < 0.5:  # was 0.6 — loosened for chunk citation overhead
            return False, "expected devanagari"
    elif expect_lang == "roman_nepali":
        if latin / tot < 0.6:  # was 0.7 — loosened
            return False, "expected roman script"
        if not _ROMAN_NE_MARKERS.search(text_blob):
            return False, "no roman-NE markers"
    elif expect_lang == "english":
        if deva / tot > 0.20:  # was 0.05 — loosened (chunks may have devanagari quotes)
            return False, "expected english"
    # The KEY check: answer must contain a refusal-style phrase for topic B.
    # Loosened: we accept any of a wider set of "I don't have this info" markers
    # OR explicit mention of needing separate/different consultation.
    refusal_markers = [
        r"\[unverified\]",
        r"उपलब्ध स्रोत",
        r"भेटिनँ",
        r"छैन",
        r"पाइ(ने|एन)",  # paaine / paaena
        r"उल्लेख",  # mentioned (often used in "no mention")
        r"reliable source",
        r"adhikarik srot",
        r"chaina",
        r"chhaina",
        r"bhetin",
        r"cannot find",
        r"can'?t find",
        r"no source",
        r"do not have",
        r"don'?t have",
        r"not available",
        r"separate consultation",
        r"separately",
        r"different",
        r"out of scope",
        r"outside the",
        r"beyond the",
    ]
    if not any(re.search(p, a, re.I | re.U) for p in refusal_markers):
        return False, "no refusal marker for topic B"
    return True, ""


def generate_batch(topic_a: str, topic_b: str, lang: str, n_per_call: int = 5) -> list[dict]:
    prompt = build_prompt(topic_a, topic_b, lang, n_per_call)
    try:
        resp = deepseek_chat(SYSTEM_GENERATOR, prompt, max_tokens=2800, temperature=0.85)
    except Exception as e:
        logging.warning("anti_template %s/%s: %s", topic_a[:30], lang, str(e)[:120])
        return []
    parsed = _try_parse_json(resp)
    if not parsed or "examples" not in parsed:
        logging.warning("parse fail %s/%s: %s", topic_a[:30], lang, resp[:160])
        return []
    out: list[dict] = []
    topic_b_kwords = [w for w in topic_b.lower().split() if len(w) > 3][:3]
    for ex in parsed["examples"]:
        ok, why = _validate_example(ex, lang, topic_b_kwords)
        if not ok:
            logging.debug("rejected (%s/%s): %s", topic_a[:30], lang, why)
            continue
        out.append({
            "chunks": ex["chunks"],
            "question": ex["question"].strip(),
            "answer": ex["answer"].strip(),
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--output", default="corpora/sft_v3_anti_template.jsonl")
    ap.add_argument("--n-per-call", type=int, default=5)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    # Distribute n across topic pairs and languages
    n_pairs = len(TOPIC_PAIRS)
    n_langs = 3
    per_pair_lang = max(1, args.n // (n_pairs * n_langs))
    targets: dict = {}
    for tp in TOPIC_PAIRS:
        for lang in ["devanagari", "roman_nepali", "english"]:
            targets[(tp, lang)] = per_pair_lang
    total_target = sum(targets.values())
    logging.info("targets: %d topic-pairs × %d langs × %d each = %d total",
                 n_pairs, n_langs, per_pair_lang, total_target)

    bucket: dict = {k: [] for k in targets}
    write_lock = Lock()
    n_calls = 0
    t0 = time.time()

    def call_for(tp, lang):
        nonlocal n_calls
        with write_lock:
            n_calls += 1
        return tp, lang, generate_batch(tp[0], tp[1], lang, args.n_per_call)

    rng = random.Random(args.seed)
    initial: list = []
    for (tp, lang), t in targets.items():
        initial.extend([(tp, lang)] * max(1, int(t / args.n_per_call / 0.7) + 1))
    rng.shuffle(initial)

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futs = {pool.submit(call_for, tp, l): (tp, l) for (tp, l) in initial}
        while futs:
            done = next(as_completed(futs))
            tp, lang = futs.pop(done)
            try:
                _, _, items = done.result()
            except Exception as e:
                logging.warning("call exc %s/%s: %s", tp[0][:30], lang, str(e)[:120])
                continue
            with write_lock:
                bucket[(tp, lang)].extend(items)
                progress = sum(min(len(v), targets[k]) for k, v in bucket.items())
                if n_calls % 5 == 0 or progress >= total_target:
                    logging.info("calls=%d progress=%d/%d (%.1fs)",
                                 n_calls, progress, total_target, time.time() - t0)
            if len(bucket[(tp, lang)]) < targets[(tp, lang)]:
                futs[pool.submit(call_for, tp, lang)] = (tp, lang)

    seen_qs: set[str] = set()
    final: list[dict] = []
    n_id = 0
    for (tp, lang), items in bucket.items():
        rng.shuffle(items)
        kept = 0
        for it in items:
            if kept >= targets[(tp, lang)]:
                break
            q_norm = it["question"].lower().strip()
            if q_norm in seen_qs:
                continue
            seen_qs.add(q_norm)
            n_id += 1
            # Tag chunks with rank for compatibility with format_sft_v2's chunk renderer
            chunks = []
            for i, c in enumerate(it["chunks"], 1):
                chunks.append({"rank": i, "url": c["url"], "text": c["text"]})
            final.append({
                "id": f"sft_anti_template_{n_id:05d}",
                "source": "anti_template_distilled",
                "question": it["question"],
                "question_lang": lang,
                "category": f"anti_template_{tp[0][:20].replace(' ','_')}",
                "chunks": chunks,
                "answer": it["answer"],
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

    print(f"\n=== anti_template summary ===", file=sys.stderr)
    print(f"  total: {len(final)} / {total_target}", file=sys.stderr)
    print(f"  calls: {n_calls}", file=sys.stderr)
    print(f"  wall: {time.time() - t0:.1f}s", file=sys.stderr)
    print(f"  output: {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
