#!/usr/bin/env python3
"""Generate SFT training tuples via reverse-instruction at scale.

For each substantive chunk, ask the teacher (Kimi K2.6 by default) to
generate BOTH a realistic citizen question AND a full grounded answer.
The output schema matches what the SFT trainer will format into Gemma 4's
chat template:

    {
        "id": "sft_grnd_00001",
        "source": "reverse_instruction",
        "question": "...",
        "question_lang": "devanagari" | "roman_nepali" | "code_mixed",
        "category": "...",
        "difficulty": "easy" | "medium" | "hard",
        "chunks": [{"url": "...", "text": "...", "tier": ..., "source_id": "..."}],
        "answer": "...",         # full grounded answer with [URL] citations
        "skip": false,
        "skip_reason": null,
        "gold_chunk_id": "..."
    }

Differences from `generate_grounded_eval.py`:
  - Outputs FULL grounded answer (not one-line answer_summary)
  - Targets larger N (5000+ chunks) — broader allocation across sources
  - Kimi backend by default (5-6× cheaper, no Max-window cap)
  - No human-review handoff (this is training data, not eval gold)

Usage:
    python scripts/generate_sft_grounded.py --n 100 --limit 100         # smoke
    python scripts/generate_sft_grounded.py --n 5000 --concurrency 12   # full
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

# Allocation across the 42 sources we have crawled. Weighted toward
# citizen-facing sources with low observed skip rate in smoke runs.
# Numbers are PROPORTIONAL; the script scales them to args.n.
# Smoke-run skip rates: jirimun 11%, moha 0%, edcd 0%, nrb 33%; ciaa/doanepal/
# nta/sebon all 100% — those have mostly raw data tables or pure regulatory
# legalese with no narrative ground for citizen questions.
DEFAULT_ALLOCATION_WEIGHTS = {
    "jirimun_gov_np":   38,  # demo target, dense municipal services, lowest skip
    "moha_gov_np":      20,  # passport, citizenship, NID — 0% skip in smoke
    "edcd_gov_np":       9,  # epidemiology / health — 0% skip
    "nrb_org_np":        7,  # banking
    "doind_gov_np":      6,  # industry registration
    "doanepal_gov_np":   5,  # agriculture (some good content among data tables)
    "nta_gov_np":        4,  # telecom (down-weight: high skip)
    "dls_gov_np":        4,  # livestock
    "ciaa_gov_np":       3,  # anti-corruption (down-weight: high skip)
    "ag_gov_np":         2,  # AG legal cases (small but useful)
    "nia_gov_np":        1,  # investigation (small)
    "sebon_gov_np":      1,  # securities (down-weight: high skip)
}

CHUNK_MIN_CHARS = 600
CHUNK_MAX_CHARS = 3000
CHUNK_TEXT_FOR_PROMPT_MAX = 1800

VALID_CATEGORIES = {
    "passport", "citizenship", "tax", "land", "business", "education",
    "driving_license", "pan_vat", "birth_registration", "marriage",
    "visa_immigration", "police", "agriculture", "health", "telecom",
    "banking", "investment", "industry", "local_services", "other",
}
VALID_LANGS = {"devanagari", "roman_nepali", "code_mixed"}
VALID_DIFFICULTIES = {"easy", "medium", "hard"}

MAX_RETRIES = 3
TIMEOUT_S = 120
MAX_TOKENS_PER_BATCH = lambda n: max(1500, 800 * n)  # noqa: E731

PROMPT = """\
You are creating high-quality SFT training items for a Nepal-government
helpdesk fine-tune. For each provided gov.np page excerpt, generate:

  1. A realistic citizen question that this excerpt directly answers.
  2. A full grounded answer in the question's language, citing the source URL.

Hard rules:
- Question language MUST be one of "devanagari", "roman_nepali", or
  "code_mixed". Never English. Pick the one a real Nepal citizen would use:
    * "devanagari" for formal/policy/ministry topics
    * "roman_nepali" for everyday/local/informal topics (Jiri palika, driving
      license, online registration)
    * "code_mixed" when English technical terms naturally appear inside an
      otherwise Nepali question (PAN, VAT, online portal, Smart card, etc.)
- Answer language MUST match the question language exactly.
- Answer MUST cite the source URL using [URL] format in square brackets after
  every factual claim, e.g. [https://www.moha.gov.np/...].
- Answer must be FULLY grounded in the excerpt. Do not introduce facts that
  are not in the excerpt. If a claim is in the excerpt but the URL is not
  cited inline, that claim does not count as grounded — always cite.
- Be concise and procedural. 3-8 short lines. No filler, no preamble.
- Do NOT introduce yourself, do NOT mention being an AI, do NOT use vendor
  names. Speak as a neutral helpdesk.

When to set "skip": true — ONLY in these specific cases:
  (a) The text is garbled / OCR mojibake / not actually parseable.
  (b) The text is a pure data table (rows of numbers / IDs with no
      descriptive context) — no narrative content to ground a question on.
  (c) The text is page navigation / footer / cookie banner / breadcrumb
      metadata only.
  (d) The text repeats the same line many times (extraction artifact).

Do NOT skip just because:
  - The text is bureaucratic / regulatory / formal.
  - It's part of a larger document (annual reports, policy docs).
  - The topic is niche (gov-employee conduct, internal commission rules,
    investor procedures, etc.) — these are still useful training items.
  - The chunk only mentions a service in passing — extract that service.

The goal is BREADTH of training data. Over-strict skipping wastes corpus.
When in doubt, generate a question; even an awkward citizen question that
the chunk can answer is more useful than a skip.

Return STRICT JSON array of EXACTLY {n} items in input order. No markdown
fences. Each item:
{{
  "chunk_id": "<echo input chunk_id>",
  "skip": <bool>,
  "skip_reason": "<one phrase if skip, else null>",
  "question": "<question, blank if skip>",
  "language": "devanagari" | "roman_nepali" | "code_mixed",
  "category": one of the categories listed,
  "difficulty": "easy" | "medium" | "hard",
  "answer": "<full grounded answer with [URL] citations, blank if skip>"
}}

Categories: passport | citizenship | tax | land | business | education |
driving_license | pan_vat | birth_registration | marriage | visa_immigration |
police | agriculture | health | telecom | banking | investment | industry |
local_services | other

Excerpts ({n} total):

{items}

JSON array (length {n}):"""


# ---- Backend (read brush.json for Kimi creds; reuse Anthropic shape) -------


def _read_brush_provider(provider_id: str) -> dict:
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


class AnthropicShapeBackend:
    """Anthropic Messages API shape; supports both x-api-key (Anthropic-style)
    and Bearer (DeepSeek-style) auth, plus per-backend request_extras for
    things like DeepSeek's `thinking: {type: disabled}` toggle."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model_id: str,
        auth_style: str = "x-api-key",
        label: str = "",
        request_extras: dict | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_id = model_id
        self.auth_style = auth_style
        self.label = label or base_url
        self.request_extras = request_extras or {}

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json", "anthropic-version": "2023-06-01"}
        if self.auth_style == "bearer":
            h["Authorization"] = f"Bearer {self.api_key}"
        else:
            h["x-api-key"] = self.api_key
        return h

    def chat(self, prompt: str, max_tokens: int) -> str:
        body = {
            "model": self.model_id,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
            **self.request_extras,
        }
        payload = json.dumps(body).encode("utf-8")
        last_err: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                req = urllib.request.Request(
                    f"{self.base_url}/v1/messages",
                    data=payload,
                    headers=self._headers(),
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
                    time.sleep([5, 15, 30][min(attempt, 2)])
                    continue
                raise last_err
            except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
                last_err = e
                time.sleep([5, 15, 30][min(attempt, 2)])
        raise RuntimeError(f"{self.label} call failed after {MAX_RETRIES} attempts: {last_err}")


def _read_fmw_key(name: str) -> str:
    """Parse simple KEY=VALUE lines from ~/.fmw."""
    path = Path.home() / ".fmw"
    if not path.exists():
        raise RuntimeError(f"{path} not found")
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == name:
            return v.strip()
    raise RuntimeError(f"key {name!r} not in {path}")


def make_backend(spec: str) -> AnthropicShapeBackend:
    if spec.startswith("meridian:"):
        return AnthropicShapeBackend(
            base_url="http://127.0.0.1:3456",
            api_key="x",
            model_id=spec[len("meridian:"):],
            auth_style="x-api-key",
            label="meridian",
        )
    if spec.startswith("kimi:"):
        prov = _read_brush_provider("kimi")
        return AnthropicShapeBackend(
            base_url=prov["base_url"],
            api_key=prov["api_key"],
            model_id=spec[len("kimi:"):],
            auth_style="x-api-key",
            label="kimi",
        )
    if spec.startswith("deepseek:"):
        key = _read_fmw_key("DEEPSEEK")
        return AnthropicShapeBackend(
            base_url="https://api.deepseek.com/anthropic",
            api_key=key,
            model_id=spec[len("deepseek:"):],
            auth_style="bearer",
            label="deepseek",
            # DeepSeek V4-Pro defaults to thinking-on; we want direct text.
            request_extras={"thinking": {"type": "disabled"}},
        )
    raise ValueError(f"unknown backend spec: {spec!r}")


# ---- Chunk selection -------------------------------------------------------


def select_chunks(
    corpus_path: Path,
    n_target: int,
    rng: random.Random,
) -> list[dict]:
    """Select chunks across sources, weighted by DEFAULT_ALLOCATION_WEIGHTS.
    Filters by length to skip nav/header/garbage. Oversamples by 25% to
    account for model-skip rate."""
    weights_total = sum(DEFAULT_ALLOCATION_WEIGHTS.values())
    # Oversample by 60% to absorb model-skip rate (~37% even with permissive
    # prompt + skewed allocation toward low-skip sources).
    n_select = int(n_target * 1.60)
    target_per_src = {
        sid: max(1, round(w * n_select / weights_total))
        for sid, w in DEFAULT_ALLOCATION_WEIGHTS.items()
    }
    by_source: dict[str, list[dict]] = {sid: [] for sid in target_per_src}
    seen_total = 0
    skipped_short = 0
    skipped_long = 0
    skipped_other_source = 0

    with corpus_path.open(encoding="utf-8") as f:
        for line in f:
            seen_total += 1
            r = json.loads(line)
            sid = r.get("source_id")
            if sid not in by_source:
                skipped_other_source += 1
                continue
            text = r.get("text") or ""
            if len(text) < CHUNK_MIN_CHARS:
                skipped_short += 1
                continue
            if len(text) > CHUNK_MAX_CHARS:
                skipped_long += 1
                continue
            by_source[sid].append(r)

    logging.info(
        "corpus scan: %d total chunks; %d skipped(other_src), %d short, %d long",
        seen_total, skipped_other_source, skipped_short, skipped_long,
    )

    selected: list[dict] = []
    for sid, target in target_per_src.items():
        pool = by_source[sid]
        if not pool:
            logging.warning("no eligible chunks for %s", sid)
            continue
        rng.shuffle(pool)
        take = min(target, len(pool))
        if take < target:
            logging.warning(
                "%s: requested %d but only %d eligible chunks", sid, target, take
            )
        selected.extend(pool[:take])
        logging.info("  %s: selected %d / pool %d", sid, take, len(pool))

    rng.shuffle(selected)  # mix source order so concurrent batches see variety
    return selected


# ---- Generation pipeline ---------------------------------------------------


def parse_response(raw: str, expected_n: int) -> list[dict]:
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s
        if s.endswith("```"):
            s = s.rsplit("```", 1)[0]
        s = s.strip()
    parsed = json.loads(s)
    if not isinstance(parsed, list):
        raise ValueError(f"expected JSON array, got {type(parsed).__name__}")
    if len(parsed) != expected_n:
        raise ValueError(f"expected {expected_n} items, got {len(parsed)}")
    return parsed


def _placeholder(chunk: dict, err: Exception) -> dict:
    return {
        "source": "reverse_instruction",
        "question": None,
        "question_lang": None,
        "category": None,
        "difficulty": None,
        "answer": None,
        "skip": True,
        "skip_reason": f"{type(err).__name__}: {str(err)[:200]}",
        "chunks": [_chunk_record(chunk)],
        "gold_chunk_id": chunk.get("chunk_id"),
    }


def _chunk_record(c: dict) -> dict:
    return {
        "chunk_id": c.get("chunk_id"),
        "url": c.get("source_url"),
        "source_id": c.get("source_id"),
        "tier": c.get("tier"),
        "text": c.get("text"),
    }


def _assemble(chunk: dict, p: dict) -> dict:
    skip = bool(p.get("skip"))
    question = (p.get("question") or "").strip()
    answer = (p.get("answer") or "").strip()
    if not skip and (not question or not answer):
        skip = True
    if skip:
        return {
            "source": "reverse_instruction",
            "question": None,
            "question_lang": None,
            "category": None,
            "difficulty": None,
            "answer": None,
            "skip": True,
            "skip_reason": (p.get("skip_reason") or "model marked skip")[:120],
            "chunks": [_chunk_record(chunk)],
            "gold_chunk_id": chunk.get("chunk_id"),
        }
    lang = p.get("language") if p.get("language") in VALID_LANGS else "devanagari"
    cat = p.get("category") if p.get("category") in VALID_CATEGORIES else "other"
    diff = p.get("difficulty") if p.get("difficulty") in VALID_DIFFICULTIES else "medium"
    return {
        "source": "reverse_instruction",
        "question": question,
        "question_lang": lang,
        "category": cat,
        "difficulty": diff,
        "answer": answer,
        "skip": False,
        "skip_reason": None,
        "chunks": [_chunk_record(chunk)],
        "gold_chunk_id": chunk.get("chunk_id"),
    }


def generate_batch(chunks: list[dict], backend: AnthropicShapeBackend) -> list[dict]:
    if not chunks:
        return []
    items_text = "\n\n".join(
        f"[{i+1}] chunk_id={c['chunk_id']} url={c['source_url']}\n{c['text'][:CHUNK_TEXT_FOR_PROMPT_MAX]}"
        for i, c in enumerate(chunks)
    )
    prompt = PROMPT.format(n=len(chunks), items=items_text)
    try:
        raw = backend.chat(prompt, max_tokens=MAX_TOKENS_PER_BATCH(len(chunks)))
        parsed = parse_response(raw, len(chunks))
    except Exception as e:
        logging.warning("batch of %d failed (%s: %s)", len(chunks), type(e).__name__, str(e)[:160])
        return [_placeholder(c, e) for c in chunks]

    out = []
    for c, p in zip(chunks, parsed):
        if not isinstance(p, dict):
            out.append(_placeholder(c, ValueError(f"non-dict item: {p}")))
            continue
        out.append(_assemble(c, p))
    return out


def already_done_chunk_ids(out_path: Path) -> set[str]:
    if not out_path.exists():
        return set()
    seen: set[str] = set()
    with out_path.open(encoding="utf-8") as f:
        for line in f:
            try:
                cid = json.loads(line).get("gold_chunk_id")
                if cid:
                    seen.add(cid)
            except (json.JSONDecodeError, KeyError):
                continue
    return seen


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default="corpora/gov_chunks_v2.jsonl")
    ap.add_argument("--output", default="corpora/sft_v1_grounded.jsonl")
    ap.add_argument("--n", type=int, default=5000, help="target net keeps after model-skips")
    ap.add_argument("--limit", type=int, default=0, help="0 = process all selected")
    ap.add_argument("--batch-size", type=int, default=5)
    ap.add_argument("--concurrency", type=int, default=12)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--model", default="kimi:kimi-for-coding")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    backend = make_backend(args.model)
    corpus_path = Path(args.corpus)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not corpus_path.exists():
        print(f"corpus not found: {corpus_path}", file=sys.stderr)
        return 1

    rng = random.Random(args.seed)
    chunks = select_chunks(corpus_path, args.n, rng)
    logging.info("selected %d chunks (oversampled from target n=%d)", len(chunks), args.n)

    done_ids = already_done_chunk_ids(out_path)
    if done_ids:
        before = len(chunks)
        chunks = [c for c in chunks if c["chunk_id"] not in done_ids]
        logging.info("skipping %d already-done chunks", before - len(chunks))

    if args.limit > 0:
        chunks = chunks[: args.limit]
        logging.info("--limit=%d; processing %d", args.limit, len(chunks))

    if not chunks:
        logging.info("nothing to do")
        return 0

    batches = [chunks[i : i + args.batch_size] for i in range(0, len(chunks), args.batch_size)]
    logging.info(
        "submitting %d batches of up to %d, concurrency=%d, model=%s",
        len(batches), args.batch_size, args.concurrency, args.model,
    )

    write_lock = Lock()
    n_done = 0
    n_kept = 0
    n_skipped = 0
    t0 = time.time()
    with out_path.open("a", encoding="utf-8") as f_out, ThreadPoolExecutor(
        max_workers=args.concurrency
    ) as pool:
        futs = {pool.submit(generate_batch, b, backend): b for b in batches}
        for fut in as_completed(futs):
            results = fut.result()
            with write_lock:
                for row in results:
                    f_out.write(json.dumps(row, ensure_ascii=False) + "\n")
                    n_done += 1
                    if row.get("skip"):
                        n_skipped += 1
                    else:
                        n_kept += 1
                f_out.flush()
                if n_done % (args.batch_size * 4) == 0 or n_done >= len(chunks):
                    elapsed = time.time() - t0
                    rate = n_done / elapsed if elapsed > 0 else 0
                    eta = (len(chunks) - n_done) / rate if rate > 0 else 0
                    logging.info(
                        "%d/%d (%.2f rec/s, eta %.0fs) | kept=%d skipped=%d",
                        n_done, len(chunks), rate, eta, n_kept, n_skipped,
                    )

    print(f"\n=== sft generator summary ===", file=sys.stderr)
    print(f"  processed: {n_done}", file=sys.stderr)
    print(f"  kept:      {n_kept}", file=sys.stderr)
    print(f"  skipped:   {n_skipped}", file=sys.stderr)
    print(f"  output:    {out_path}", file=sys.stderr)
    print(f"  wall:      {time.time()-t0:.0f}s", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
