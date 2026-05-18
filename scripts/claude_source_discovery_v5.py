#!/usr/bin/env python3
"""Use Claude Code/Opus as a source-discovery worker for SpeakGov.

This script is intentionally not a replacement for RAG. It asks Claude Code to
search for official sources, return crawlable URLs and a source-backed answer
contract, then saves the results as JSONL. The durable output should be used to
seed/crawl official sources and then regenerate RAG contracts from our own
indexed corpus.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_MODEL = "opus"

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "question": {"type": "string"},
        "service": {"type": "string"},
        "action": {"type": "string"},
        "location": {"type": "string"},
        "answerability": {
            "type": "string",
            "enum": ["answer", "partial", "no_official_source", "off_domain"],
        },
        "official_sources": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "title": {"type": "string"},
                    "authority": {"type": "string"},
                    "source_class": {
                        "type": "string",
                        "enum": [
                            "law_or_rule",
                            "service_page",
                            "citizen_charter",
                            "notice_or_fee",
                            "form_or_download",
                            "contact_or_staff",
                            "office_directory",
                            "faq_or_help",
                            "other_official",
                        ],
                    },
                    "verification": {
                        "type": "string",
                        "enum": [
                            "fetched_and_relevant",
                            "official_candidate_not_fetched",
                            "official_but_low_relevance",
                        ],
                    },
                    "evidence": {"type": "string"},
                    "claims_supported": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "crawl_priority": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                },
                "required": [
                    "url",
                    "title",
                    "authority",
                    "source_class",
                    "verification",
                    "evidence",
                    "claims_supported",
                    "crawl_priority",
                ],
                "additionalProperties": False,
            },
        },
        "facts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "source_urls": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["claim", "source_urls"],
                "additionalProperties": False,
            },
        },
        "missing": {
            "type": "array",
            "items": {"type": "string"},
        },
        "followups": {
            "type": "array",
            "items": {"type": "string"},
        },
        "answer": {"type": "string"},
        "crawl_notes": {"type": "string"},
        "suggested_search_queries": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": [
        "question",
        "service",
        "action",
        "location",
        "answerability",
        "official_sources",
        "facts",
        "missing",
        "followups",
        "answer",
        "crawl_notes",
        "suggested_search_queries",
    ],
    "additionalProperties": False,
}


PROMPT_TEMPLATE = """\
You are doing source discovery for SpeakGov, a Nepal government-service
navigator. Use web search/fetch if needed.

Goal:
- First inspect the Current SpeakGov RAG retrieval pack.
- Decide whether the current RAG sources are enough, partially useful, or wrong.
- Find official source URLs that should be added to our RAG corpus.
- Produce a concise answer contract only from official sources you found.
- Be honest when an official URL is only a candidate and was not fetched.

Strict rules:
- Prefer official Nepal sources: .gov.np, official ministry/department pages,
  lawcommission.gov.np, parliament/commission/statutory bodies, official
  embassy/mission pages, and official province/municipality pages.
- You may use secondary sources only to discover official URLs. Do not cite
  secondary sources in official_sources or facts.
- Do not invent phone numbers, contacts, forms, fees, deadlines, or law
  sections.
- If a source is likely official but could not be fetched, include it with
  verification="official_candidate_not_fetched" and do not treat its detailed
  claims as verified facts.
- For ambiguous citizen questions, include compact followups but still give
  useful supported routing/contact/source information.
- Match the user's language/script in answer when practical. If the question is
  Roman Nepali, use Roman Nepali, not Hindi.
- If the Current SpeakGov RAG sources are relevant, reuse them and say which
  claims they support. If they are irrelevant, say they are distractors and find
  better official sources.
- official_sources should include useful current RAG URLs too, when relevant,
  not only newly discovered web URLs.
- Return JSON only in the required schema.

Record metadata:
id: {record_id}
service/topic hint: {topic}
expected authority domains if known: {expected_domains}

User question:
{question}

Current SpeakGov RAG retrieval pack:
{rag_pack}
"""


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


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()


def done_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    out: set[str] = set()
    for row in load_jsonl(path):
        if row.get("id"):
            out.add(str(row["id"]))
    return out


def record_id(row: dict[str, Any], index: int) -> str:
    return str(row.get("id") or row.get("demand_id") or f"row_{index:04d}")


def compact_question(row: dict[str, Any]) -> str:
    q = str(row.get("question") or row.get("raw_query") or row.get("canonical_query") or "")
    q = re.sub(r"\s+", " ", q).strip()
    return q


def post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def retrieve_rag(
    base_url: str,
    question: str,
    timeout: int,
    top_k_tacit: int,
    top_k_gov: int,
) -> dict[str, Any] | None:
    if not base_url:
        return None
    return post_json(
        f"{base_url.rstrip('/')}/retrieve",
        {
            "question": question,
            "top_k_tacit": top_k_tacit,
            "top_k_gov": top_k_gov,
        },
        timeout,
    )


def compact(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def format_rag_pack(rag: dict[str, Any] | None, snippet_chars: int) -> str:
    if not rag:
        return "(not provided)"
    lines: list[str] = []
    quality = rag.get("quality") or {}
    if quality:
        lines.append("Retrieval quality:")
        lines.append(json.dumps(quality, ensure_ascii=False))
        lines.append("")
    sources = rag.get("sources") or []
    if not sources:
        lines.append("(no current RAG sources surfaced)")
        return "\n".join(lines)
    for idx, src in enumerate(sources, 1):
        sid = src.get("source_ref") or f"S{src.get('rank') or idx}"
        label = src.get("label") or ("CITIZEN INTERVIEW" if src.get("is_tacit") else "GOV.NP")
        lines.append(f"[{sid}] {label}")
        if src.get("host"):
            lines.append(f"Host: {src.get('host')}")
        if src.get("url"):
            lines.append(f"URL: {src.get('url')}")
        if src.get("title"):
            lines.append(f"Title: {src.get('title')}")
        lines.append(f"Excerpt: {compact(src.get('snippet') or '', snippet_chars)}")
        lines.append("")
    return "\n".join(lines).strip()


def run_claude(prompt: str, model: str, timeout: int, cwd: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    cmd = [
        "claude",
        "-p",
        "--model",
        model,
        "--no-session-persistence",
        "--allowedTools",
        "WebSearch,WebFetch",
        "--output-format",
        "json",
        "--json-schema",
        json.dumps(SCHEMA, separators=(",", ":")),
        prompt,
    ]
    started = time.time()
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    elapsed_ms = int((time.time() - started) * 1000)
    if not proc.stdout.strip():
        raise RuntimeError(f"claude produced no stdout; rc={proc.returncode}; stderr={proc.stderr[-1000:]}")
    try:
        wrapper = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"claude stdout was not JSON: {proc.stdout[:1000]}") from e
    if proc.returncode != 0 or wrapper.get("is_error"):
        raise RuntimeError(
            f"claude failed rc={proc.returncode} subtype={wrapper.get('subtype')} "
            f"errors={wrapper.get('errors')} result={str(wrapper.get('result'))[:1000]} "
            f"stderr={proc.stderr[-1000:]}"
        )
    structured = wrapper.get("structured_output")
    if not isinstance(structured, dict):
        result = wrapper.get("result")
        if isinstance(result, str):
            structured = json.loads(result)
        else:
            raise RuntimeError("claude result missing structured_output")
    meta = {
        "elapsed_ms": elapsed_ms,
        "total_cost_usd": wrapper.get("total_cost_usd"),
        "model_usage": wrapper.get("modelUsage"),
        "session_id": wrapper.get("session_id"),
        "stderr_tail": proc.stderr[-1000:] if proc.stderr else "",
    }
    return structured, meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--rag-base-url", default="")
    ap.add_argument("--rag-timeout", type=int, default=60)
    ap.add_argument("--top-k-tacit", type=int, default=3)
    ap.add_argument("--top-k-gov", type=int, default=6)
    ap.add_argument("--rag-snippet-chars", type=int, default=900)
    ap.add_argument(
        "--cwd",
        default="/tmp",
        help="Run Claude from this directory to avoid loading project context.",
    )
    args = ap.parse_args()

    rows = load_jsonl(Path(args.questions))
    if args.limit:
        rows = rows[: args.limit]

    out_path = Path(args.out)
    seen = done_ids(out_path) if args.resume else set()
    if out_path.exists() and not args.resume:
        out_path.unlink()

    failures = 0
    for idx, row in enumerate(rows, 1):
        rid = record_id(row, idx)
        if rid in seen:
            print(f"[{idx:04d}/{len(rows)}] SKIP {rid}", flush=True)
            continue
        question = compact_question(row)
        rag_resp: dict[str, Any] | None = None
        rag_error: str | None = None
        if args.rag_base_url:
            try:
                rag_resp = retrieve_rag(
                    args.rag_base_url,
                    question,
                    timeout=args.rag_timeout,
                    top_k_tacit=args.top_k_tacit,
                    top_k_gov=args.top_k_gov,
                )
            except Exception as e:
                rag_error = str(e)
        rag_pack = format_rag_pack(rag_resp, args.rag_snippet_chars)
        if rag_error:
            rag_pack = f"RAG retrieval error: {rag_error}\n\n{rag_pack}"
        prompt = PROMPT_TEMPLATE.format(
            record_id=rid,
            topic=row.get("topic") or row.get("service") or row.get("category") or "",
            expected_domains=", ".join(row.get("expected_domains") or row.get("suggested_authority_domains") or []),
            question=question,
            rag_pack=rag_pack,
        )
        try:
            structured, meta = run_claude(prompt, args.model, args.timeout, Path(args.cwd))
            result = {
                "id": rid,
                "source": "claude_code_source_discovery_v5",
                "question": question,
                "input": row,
                "rag_retrieve": rag_resp,
                "rag_error": rag_error,
                "discovery": structured,
                "error": None,
                **meta,
            }
            status = "OK"
        except Exception as e:
            failures += 1
            result = {
                "id": rid,
                "source": "claude_code_source_discovery_v5",
                "question": question,
                "input": row,
                "rag_retrieve": rag_resp,
                "rag_error": rag_error,
                "discovery": None,
                "error": str(e),
            }
            status = "ERROR"
        append_jsonl(out_path, result)
        cost = result.get("total_cost_usd")
        cost_s = f" cost=${cost:.3f}" if isinstance(cost, (int, float)) else ""
        print(f"[{idx:04d}/{len(rows)}] {status} {rid}{cost_s}", flush=True)

    print(f"wrote: {args.out}")
    print(f"errors: {failures}/{len(rows)}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
