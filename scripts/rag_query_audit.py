#!/usr/bin/env python3
"""Audit full RAG answers independently of a human clicking the chat UI.

The retrieval audit checks whether the right domain surfaced. This script checks
the next layer: whether `/query` returned a usable grounded answer with mapped
citations, no runaway refusal loop, and acceptable latency.

Usage:
    python3 scripts/rag_query_audit.py \
        --base-url http://127.0.0.1:8000 \
        --questions eval/rag_query_smoke.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


SOURCE_REF_RE = re.compile(r"\[(?:S|s)(\d{1,2})\]")
URL_CITATION_RE = re.compile(r"\[https?://[^\]]+\]")
REFUSAL_RE = re.compile(
    r"cannot find an authoritative source|"
    r"मलाई[^\n।.]{0,80}स्रोत[^\n।.]{0,40}भेटि|"
    r"Yo prashnako adhikarik srot bhetina|"
    r"hello\s*sarkar|हेलो\s*सरकार",
    re.I,
)
SENTENCE_SPLIT_RE = re.compile(r"(?<=[।.!?])\s+")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as e:
                raise SystemExit(f"{path}:{line_no}: bad JSON: {e}") from e
    return rows


def post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {detail[:500]}") from e


def host_from_url(url: str | None) -> str:
    if not url:
        return ""
    return urllib.parse.urlparse(url).netloc.lower()


def domain_matches(host: str, expected: list[str]) -> bool:
    host = (host or "").lower()
    for d in expected:
        d = d.lower()
        if host == d or host.endswith("." + d):
            return True
    return False


def normalize_sentence(s: str) -> str:
    s = re.sub(r"\[[^\]]+\]", "", s)
    s = re.sub(r"\W+", " ", s.lower(), flags=re.U).strip()
    return s


def repetition_issue(answer: str) -> str | None:
    sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(answer) if s.strip()]
    seen: dict[str, int] = {}
    for s in sentences:
        key = normalize_sentence(s)
        if len(key) < 20:
            continue
        seen[key] = seen.get(key, 0) + 1
        if seen[key] >= 3:
            return "repeated_sentence"
    refusal_hits = len(REFUSAL_RE.findall(answer))
    if refusal_hits >= 3:
        return "repeated_refusal"
    return None


def required_term_hit(answer: str, terms: list[str]) -> bool:
    if not terms:
        return True
    answer_l = answer.lower()
    return any(t.lower() in answer_l for t in terms)


def audit_response(rec: dict[str, Any], resp: dict[str, Any]) -> dict[str, Any]:
    answer = resp.get("answer") or ""
    sources = resp.get("sources") or []
    citations = resp.get("citations") or []
    expected_domains = rec.get("expected_domains") or []
    expected_refusal = bool(rec.get("expected_refusal"))

    source_ranks = {int(s.get("rank")) for s in sources if s.get("rank") is not None}
    source_hosts = [host_from_url(s.get("url")) for s in sources]
    cited_ranks = {int(c.get("rank")) for c in citations if c.get("rank") is not None}
    cited_hosts = [host_from_url(c.get("url")) for c in citations]
    answer_source_refs = {int(x) for x in SOURCE_REF_RE.findall(answer)}

    issues: list[str] = []
    warnings: list[str] = []

    if expected_domains and not any(domain_matches(h, expected_domains) for h in source_hosts):
        issues.append("expected_domain_missing_from_sources")

    if expected_domains and citations and not any(domain_matches(h, expected_domains) for h in cited_hosts):
        warnings.append("expected_domain_not_cited")

    did_refuse = bool(resp.get("did_refuse")) or bool(REFUSAL_RE.search(answer))
    if did_refuse and not expected_refusal:
        issues.append("unexpected_refusal")
    if expected_refusal and not did_refuse:
        issues.append("expected_refusal_missing")

    if not expected_refusal and not citations:
        issues.append("no_citations")

    if any(int(c.get("rank") or 0) == 0 for c in citations):
        issues.append("rank0_citation")

    if any(rank not in source_ranks for rank in cited_ranks):
        issues.append("citation_rank_not_in_sources")

    if any(rank not in source_ranks for rank in answer_source_refs):
        issues.append("answer_source_ref_not_in_sources")

    if URL_CITATION_RE.search(answer):
        warnings.append("raw_url_citation_in_answer")

    if not required_term_hit(answer, rec.get("required_any") or []):
        issues.append("required_term_missing")

    max_devanagari_answer_chars = rec.get("max_devanagari_answer_chars")
    devanagari_answer_chars = sum(1 for c in answer if "ऀ" <= c <= "ॿ")
    if (
        max_devanagari_answer_chars is not None
        and devanagari_answer_chars > int(max_devanagari_answer_chars)
    ):
        issues.append("answer_devanagari_chars_high")

    rep = repetition_issue(answer)
    if rep:
        issues.append(rep)

    max_generation_ms = int(rec.get("max_generation_ms") or 0)
    generation_ms = int((resp.get("latency_ms") or {}).get("generation") or 0)
    if max_generation_ms and generation_ms > max_generation_ms:
        issues.append("generation_latency_high")

    return {
        "id": rec.get("id"),
        "question": rec.get("question"),
        "topic": rec.get("topic"),
        "ok": not issues,
        "issues": issues,
        "warnings": warnings,
        "did_refuse": did_refuse,
        "expected_refusal": expected_refusal,
        "source_hosts": source_hosts,
        "cited_hosts": cited_hosts,
        "answer_source_refs": sorted(answer_source_refs),
        "citation_ranks": sorted(cited_ranks),
        "devanagari_answer_chars": devanagari_answer_chars,
        "latency_ms": resp.get("latency_ms") or {},
        "answer_preview": re.sub(r"\s+", " ", answer).strip()[:300],
        "response": resp,
    }


def audit_one(
    base_url: str,
    rec: dict[str, Any],
    top_k_tacit: int,
    top_k_gov: int,
    max_new_tokens: int,
    timeout: int,
) -> dict[str, Any]:
    payload = {
        "question": rec["question"],
        "top_k_tacit": int(rec.get("top_k_tacit", top_k_tacit)),
        "top_k_gov": int(rec.get("top_k_gov", top_k_gov)),
        "max_new_tokens": int(rec.get("max_new_tokens", max_new_tokens)),
        "history": rec.get("history") or [],
    }
    t0 = time.time()
    resp = post_json(f"{base_url.rstrip('/')}/query", payload, timeout=timeout)
    result = audit_response(rec, resp)
    result["wall_ms"] = int((time.time() - t0) * 1000)
    return result


def pct(n: int, d: int) -> str:
    if d == 0:
        return "0.0%"
    return f"{100.0 * n / d:.1f}%"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--questions", default="eval/rag_query_smoke.jsonl")
    ap.add_argument("--out", default="")
    ap.add_argument("--top-k-tacit", type=int, default=3)
    ap.add_argument("--top-k-gov", type=int, default=3)
    ap.add_argument("--max-new-tokens", type=int, default=300)
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    questions = load_jsonl(Path(args.questions))
    if args.limit:
        questions = questions[: args.limit]
    if not questions:
        print("no questions to audit", file=sys.stderr)
        return 1

    out_path = Path(args.out) if args.out else Path(
        f"eval/reports/rag_query_audit_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for i, rec in enumerate(questions, 1):
        try:
            result = audit_one(
                args.base_url,
                rec,
                top_k_tacit=args.top_k_tacit,
                top_k_gov=args.top_k_gov,
                max_new_tokens=args.max_new_tokens,
                timeout=args.timeout,
            )
        except Exception as e:
            result = {
                "id": rec.get("id"),
                "question": rec.get("question"),
                "ok": False,
                "issues": ["request_error"],
                "error": str(e),
            }
        results.append(result)
        status = "OK" if result.get("ok") else "FAIL"
        details = ",".join(result.get("issues") or result.get("warnings") or [])
        print(f"[{i:02d}/{len(questions)}] {status} {rec.get('id')} {details}")

    with out_path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    n = len(results)
    ok = sum(1 for r in results if r.get("ok"))
    refused = sum(1 for r in results if r.get("did_refuse"))
    bad_cites = sum(1 for r in results if any("citation" in x for x in r.get("issues", [])))
    loops = sum(1 for r in results if any("repeated" in x for x in r.get("issues", [])))
    slow = sum(1 for r in results if "generation_latency_high" in r.get("issues", []))

    print()
    print(f"wrote: {out_path}")
    print(f"pass: {ok}/{n} ({pct(ok, n)})")
    print(f"refused: {refused}/{n} ({pct(refused, n)})")
    print(f"bad citations: {bad_cites}/{n} ({pct(bad_cites, n)})")
    print(f"loops: {loops}/{n} ({pct(loops, n)})")
    print(f"slow generation: {slow}/{n} ({pct(slow, n)})")

    failures = [r for r in results if not r.get("ok")]
    if failures:
        print("\nfailures:")
        for r in failures[:20]:
            print(f"- {r.get('id')}: {', '.join(r.get('issues', []))}")
            if r.get("answer_preview"):
                print(f"  {r['answer_preview']}")
            if r.get("error"):
                print(f"  {r['error']}")

    return 0 if ok == n else 2


if __name__ == "__main__":
    raise SystemExit(main())
