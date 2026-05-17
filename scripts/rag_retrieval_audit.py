#!/usr/bin/env python3
"""Audit RAG retrieval independently of generation.

This calls the server's /retrieve endpoint and checks whether the expected
official domain appears in top-1/top-3/top-5. The goal is to make RAG quality
visible before judging model answers.

Usage:
    python3 scripts/rag_retrieval_audit.py \
        --base-url http://127.0.0.1:8000 \
        --questions eval/rag_retrieval_seed.jsonl
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


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
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


def domain_from_url(url: str | None) -> str:
    if not url:
        return ""
    host = urllib.parse.urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def domain_matches(host: str, expected: list[str]) -> bool:
    host = (host or "").lower()
    if host.startswith("www."):
        host = host[4:]
    for d in expected:
        d = d.lower()
        if d.startswith("www."):
            d = d[4:]
        if host == d or host.endswith("." + d):
            return True
    return False


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def source_blob(source: dict) -> str:
    return normalize_text(" ".join([
        source.get("url") or "",
        source.get("host") or "",
        source.get("title") or "",
        source.get("snippet") or "",
    ]))


def term_hit(blob: str, terms: list[str]) -> bool:
    if not terms:
        return True
    return any(normalize_text(t) in blob for t in terms)


def all_terms_hit(blob: str, terms: list[str]) -> bool:
    if not terms:
        return True
    return all(normalize_text(t) in blob for t in terms)


def combo_hit_rank(sources: list[dict], combos: list[list[str]]) -> int | None:
    if not combos:
        return 1
    blobs = [(int(s.get("rank") or i), source_blob(s)) for i, s in enumerate(sources, 1)]
    for combo in combos:
        ranks = [rank for rank, blob in blobs if all_terms_hit(blob, combo)]
        if ranks:
            return min(ranks)
    return None


def post_json(url: str, payload: dict, timeout: int) -> dict:
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
        raise RuntimeError(f"HTTP {e.code}: {detail}") from e


def audit_one(base_url: str, rec: dict, top_k: int, timeout: int) -> dict:
    payload = {
        "question": rec["question"],
        "top_k_tacit": 0,
        "top_k_gov": top_k,
    }
    resp = post_json(f"{base_url.rstrip('/')}/retrieve", payload, timeout=timeout)
    expected = rec.get("expected_domains") or []
    gov_sources = [s for s in resp.get("sources", []) if not s.get("is_tacit")]
    hosts = [
        (s.get("host") or domain_from_url(s.get("url")))
        for s in gov_sources
    ]
    hit_ranks = [
        i for i, host in enumerate(hosts, 1)
        if domain_matches(host, expected)
    ]
    expected_sources = [
        s for s in gov_sources
        if domain_matches(s.get("host") or domain_from_url(s.get("url")), expected)
    ] if expected else gov_sources
    expected_blob = "\n".join(source_blob(s) for s in expected_sources)
    all_blob = "\n".join(source_blob(s) for s in gov_sources)

    required_any = rec.get("required_source_any") or rec.get("required_any") or []
    required_all = rec.get("required_source_all") or []
    required_combo_any = rec.get("required_source_combo_any") or []
    required_combo_min_rank = int(rec.get("required_source_combo_min_rank") or 0)
    url_contains_any = rec.get("expected_url_contains_any") or []
    url_contains_all = rec.get("expected_url_contains_all") or []

    issues: list[str] = []
    if expected and not hit_ranks:
        issues.append("expected_domain_missing")
    if required_any and not term_hit(expected_blob or all_blob, required_any):
        issues.append("required_source_any_missing")
    if required_all and not all_terms_hit(expected_blob or all_blob, required_all):
        issues.append("required_source_all_missing")
    combo_rank = combo_hit_rank(expected_sources or gov_sources, required_combo_any)
    if required_combo_any and combo_rank is None:
        issues.append("required_source_combo_any_missing")
    if required_combo_min_rank and (combo_rank is None or combo_rank > required_combo_min_rank):
        issues.append(f"required_source_combo_not_top{required_combo_min_rank}")
    urls_blob = "\n".join(normalize_text(s.get("url") or "") for s in expected_sources or gov_sources)
    if url_contains_any and not term_hit(urls_blob, url_contains_any):
        issues.append("expected_url_contains_any_missing")
    if url_contains_all and not all_terms_hit(urls_blob, url_contains_all):
        issues.append("expected_url_contains_all_missing")
    min_expected_rank = int(rec.get("min_expected_rank") or 0)
    if min_expected_rank and (not hit_ranks or hit_ranks[0] > min_expected_rank):
        issues.append(f"expected_domain_not_top{min_expected_rank}")

    return {
        "id": rec.get("id"),
        "question": rec["question"],
        "topic": rec.get("topic"),
        "expected_domains": expected,
        "ok": not issues,
        "issues": issues,
        "required_source_any": required_any,
        "required_source_all": required_all,
        "required_source_combo_any": required_combo_any,
        "required_source_combo_rank": combo_rank,
        "expected_url_contains_any": url_contains_any,
        "expected_url_contains_all": url_contains_all,
        "quality": resp.get("quality"),
        "hit_rank": hit_ranks[0] if hit_ranks else None,
        "hit_top1": bool(hit_ranks and hit_ranks[0] <= 1),
        "hit_top3": bool(hit_ranks and hit_ranks[0] <= 3),
        "hit_top5": bool(hit_ranks and hit_ranks[0] <= 5),
        "hosts": hosts,
        "sources": gov_sources,
        "latency_ms": resp.get("latency_ms", {}),
    }


def pct(n: int, d: int) -> str:
    if d == 0:
        return "0.0%"
    return f"{100.0 * n / d:.1f}%"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--questions", default="eval/rag_retrieval_seed.jsonl")
    ap.add_argument("--out", default="")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    questions = load_jsonl(Path(args.questions))
    if args.limit:
        questions = questions[: args.limit]
    if not questions:
        print("no questions to audit", file=sys.stderr)
        return 1

    out_path = Path(args.out) if args.out else Path(
        f"eval/reports/rag_retrieval_audit_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    for i, rec in enumerate(questions, 1):
        try:
            result = audit_one(args.base_url, rec, top_k=args.top_k, timeout=args.timeout)
        except Exception as e:
            result = {
                "id": rec.get("id"),
                "question": rec.get("question"),
                "expected_domains": rec.get("expected_domains") or [],
                "error": str(e),
                "hit_top1": False,
                "hit_top3": False,
                "hit_top5": False,
            }
        results.append(result)
        if result.get("error"):
            status = "ERR"
        elif result.get("ok"):
            status = f"OK hit@{result['hit_rank']}" if result.get("hit_rank") else "OK"
        else:
            status = "FAIL " + ",".join(result.get("issues") or [])
        print(f"[{i:02d}/{len(questions)}] {status} {rec.get('id')}: {rec['question']}")

    with out_path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    n = len(results)
    errors = sum(1 for r in results if r.get("error"))
    top1 = sum(1 for r in results if r.get("hit_top1"))
    top3 = sum(1 for r in results if r.get("hit_top3"))
    top5 = sum(1 for r in results if r.get("hit_top5"))
    ok = sum(1 for r in results if r.get("ok"))
    passed = sum(1 for r in results if r.get("quality", {}).get("passed"))

    print()
    print(f"wrote: {out_path}")
    print(f"errors: {errors}/{n}")
    print(f"coverage ok: {ok}/{n} ({pct(ok, n)})")
    print(f"retrieval quality pass: {passed}/{n} ({pct(passed, n)})")
    print(f"domain hit@1: {top1}/{n} ({pct(top1, n)})")
    print(f"domain hit@3: {top3}/{n} ({pct(top3, n)})")
    print(f"domain hit@5: {top5}/{n} ({pct(top5, n)})")

    failures = [r for r in results if not r.get("ok") and not r.get("error")]
    if failures:
        print("\nfailures:")
        for r in failures[:15]:
            hosts = ", ".join(h for h in r.get("hosts", [])[:5] if h)
            print(f"- {r.get('id')}: {', '.join(r.get('issues', []))}")
            print(f"  expected={r.get('expected_domains')} got={hosts}")

    return 0 if errors == 0 and ok == n else 2


if __name__ == "__main__":
    raise SystemExit(main())
