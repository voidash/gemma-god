#!/usr/bin/env python3
"""Smoke-test the service-navigator behavior of `/query`.

This is deliberately stricter than the generic RAG audit: it checks that
ambiguous service questions ask follow-up, harmless off-domain questions skip
retrieval, memory is used, and location-specific questions do not cite a
different district's source.
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


def host(url: str | None) -> str:
    return urllib.parse.urlparse(url or "").netloc.lower()


def domain_matches(h: str, domains: list[str]) -> bool:
    h = h.lower()
    return any(h == d.lower() or h.endswith("." + d.lower()) for d in domains)


def contains_any(blob: str, terms: list[str]) -> bool:
    if not terms:
        return True
    blob_l = blob.lower()
    return any(t.lower() in blob_l for t in terms)


def audit_response(rec: dict[str, Any], resp: dict[str, Any]) -> dict[str, Any]:
    answer = resp.get("answer") or ""
    sources = resp.get("sources") or []
    source_urls = [s.get("url") or "" for s in sources]
    blob = "\n".join([answer, *source_urls])
    issues: list[str] = []

    for term in rec.get("must_include_all") or []:
        if term.lower() not in answer.lower():
            issues.append(f"missing:{term}")
    if not contains_any(answer, rec.get("must_include_any") or []):
        issues.append("missing_any")
    for term in rec.get("must_not_include") or []:
        if term.lower() in blob.lower():
            issues.append(f"forbidden:{term}")

    expected_domains = rec.get("expected_domains") or []
    if expected_domains:
        source_hosts = [host(u) for u in source_urls]
        if not any(domain_matches(h, expected_domains) for h in source_hosts):
            issues.append("expected_domain_missing")

    max_generation_ms = rec.get("max_generation_ms")
    if max_generation_ms is not None:
        generation_ms = int((resp.get("latency_ms") or {}).get("generation") or 0)
        if generation_ms > int(max_generation_ms):
            issues.append(f"generation_ms>{max_generation_ms}")

    max_retrieved_total = rec.get("max_retrieved_total")
    if max_retrieved_total is not None:
        retrieved_total = int(resp.get("retrieved_tacit") or 0) + int(resp.get("retrieved_gov") or 0)
        if retrieved_total > int(max_retrieved_total):
            issues.append(f"retrieved_total>{max_retrieved_total}")

    return {
        "id": rec.get("id"),
        "question": rec.get("question"),
        "ok": not issues,
        "issues": issues,
        "latency_ms": resp.get("latency_ms") or {},
        "retrieved_tacit": resp.get("retrieved_tacit"),
        "retrieved_gov": resp.get("retrieved_gov"),
        "source_hosts": [host(u) for u in source_urls],
        "answer_preview": re.sub(r"\s+", " ", answer).strip()[:500],
        "response": resp,
    }


def audit_one(base_url: str, rec: dict[str, Any], timeout: int) -> dict[str, Any]:
    payload = {
        "question": rec["question"],
        "history": rec.get("history") or [],
        "top_k_tacit": int(rec.get("top_k_tacit", 3)),
        "top_k_gov": int(rec.get("top_k_gov", 3)),
        "max_new_tokens": int(rec.get("max_new_tokens", 300)),
    }
    started = time.time()
    resp = post_json(f"{base_url.rstrip('/')}/query", payload, timeout)
    result = audit_response(rec, resp)
    result["wall_ms"] = int((time.time() - started) * 1000)
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--questions", default="eval/navigator_smoke.jsonl")
    ap.add_argument("--out", default="")
    ap.add_argument("--timeout", type=int, default=90)
    args = ap.parse_args()

    rows = load_jsonl(Path(args.questions))
    out_path = Path(args.out) if args.out else Path(
        f"eval/reports/navigator_smoke_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for i, rec in enumerate(rows, 1):
        try:
            result = audit_one(args.base_url, rec, args.timeout)
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
        details = ",".join(result.get("issues") or [])
        print(f"[{i:02d}/{len(rows)}] {status} {rec.get('id')} {details}")

    with out_path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    ok = sum(1 for r in results if r.get("ok"))
    print()
    print(f"wrote: {out_path}")
    print(f"pass: {ok}/{len(results)}")
    failures = [r for r in results if not r.get("ok")]
    if failures:
        print("\nfailures:")
        for r in failures:
            print(f"- {r.get('id')}: {', '.join(r.get('issues') or [])}")
            if r.get("answer_preview"):
                print(f"  {r['answer_preview']}")
            if r.get("error"):
                print(f"  {r['error']}")
    return 0 if ok == len(results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
