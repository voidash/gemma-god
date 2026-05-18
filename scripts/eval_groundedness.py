#!/usr/bin/env python3
"""Eval harness for the Nepal-gov-helpdesk groundedness eval set.

Inputs:
  - eval/gov_helpdesk_gold_v1.jsonl : human-reviewed gold (output of review_web.py)
  - --model SPEC                    : a backend specifier, e.g.
                                      `meridian:claude-sonnet-4-6`
                                      `meridian:claude-opus-4-6`
                                      `meridian:claude-haiku-4-5-20251001`
                                      `mlx:mlx-community/gemma-4-e4b-it-bf16` (TODO)

For each non-dropped gold item, the harness:
  1. Builds the same RAG prompt the deployed helpdesk would use (system prompt
     enforcing strict grounding + question + top retrieved chunks).
  2. Runs the model.
  3. Scores against the gold:
       - grounded items   → chrF + citation-URL recall + wrongly-refused flag
       - refusal items    → did the model correctly refuse (refusal-pattern match)
       - ungrounded items → recorded but excluded from primary metrics

Outputs:
  - eval/reports/<label>.json : per-item results + aggregate stats
  - stdout                     : one-screen summary

Usage:
    # Sonnet 4.6 baseline (via Meridian)
    python scripts/eval_groundedness.py --model meridian:claude-sonnet-4-6 --label sonnet-4-6-baseline

    # Smoke test on 10 items
    python scripts/eval_groundedness.py --model meridian:claude-sonnet-4-6 --limit 10 --label smoke

    # Skip refusals (e.g., for grounded-only iteration)
    python scripts/eval_groundedness.py --model meridian:... --skip-refusal
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

MERIDIAN_URL = os.environ.get("MERIDIAN_URL", "http://127.0.0.1:3456")
DEFAULT_GOLD = "eval/gov_helpdesk_gold_v1.jsonl"
DEFAULT_OUT_DIR = "eval/reports"
TOP_K_CHUNKS = 5
CHUNK_TEXT_MAX_CHARS = 1200  # match build_groundedness_eval params
MAX_TOKENS = 800
MAX_RETRIES = 3
TIMEOUT_S = 90


# ---- Model backends --------------------------------------------------------


class AnthropicShapeBackend:
    """Generic Anthropic Messages-shape backend.

    Both Meridian (local OAuth proxy for Claude Max) and Kimi (Moonshot's
    api.kimi.com endpoint) speak the same Messages API; only base_url and
    api_key differ.
    """

    def __init__(self, base_url: str, api_key: str, model_id: str, label: str = ""):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_id = model_id
        self.label = label or base_url

    def chat(self, system: str, user: str, max_tokens: int = MAX_TOKENS) -> str:
        # `thinking: {type: disabled}` — DeepSeek V4 series defaults thinking-on,
        # which consumes the full max_tokens budget on internal reasoning and
        # returns empty content blocks. Caused n=46 silently-empty judge calls
        # in v3a eval (and 49/50 in v2's first pass). Other Anthropic-shape
        # endpoints (Meridian, Kimi) ignore the field. Always send it.
        payload = json.dumps(
            {
                "model": self.model_id,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
                "thinking": {"type": "disabled"},
            }
        ).encode("utf-8")
        last_err: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                req = urllib.request.Request(
                    f"{self.base_url}/v1/messages",
                    data=payload,
                    headers={
                        "Content-Type": "application/json",
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                    data = json.loads(resp.read())
                if "content" not in data:
                    raise RuntimeError(f"missing 'content' in response: {data}")
                parts = [
                    b.get("text", "")
                    for b in data["content"]
                    if b.get("type") == "text"
                ]
                return "".join(parts).strip()
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="replace")
                last_err = RuntimeError(f"HTTP {e.code}: {err_body[:300]}")
                if e.code in (429, 500, 502, 503, 504):
                    time.sleep(2 ** attempt)
                    continue
                raise last_err
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
                last_err = e
                time.sleep(2 ** attempt)
        raise RuntimeError(
            f"{self.label} call failed after {MAX_RETRIES} attempts: {last_err}"
        )


def _read_brush_provider(provider_id: str) -> dict:
    """Load a provider config from ~/.config/brush/brush.json (key + base_url)."""
    path = Path.home() / ".config" / "brush" / "brush.json"
    if not path.exists():
        raise RuntimeError(f"brush config not found: {path}")
    with path.open(encoding="utf-8") as f:
        cfg = json.load(f)
    prov = cfg.get("providers", {}).get(provider_id)
    if not prov:
        raise RuntimeError(
            f"provider {provider_id!r} not present in {path}; available: "
            f"{list(cfg.get('providers', {}).keys())}"
        )
    return prov


def make_backend(spec: str):
    if spec.startswith("meridian:"):
        return AnthropicShapeBackend(
            base_url=MERIDIAN_URL,
            api_key="x",
            model_id=spec[len("meridian:"):],
            label="meridian",
        )
    if spec.startswith("kimi:"):
        prov = _read_brush_provider("kimi")
        return AnthropicShapeBackend(
            base_url=prov["base_url"],
            api_key=prov["api_key"],
            model_id=spec[len("kimi:"):],
            label="kimi",
        )
    if spec.startswith("mlx:"):
        raise NotImplementedError(
            "MLX backend not yet implemented. Stub for: " + spec[len("mlx:"):]
        )
    raise ValueError(
        f"unknown model spec: {spec!r}. Use 'meridian:<id>', 'kimi:<id>', or 'mlx:<id>'."
    )


# ---- Prompt construction ---------------------------------------------------


SYSTEM_PROMPT = """\
You are a Nepal-government helpdesk. Use ONLY the provided sources to answer.

HARD RULES:
1. Cite each factual claim with source IDs in square brackets, e.g. [S1] or [S2].
   Do not cite raw URLs. Do not use numeric citations like [1].
2. If a claim is not directly supported by ANY source, drop it or mark `[unverified]`.
3. If NO source meaningfully addresses the question, refuse with: "मलाई यो प्रश्नको आधिकारिक स्रोत भेटिनँ" (Devanagari) or "Yo prashnako adhikarik srot bhetina" (Roman-Nepali) or "I cannot find an authoritative source for this" (English) — match the question's language.
4. Respond in the same language/script as the question.
5. Be concise and procedural.
6. Do NOT introduce yourself, do NOT mention being an AI, do NOT use vendor names."""


def build_user_prompt(question: str, chunks: list) -> str:
    parts = [f"Question: {question.strip()}", "", "Sources:"]
    if not chunks:
        parts.append("(no candidate sources surfaced)")
    for c in chunks[:TOP_K_CHUNKS]:
        text = (c.get("text") or "")[:CHUNK_TEXT_MAX_CHARS]
        parts.append(f"\n[S{c.get('rank', '?')}] {c.get('url', '')}")
        parts.append(text)
    parts.append("\nCompose a grounded answer following the rules.")
    return "\n".join(parts)


# ---- Metrics ---------------------------------------------------------------


URL_BRACKETED_RE = re.compile(r"\[(https?://[^\]\s]+)\]")
URL_BARE_RE = re.compile(r"https?://[^\s\)\]\>'\"`]+")
SOURCE_ID_RE = re.compile(r"\[S(\d{1,2})\]")
NUMERIC_CITATION_RE = re.compile(r"(?<!S)\[(\d{1,2})\]")
TRAILING_PUNCT = ",.;:!?)>\"'"


def extract_citations(text: str) -> list[str]:
    """Extract cited URLs from model output.

    Catches both Sonnet-style `[https://...]` and Kimi-style bare URLs
    (often with a `[1]` reference number elsewhere). Trailing punctuation
    is stripped. Order preserved, deduplicated.
    """
    if not text:
        return []
    raw: list[str] = []
    raw.extend(URL_BRACKETED_RE.findall(text))
    raw.extend(URL_BARE_RE.findall(text))
    cleaned: list[str] = []
    for u in raw:
        u = u.rstrip(TRAILING_PUNCT)
        if u:
            cleaned.append(u)
    return list(dict.fromkeys(cleaned))


def extract_source_ids(text: str) -> list[str]:
    """Extract product-style source IDs, e.g. [S1], in order."""
    if not text:
        return []
    return list(dict.fromkeys(f"S{m.group(1)}" for m in SOURCE_ID_RE.finditer(text)))


def source_id_urls(item: dict, source_ids: list[str]) -> list[str]:
    """Map [S#] citations back to candidate chunk URLs for recall scoring."""
    chunks = item.get("candidate_chunks") or []
    urls: list[str] = []
    for sid in source_ids:
        try:
            n = int(sid[1:])
        except Exception:
            continue
        # The prompt numbers candidate chunks as [rank] in order. Prefer rank,
        # then fall back to 1-based list index.
        match = None
        for chunk in chunks:
            if int(chunk.get("rank") or -1) == n:
                match = chunk
                break
        if match is None and 1 <= n <= len(chunks):
            match = chunks[n - 1]
        if match and match.get("url"):
            urls.append(str(match["url"]))
    return list(dict.fromkeys(urls))


def extract_cited_urls(item: dict, text: str) -> list[str]:
    """Extract raw URL citations plus URLs implied by [S#] source IDs."""
    urls = extract_citations(text)
    urls.extend(source_id_urls(item, extract_source_ids(text)))
    return list(dict.fromkeys(urls))


# Refusal-detector patterns. We scan for any of these in the model output.
# Calibrated against Sonnet 4.6 baseline outputs (2026-04-28); the previous
# regex over-fit on `\b` boundaries that fail in Roman-Nepali (e.g.,
# "bhetina" — `bhetin\b` fails because `a` is a word char) and gap sizes too
# tight for the natural Devanagari refusal phrase "मलाई यो प्रश्नको
# आधिकारिक स्रोत भेटिनँ" (~25 chars between मलाई and स्रोत).
REFUSAL_PATTERNS = [
    re.compile(r"\bNO_SOURCE_AVAILABLE\b", re.I),
    # English soft refusals.
    re.compile(
        r"\b(?:cannot|can'?t|do(?:es)? not|don'?t|unable to)\s+"
        r"(?:find|locate|access|provide|determine|confirm|verify|cite|answer)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:no|not|insufficient|lack of|don'?t have)\b[^\.\n]{0,80}\b"
        r"(?:source|sources|info|information|data|details?|reference|coverage)\b",
        re.I,
    ),
    # Devanagari refusal phrases — wider gap, no trailing-letter constraint.
    re.compile(r"मलाई[^\.\n]{0,80}स्रोत[^\.\n]{0,40}भेटि", re.U),
    re.compile(r"स्रोत\s*भेटि", re.U),
    re.compile(r"स्रोत[^\.\n]{0,40}छैन", re.U),
    re.compile(r"आधिकारिक\s+(?:जानकारी|स्रोत|उत्तर)[^\.\n]{0,30}(?:छैन|भेटि|पाइ(?:ँ|न))", re.U),
    re.compile(r"जानकारी\s*उपलब्ध\s*छैन", re.U),
    re.compile(r"उल्लेख\s+(?:गरिएको\s+)?(?:छैन|पाइँदैन)", re.U),
    # Roman-Nepali refusal phrases — no word-boundary trap.
    re.compile(r"\b(?:srot|source)\s+(?:bhetin|chaina|nai chaina|bhetena)", re.I),
    re.compile(r"\badhikarik\s+(?:srot|jawab|jankari)", re.I),  # signature opening of enriched refusals
    re.compile(r"\bjankari\s+(?:chaina|nabhetiyo|napaune|bhetena)", re.I),
    re.compile(r"\bcorpus\s+ma\s+(?:chaina|bhetin)", re.I),
    # Hello Sarkar fallback markers.
    re.compile(r"हेलो\s*सरकार\s*1111", re.U),
    re.compile(r"\bhello\s*sarkar\b[^\n]{0,10}1111", re.I),
    re.compile(r"\b1111\b[^\n]{0,40}(?:टोल[- ]?फ्री|toll[- ]?free)", re.I | re.U),
]


def is_refusal(text: str) -> bool:
    if not text:
        return False
    return any(p.search(text) for p in REFUSAL_PATTERNS)


def char_ngrams(s: str, n: int) -> Counter:
    """Return Counter of character n-grams (excluding pure whitespace runs)."""
    if n <= 0 or len(s) < n:
        return Counter()
    return Counter(s[i : i + n] for i in range(len(s) - n + 1))


def chrf(hyp: str, ref: str, n_max: int = 6, beta: float = 2.0) -> float:
    """Compute chrF (character n-gram F-beta) over n=1..n_max.

    Reference: Popovic 2015. We use n_max=6, beta=2 (standard chrF). This is
    the basic chrF, not chrF++ (which adds word n-grams). For our use case
    (text similarity in a multilingual setting) chrF is the right choice
    because it doesn't depend on tokenization.
    """
    if not hyp or not ref:
        return 0.0
    p_total = 0.0
    r_total = 0.0
    n_used = 0
    for n in range(1, n_max + 1):
        h = char_ngrams(hyp, n)
        r = char_ngrams(ref, n)
        if not h or not r:
            continue
        overlap = sum((h & r).values())
        h_count = sum(h.values())
        r_count = sum(r.values())
        if h_count == 0 or r_count == 0:
            continue
        p_total += overlap / h_count
        r_total += overlap / r_count
        n_used += 1
    if n_used == 0:
        return 0.0
    p_avg = p_total / n_used
    r_avg = r_total / n_used
    if p_avg + r_avg == 0:
        return 0.0
    score = (1 + beta * beta) * p_avg * r_avg / (beta * beta * p_avg + r_avg)
    return 100.0 * score  # standard chrF reported as percentage


def normalize_url(u: str) -> str:
    """Normalize a URL for matching: percent-decode, strip whitespace + trailing
    slash. This makes %E0%A4...-encoded Devanagari URLs match literal-Devanagari
    URLs, which is the same gov.np page either way."""
    if not u:
        return ""
    try:
        return urllib.parse.unquote(u.strip()).rstrip("/")
    except Exception:
        return u.strip().rstrip("/")


def url_recall(model_urls: list[str], gold_urls: list[str]) -> float | None:
    """Citation recall: fraction of gold URLs the model actually cited.
    URLs are percent-decoded before comparison so encoded == literal Unicode.
    Returns None if no gold URLs (irrelevant for grounded items with empty gold)."""
    if not gold_urls:
        return None
    norm_model = {normalize_url(u) for u in model_urls}
    norm_gold = {normalize_url(u) for u in gold_urls}
    matched = norm_model & norm_gold
    return len(matched) / len(norm_gold)


# ---- Per-item evaluation ---------------------------------------------------


def score_one(item: dict, model_output: str, elapsed_ms: int | None = None) -> dict:
    """Score a precomputed model_output against an item. Pure scoring — no
    backend call. Used by both eval_one (sequential) and the batched
    eval_sft_v1 path so the scoring stays in one place."""
    out = {
        "id": item["id"],
        "type": item["type"],
        "category": item.get("question_category"),
        "lang": item.get("question_lang"),
    }
    if elapsed_ms is not None:
        out["elapsed_ms"] = elapsed_ms
    out["model_output"] = model_output
    out["model_source_ids"] = extract_source_ids(model_output)
    out["model_raw_url_citations"] = extract_citations(model_output)
    out["model_numeric_citations"] = list(dict.fromkeys(NUMERIC_CITATION_RE.findall(model_output or "")))
    out["model_citations"] = extract_cited_urls(item, model_output)
    out["model_refused"] = is_refusal(model_output)

    rev = item.get("review") or {}
    gold_answer = rev.get("gold_answer") or item.get("draft_answer") or ""
    gold_urls = rev.get("gold_source_urls") or item.get("draft_citations") or []
    out["gold_answer"] = gold_answer
    out["gold_urls"] = gold_urls

    typ = item["type"]
    if typ == "grounded":
        out["chrf"] = chrf(model_output, gold_answer)
        out["url_recall"] = url_recall(out["model_citations"], gold_urls)
        out["wrongly_refused"] = bool(out["model_refused"])
    elif typ == "refusal":
        out["correctly_refused"] = bool(out["model_refused"])
        out["hallucination"] = bool(not out["model_refused"])
    else:  # ungrounded_attempt
        out["chrf"] = chrf(model_output, gold_answer)
        out["url_recall"] = url_recall(out["model_citations"], gold_urls)
        out["model_refused_when_partial"] = bool(out["model_refused"])
    return out


def eval_one(item: dict, backend) -> dict:
    """Run model on one item; score; return result row.

    On model error, returns a row with error=str(...) and no scores.
    """
    chunks = item.get("candidate_chunks") or []
    user_prompt = build_user_prompt(item["question"], chunks)

    try:
        t0 = time.time()
        model_output = backend.chat(SYSTEM_PROMPT, user_prompt)
        elapsed_ms = int((time.time() - t0) * 1000)
    except Exception as e:
        return {
            "id": item["id"],
            "type": item["type"],
            "category": item.get("question_category"),
            "lang": item.get("question_lang"),
            "error": f"{type(e).__name__}: {str(e)[:200]}",
        }

    return score_one(item, model_output, elapsed_ms)


# ---- Aggregation ----------------------------------------------------------


def aggregate(results: list[dict]) -> dict:
    """Compute aggregate statistics across all per-item results."""
    by_type: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        if r.get("error"):
            continue
        by_type[r["type"]].append(r)

    summary: dict = {
        "n_items": len(results),
        "n_errors": sum(1 for r in results if r.get("error")),
        "by_type": {},
    }

    grounded = by_type.get("grounded", [])
    if grounded:
        chrfs = [r["chrf"] for r in grounded]
        recalls = [r["url_recall"] for r in grounded if r["url_recall"] is not None]
        wrongly = sum(1 for r in grounded if r["wrongly_refused"])
        summary["by_type"]["grounded"] = {
            "n": len(grounded),
            "chrf_mean": sum(chrfs) / len(chrfs),
            "chrf_median": sorted(chrfs)[len(chrfs) // 2],
            "url_recall_mean": (sum(recalls) / len(recalls)) if recalls else None,
            "wrongly_refused": wrongly,
            "wrongly_refused_pct": 100 * wrongly / len(grounded),
        }

    refusal = by_type.get("refusal", [])
    if refusal:
        correct = sum(1 for r in refusal if r["correctly_refused"])
        summary["by_type"]["refusal"] = {
            "n": len(refusal),
            "correctly_refused": correct,
            "correct_pct": 100 * correct / len(refusal),
            "hallucinated": len(refusal) - correct,
            "hallucination_pct": 100 * (len(refusal) - correct) / len(refusal),
        }

    ungr = by_type.get("ungrounded_attempt", [])
    if ungr:
        chrfs = [r["chrf"] for r in ungr]
        summary["by_type"]["ungrounded_attempt"] = {
            "n": len(ungr),
            "chrf_mean": sum(chrfs) / len(chrfs),
        }

    # Per-category for grounded
    by_cat: dict[str, list[float]] = defaultdict(list)
    for r in grounded:
        by_cat[r["category"] or "?"].append(r["chrf"])
    if by_cat:
        summary["grounded_by_category"] = {
            cat: {"n": len(v), "chrf_mean": sum(v) / len(v)}
            for cat, v in sorted(by_cat.items())
        }

    # Per-category for refusal
    ref_by_cat: dict[str, dict] = defaultdict(lambda: {"n": 0, "correct": 0})
    for r in refusal:
        c = r["category"] or "?"
        ref_by_cat[c]["n"] += 1
        ref_by_cat[c]["correct"] += int(r["correctly_refused"])
    if ref_by_cat:
        summary["refusal_by_category"] = {
            cat: {
                "n": d["n"],
                "correct_pct": 100 * d["correct"] / d["n"] if d["n"] else 0,
            }
            for cat, d in sorted(ref_by_cat.items())
        }

    # Per-language
    by_lang: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        if r.get("error"):
            continue
        by_lang[r["lang"] or "?"].append(r)
    summary["by_lang"] = {
        lang: {
            "n": len(rs),
            "grounded_chrf_mean": (
                sum(r["chrf"] for r in rs if r["type"] == "grounded")
                / max(1, sum(1 for r in rs if r["type"] == "grounded"))
            ),
            "refusal_correct_pct": (
                100
                * sum(1 for r in rs if r["type"] == "refusal" and r["correctly_refused"])
                / max(1, sum(1 for r in rs if r["type"] == "refusal"))
            ),
        }
        for lang, rs in sorted(by_lang.items())
    }
    return summary


def print_summary(summary: dict, label: str) -> None:
    print(f"\n=== eval summary: {label} ===")
    print(f"  total items: {summary['n_items']}, errors: {summary['n_errors']}")
    for t, s in summary.get("by_type", {}).items():
        print(f"\n  [{t}] n={s['n']}")
        for k, v in s.items():
            if k == "n":
                continue
            if isinstance(v, float):
                print(f"      {k}: {v:.2f}")
            else:
                print(f"      {k}: {v}")
    if "by_lang" in summary:
        print("\n  by language:")
        for lang, s in summary["by_lang"].items():
            print(
                f"      {lang:>15}: n={s['n']} "
                f"chrf={s['grounded_chrf_mean']:.1f} "
                f"refusal_correct={s['refusal_correct_pct']:.0f}%"
            )


# ---- Main ------------------------------------------------------------------


def load_gold(path: Path, include_dropped: bool = False) -> list[dict]:
    """Load gold; keep only the latest record per id (last-write-wins).
    Drops items with verdict=='dropped' unless include_dropped=True."""
    latest: dict[str, dict] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            latest[r["id"]] = r
    out = []
    for r in latest.values():
        v = (r.get("review") or {}).get("verdict")
        if v == "dropped" and not include_dropped:
            continue
        out.append(r)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default=DEFAULT_GOLD)
    ap.add_argument("--model", required=True, help="backend spec, e.g. meridian:claude-sonnet-4-6")
    ap.add_argument("--label", required=True, help="run label, used in output filename")
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR)
    ap.add_argument("--limit", type=int, default=0, help="0 = all items")
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument(
        "--skip-refusal", action="store_true", help="exclude refusal items"
    )
    ap.add_argument(
        "--skip-grounded", action="store_true", help="exclude grounded items"
    )
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    backend = make_backend(args.model)
    items = load_gold(Path(args.gold))

    if args.skip_refusal:
        items = [r for r in items if r["type"] != "refusal"]
    if args.skip_grounded:
        items = [r for r in items if r["type"] != "grounded"]
    if args.limit > 0:
        items = items[: args.limit]

    type_counts = Counter(r["type"] for r in items)
    logging.info(
        "evaluating %d items (%s) with %s",
        len(items),
        dict(type_counts),
        args.model,
    )

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / f"{args.label}.json"

    results: list[dict] = []
    write_lock = Lock()
    n_done = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futs = {pool.submit(eval_one, it, backend): it for it in items}
        for fut in as_completed(futs):
            res = fut.result()
            with write_lock:
                results.append(res)
                n_done += 1
                if n_done % 5 == 0 or n_done == len(items):
                    elapsed = time.time() - t0
                    rate = n_done / elapsed if elapsed > 0 else 0
                    eta = (len(items) - n_done) / rate if rate > 0 else 0
                    n_err = sum(1 for r in results if r.get("error"))
                    logging.info(
                        "%d/%d (%.2f rec/s, eta %.0fs) | errors=%d",
                        n_done,
                        len(items),
                        rate,
                        eta,
                        n_err,
                    )

    summary = aggregate(results)
    summary["label"] = args.label
    summary["model"] = args.model
    summary["wall_seconds"] = round(time.time() - t0, 1)

    with report_path.open("w", encoding="utf-8") as f:
        json.dump(
            {"summary": summary, "results": results},
            f,
            ensure_ascii=False,
            indent=2,
        )

    print_summary(summary, args.label)
    print(f"\nreport written: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
