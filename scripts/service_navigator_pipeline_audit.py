#!/usr/bin/env python3
"""Audit SpeakGov's planner-first service-navigation pipeline.

This complements the older retrieval and answer audits. It checks that the
resolver/planner produces the intended case frame before generation, then checks
retrieval/source hosts and the final answer for the failure modes we care about:
wrong local source, missing follow-up, Hindi leakage, refusal loops, and source
contract breakage.
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


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.navigator import planner_contract, resolve_case  # noqa: E402


SOURCE_REF_RE = re.compile(r"\[(?:S|s)(\d{1,2})\]")
RAW_URL_CITATION_RE = re.compile(r"\[https?://[^\]]+\]")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[।.!?])\s+")
REFUSAL_RE = re.compile(
    r"cannot find an authoritative source|"
    r"मलाई[^\n।.]{0,80}स्रोत[^\n।.]{0,40}भेटि|"
    r"Yo prashnako adhikarik srot bhetina|"
    r"hello\s*sarkar|हेलो\s*सरकार",
    re.I,
)
HINDI_ARTIFACT_RE = re.compile(
    r"\b(?:hai|nahi|aap|hamare|kijiye|sakta hai|karna hoga)\b|है|नहीं|कीजिए|करना होगा",
    re.I,
)


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


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


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


def domain_matches(candidate: str, expected: list[str]) -> bool:
    h = (candidate or "").lower()
    return any(h == d.lower() or h.endswith("." + d.lower()) for d in expected)


def contains_all(blob: str, terms: list[str]) -> list[str]:
    blob_l = blob.lower()
    return [term for term in terms if term.lower() not in blob_l]


def contains_any(blob: str, terms: list[str]) -> bool:
    if not terms:
        return True
    blob_l = blob.lower()
    return any(term.lower() in blob_l for term in terms)


def normalize_sentence(s: str) -> str:
    s = re.sub(r"\[[^\]]+\]", "", s)
    s = re.sub(r"\W+", " ", s.lower(), flags=re.U).strip()
    return s


def repetition_issue(answer: str) -> str | None:
    sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(answer or "") if s.strip()]
    seen: dict[str, int] = {}
    for s in sentences:
        key = normalize_sentence(s)
        if len(key) < 20:
            continue
        seen[key] = seen.get(key, 0) + 1
        if seen[key] >= 3:
            return "repeated_sentence"
    if len(REFUSAL_RE.findall(answer or "")) >= 3:
        return "repeated_refusal"
    return None


def planner_from_local(rec: dict[str, Any]) -> dict[str, Any]:
    frame = resolve_case(rec.get("question") or "", rec.get("history") or [], registry_path=ROOT / "corpora" / "sources_tiered.jsonl")
    return planner_contract(frame)


def planner_issues(rec: dict[str, Any], planner: dict[str, Any] | None) -> list[str]:
    issues: list[str] = []
    if not planner:
        return ["planner_missing"]

    expected_service = rec.get("expected_service")
    if expected_service and planner.get("service") != expected_service:
        issues.append(f"planner_service:{planner.get('service')}!=expected:{expected_service}")

    expected_action = rec.get("expected_action")
    if expected_action and planner.get("action") != expected_action:
        issues.append(f"planner_action:{planner.get('action')}!=expected:{expected_action}")

    expected_case_type = rec.get("expected_case_type")
    if expected_case_type and planner.get("case_type") != expected_case_type:
        issues.append(f"planner_case_type:{planner.get('case_type')}!=expected:{expected_case_type}")

    if "expected_contextual_followup" in rec:
        actual_contextual = bool((planner.get("case_frame") or {}).get("contextual_followup"))
        if actual_contextual != bool(rec.get("expected_contextual_followup")):
            issues.append(f"planner_contextual_followup:{actual_contextual}!=expected:{bool(rec.get('expected_contextual_followup'))}")

    expected_decision = rec.get("expected_decision")
    if expected_decision and planner.get("decision") != expected_decision:
        issues.append(f"planner_decision:{planner.get('decision')}!=expected:{expected_decision}")

    actual_missing = set(planner.get("missing_slots") or [])
    for slot in rec.get("expected_missing_slots") or []:
        if slot not in actual_missing:
            issues.append(f"planner_missing_slot_absent:{slot}")

    planner_domains = planner.get("expected_domains") or []
    for domain in rec.get("expected_domains") or []:
        if not any(domain_matches(d, [domain]) for d in planner_domains):
            issues.append(f"planner_expected_domain_absent:{domain}")

    retrieval_query = planner.get("retrieval_query") or ""
    for term in rec.get("retrieval_query_must_include_all") or []:
        if term.lower() not in retrieval_query.lower():
            issues.append(f"planner_retrieval_query_missing:{term}")

    if expected_decision == "partial_answer_plus_followup" and not planner.get("followup_questions"):
        issues.append("planner_followup_questions_missing")

    return issues


def source_hosts(resp: dict[str, Any] | None) -> list[str]:
    if not resp:
        return []
    return [s.get("host") or host(s.get("url")) for s in resp.get("sources") or []]


def answer_issues(rec: dict[str, Any], query_resp: dict[str, Any] | None) -> list[str]:
    if not query_resp:
        return []
    answer = query_resp.get("answer") or ""
    issues: list[str] = []

    missing_all = contains_all(answer, rec.get("answer_must_include_all") or [])
    issues.extend(f"answer_missing:{term}" for term in missing_all)
    if not contains_any(answer, rec.get("answer_must_include_any") or []):
        issues.append("answer_missing_any")
    blob = "\n".join([
        answer,
        *[s.get("url") or "" for s in query_resp.get("sources") or []],
    ])
    for term in rec.get("answer_must_not_include") or []:
        if term.lower() in blob.lower():
            issues.append(f"answer_forbidden:{term}")

    max_deva = rec.get("max_devanagari_answer_chars")
    if max_deva is not None:
        deva = sum(1 for c in answer if "ऀ" <= c <= "ॿ")
        if deva > int(max_deva):
            issues.append(f"answer_devanagari_chars>{max_deva}")

    if rec.get("forbid_hindi", True) and HINDI_ARTIFACT_RE.search(answer):
        issues.append("answer_hindi_artifact")

    if RAW_URL_CITATION_RE.search(answer):
        issues.append("answer_raw_url_citation")

    rep = repetition_issue(answer)
    if rep:
        issues.append(rep)

    max_generation_ms = rec.get("max_generation_ms")
    if max_generation_ms is not None:
        generation_ms = int((query_resp.get("latency_ms") or {}).get("generation") or 0)
        if generation_ms > int(max_generation_ms):
            issues.append(f"generation_ms>{max_generation_ms}")

    max_retrieved_total = rec.get("max_retrieved_total")
    if max_retrieved_total is not None:
        retrieved_total = int(query_resp.get("retrieved_tacit") or 0) + int(query_resp.get("retrieved_gov") or 0)
        if retrieved_total > int(max_retrieved_total):
            issues.append(f"retrieved_total>{max_retrieved_total}")

    cited = {int(x) for x in SOURCE_REF_RE.findall(answer)}
    source_ranks = {int(s.get("rank")) for s in query_resp.get("sources") or [] if s.get("rank") is not None}
    for rank in cited:
        if rank not in source_ranks:
            issues.append(f"answer_source_ref_not_in_sources:S{rank}")

    return issues


def audit_record(
    rec: dict[str, Any],
    *,
    base_url: str,
    timeout: int,
    planner_only: bool,
) -> dict[str, Any]:
    payload = {
        "question": rec["question"],
        "history": rec.get("history") or [],
        "top_k_tacit": int(rec.get("top_k_tacit", 3)),
        "top_k_gov": int(rec.get("top_k_gov", 3)),
        "max_new_tokens": int(rec.get("max_new_tokens", 300)),
    }
    started = time.time()
    retrieve_resp: dict[str, Any] | None = None
    query_resp: dict[str, Any] | None = None
    planner: dict[str, Any] | None

    if planner_only:
        planner = planner_from_local(rec)
    else:
        retrieve_resp = post_json(f"{base_url.rstrip('/')}/retrieve", {**payload, "include_prompt": False}, timeout)
        planner = retrieve_resp.get("planner")
        query_resp = post_json(f"{base_url.rstrip('/')}/query", payload, timeout)
        planner = query_resp.get("planner") or planner

    issues = planner_issues(rec, planner)

    hosts = source_hosts(retrieve_resp) or source_hosts(query_resp)
    if hosts:
        any_domains = rec.get("source_hosts_must_include_any") or []
        if any_domains and not any(domain_matches(h, any_domains) for h in hosts):
            issues.append("source_host_missing_any")
        for domain in rec.get("source_hosts_must_include_all") or []:
            if not any(domain_matches(h, [domain]) for h in hosts):
                issues.append(f"source_host_missing:{domain}")

    issues.extend(answer_issues(rec, query_resp))

    return {
        "id": rec.get("id"),
        "question": rec.get("question"),
        "ok": not issues,
        "issues": issues,
        "wall_ms": int((time.time() - started) * 1000),
        "planner": planner,
        "source_hosts": hosts,
        "answer_preview": re.sub(r"\s+", " ", (query_resp or {}).get("answer") or "").strip()[:500],
        "retrieve_response": retrieve_resp,
        "query_response": query_resp,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--questions", default="eval/service_navigator_pipeline_smoke.jsonl")
    ap.add_argument("--out", default="")
    ap.add_argument("--timeout", type=int, default=90)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--planner-only", action="store_true", help="validate local resolver/planner without calling the server")
    args = ap.parse_args()

    rows = load_jsonl(ROOT / args.questions if not Path(args.questions).is_absolute() else Path(args.questions))
    if args.limit:
        rows = rows[: args.limit]
    out_path = Path(args.out) if args.out else ROOT / "eval" / "reports" / f"service_navigator_pipeline_{time.strftime('%Y%m%d_%H%M%S')}.jsonl"

    results: list[dict[str, Any]] = []
    for idx, rec in enumerate(rows, 1):
        try:
            result = audit_record(rec, base_url=args.base_url, timeout=args.timeout, planner_only=args.planner_only)
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
        print(f"[{idx:02d}/{len(rows)}] {status} {rec.get('id')} {','.join(result.get('issues') or [])}")

    write_jsonl(out_path, results)
    ok = sum(1 for r in results if r.get("ok"))
    print()
    print(f"wrote: {out_path}")
    print(f"pass: {ok}/{len(results)}")
    if ok != len(results):
        print("\nfailures:")
        for result in results:
            if result.get("ok"):
                continue
            print(f"- {result.get('id')}: {', '.join(result.get('issues') or [])}")
            if result.get("answer_preview"):
                print(f"  {result['answer_preview']}")
            if result.get("error"):
                print(f"  {result['error']}")
    return 0 if ok == len(results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
