#!/usr/bin/env python3
"""Distill v6 planner/composer contracts from reviewed gold eval chunks.

This is different from live-RAG distillation: the reviewed gold file already
contains the source chunks that should answer or fail the case. Use this when
training source-conditioned behavior such as "do not refuse when S1 contains
the answer" without confounding the run with retrieval misses.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.parse
from pathlib import Path
from typing import Any

from distill_planner_composer_v6 import (  # noqa: E402
    SYSTEM,
    extract_json,
    call_deepseek,
    call_meridian,
    history_text,
    language_instruction,
    load_jsonl,
    merge_unique,
    resolve_planner_hint,
    source_pack,
    validate_contract,
    append_jsonl,
    write_jsonl,
)


def host(url: str) -> str:
    h = urllib.parse.urlparse(url).netloc.lower()
    return h[4:] if h.startswith("www.") else h


def expected_domains(row: dict[str, Any]) -> list[str]:
    out: list[str] = []
    review = row.get("review") or {}
    for url in review.get("gold_source_urls") or []:
        h = host(str(url))
        if h:
            out.append(h)
    gold = row.get("gold_chunk") or {}
    if gold.get("url"):
        h = host(str(gold["url"]))
        if h:
            out.append(h)
    for chunk in row.get("candidate_chunks") or []:
        if chunk.get("url"):
            h = host(str(chunk["url"]))
            if h:
                out.append(h)
    return merge_unique([], out)


def gold_answer(row: dict[str, Any]) -> str:
    review = row.get("review") or {}
    return str(review.get("gold_answer") or row.get("draft_answer") or "").strip()


def candidate_sources(row: dict[str, Any], max_sources: int) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for idx, chunk in enumerate(row.get("candidate_chunks") or [], 1):
        url = str(chunk.get("url") or "")
        sources.append({
            "source_ref": f"S{idx}",
            "rank": idx,
            "url": url,
            "host": host(url) if url else "",
            "label": "GOV.NP",
            "title": chunk.get("title") or "",
            "snippet": chunk.get("text") or "",
            "is_tacit": False,
        })
    if not sources:
        gold = row.get("gold_chunk") or {}
        url = str(gold.get("url") or "")
        if gold.get("text"):
            sources.append({
                "source_ref": "S1",
                "rank": 1,
                "url": url,
                "host": host(url) if url else "",
                "label": "GOV.NP",
                "title": gold.get("title") or "",
                "snippet": gold.get("text") or "",
                "is_tacit": False,
            })
    return sources[:max_sources]


def expected_behavior(row: dict[str, Any]) -> str:
    typ = row.get("type")
    if typ == "grounded":
        return "answer"
    if typ == "refusal":
        return "refuse"
    return "partial_or_followup"


def distill_one(
    row: dict[str, Any],
    provider: str,
    model: str,
    timeout: int,
    max_snippet_chars: int,
    max_sources: int,
) -> dict[str, Any]:
    rec = {
        "id": f"v6_1_gold_{row.get('id')}",
        "question": row.get("question") or "",
        "history": row.get("history") or [],
        "question_lang": row.get("question_lang"),
        "service": row.get("question_category") or "other",
        "topic": row.get("question_category") or "other",
        "expected_behavior": expected_behavior(row),
        "expected_domains": expected_domains(row),
    }
    frame, planner_hint = resolve_planner_hint(rec)
    rec["expected_domains"] = merge_unique(planner_hint.get("expected_domains") or [], rec["expected_domains"])
    sources = candidate_sources(row, max_sources=max_sources)
    retrieve_resp = {
        "sources": sources,
        "quality": {
            "mode": "reviewed_gold_candidate_chunks",
            "gold_type": row.get("type"),
            "topic": rec["topic"],
            "gold_answer": gold_answer(row),
        },
    }
    sources_text, valid_ids, sid_text, sid_host = source_pack(retrieve_resp, max_snippet_chars)
    question_lang = rec.get("question_lang") or frame.language
    expected_domains_text = ""
    if rec["expected_domains"]:
        expected_domains_text = (
            "Expected authoritative domains for this reviewed gold case: "
            f"{', '.join(rec['expected_domains'])}\n"
            "The gold answer below was human-reviewed; preserve its factual content but match the requested language/script and cite source IDs.\n\n"
        )
    reviewed_answer = gold_answer(row)
    user = (
        f"Conversation history:\n{history_text(rec.get('history') or [])}\n\n"
        f"Latest user question: {rec['question'].strip()}\n\n"
        f"Question language: {question_lang}\n"
        f"Language instruction: {language_instruction(question_lang)}\n\n"
        f"Reviewed gold answer:\n{reviewed_answer}\n\n"
        f"Gold row type: {row.get('type')}\n"
        f"Expected behavior: {rec['expected_behavior']}\n\n"
        f"Deterministic planner hint:\n{json.dumps(planner_hint, ensure_ascii=False, indent=2)}\n\n"
        f"{expected_domains_text}"
        f"{sources_text}\n\n"
        "Return the v6 JSON contract only. If Gold row type is grounded and the Sources support the reviewed answer, answer instead of refusing."
    )
    t0 = time.time()
    if provider == "meridian":
        raw = call_meridian(SYSTEM, user, model=model, timeout=timeout)
    elif provider == "deepseek":
        raw = call_deepseek(SYSTEM, user, model=model, timeout=timeout)
    else:
        raise ValueError(f"unsupported provider: {provider}")
    teacher_ms = int((time.time() - t0) * 1000)
    contract = extract_json(raw)
    issues = validate_contract(
        contract,
        valid_ids=valid_ids,
        sid_text=sid_text,
        sid_host=sid_host,
        expected_lang=question_lang,
        expected_domains=rec["expected_domains"],
        planner_hint=planner_hint,
    )
    return {
        **rec,
        "source": "v6_planner_composer_gold_teacher",
        "teacher_provider": provider,
        "teacher_model": model,
        "original_gold_id": row.get("id"),
        "gold_type": row.get("type"),
        "reviewed_gold_answer": reviewed_answer,
        "planner_hint": planner_hint,
        "retrieve_quality": retrieve_resp["quality"],
        "sources": sources,
        "contract": contract,
        "answer": contract.get("final_answer"),
        "validation_issues": issues,
        "teacher_ms": teacher_ms,
        "raw_teacher": raw if issues else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default="eval/gov_helpdesk_gold_v1.jsonl")
    ap.add_argument("--out", default="corpora/sft_v6_1_gold_contracts.jsonl")
    ap.add_argument("--provider", choices=["meridian", "deepseek"], default="deepseek")
    ap.add_argument("--model", default="")
    ap.add_argument("--include-types", default="grounded")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-snippet-chars", type=int, default=1400)
    ap.add_argument("--max-sources", type=int, default=5)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--fail-on-issues", action="store_true")
    args = ap.parse_args()

    model = args.model or ("claude-sonnet-4-6" if args.provider == "meridian" else "deepseek-v4-flash")
    include_types = {s.strip() for s in args.include_types.split(",") if s.strip()}
    rows = [r for r in load_jsonl(Path(args.gold)) if r.get("type") in include_types]
    if args.offset:
        rows = rows[args.offset :]
    if args.limit:
        rows = rows[: args.limit]
    if not rows:
        print("no gold rows to distill")
        return 1

    out_path = Path(args.out)
    out: list[dict[str, Any]] = []
    done_ids: set[str] = set()
    if args.resume and out_path.exists():
        out = load_jsonl(out_path)
        done_ids = {str(r.get("original_gold_id")) for r in out if r.get("original_gold_id")}
    elif out_path.exists():
        out_path.unlink()

    failures = 0
    for i, row in enumerate(rows, 1):
        if row.get("id") in done_ids:
            print(f"[{i:03d}/{len(rows)}] SKIP {row.get('id')} already_done", flush=True)
            continue
        try:
            distilled = distill_one(
                row,
                provider=args.provider,
                model=model,
                timeout=args.timeout,
                max_snippet_chars=args.max_snippet_chars,
                max_sources=args.max_sources,
            )
        except Exception as e:
            failures += 1
            distilled = {
                "id": f"v6_1_gold_{row.get('id')}",
                "original_gold_id": row.get("id"),
                "question": row.get("question"),
                "source": "v6_planner_composer_gold_teacher",
                "teacher_provider": args.provider,
                "teacher_model": model,
                "error": str(e),
                "validation_issues": ["distill_error"],
            }
            print(f"[{i:03d}/{len(rows)}] ERROR {row.get('id')} {e}", flush=True)
        out.append(distilled)
        append_jsonl(out_path, distilled)
        status = "OK" if not distilled.get("validation_issues") else "WARN"
        issues = ",".join(distilled.get("validation_issues") or [])
        print(f"[{i:03d}/{len(rows)}] {status} {row.get('id')} {issues}", flush=True)

    invalid = sum(1 for r in out if r.get("validation_issues"))
    print()
    print(f"wrote: {args.out}")
    print(f"errors: {failures}/{len(out)}")
    print(f"validation issues: {invalid}/{len(out)}")
    if args.fail_on_issues and invalid:
        return 1
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
