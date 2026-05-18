#!/usr/bin/env python3
"""Create DPO/ORPO-ready preference pairs from validated v5 RAG contracts.

Input rows come from `distill_rag_contract_v5.py`. For each valid RAG contract,
the chosen answer is the teacher-approved answer. A Sonnet/DeepSeek teacher then
creates one plausible rejected answer that exhibits a specific failure mode:
wrong locality, raw URL citation, hallucinated contact, over-refusal,
wrong-language answer, ignored history, generic answer, or unsupported claim.

These pairs are saved separately from SFT rows. The chosen side can be folded
into SFT, but the real value is future preference tuning and eval negatives.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.distill_rag_contract_v5 import call_deepseek, call_meridian, extract_json  # noqa: E402


SYSTEM = """\
You are creating preference-training data for SpeakGov, a Nepal government-service navigator.

Given a user question, conversation history, retrieved source pack, and the approved chosen answer,
create ONE plausible but flawed rejected answer.

Return ONLY valid JSON:
{
  "failure_type": "wrong_source" | "wrong_locality" | "wrong_language" | "hallucinated_contact" |
                  "over_refusal" | "generic_answer" | "ignored_history" | "unsupported_claim" |
                  "raw_url_citation",
  "rejected": "the flawed answer",
  "why_rejected": "short explanation"
}

Rules for the rejected answer:
- It must be realistic: the kind of answer a weak small model might produce.
- It must be clearly worse than the chosen answer.
- It must not contain instructions for illegal harm or personal abuse.
- Preserve the user's broad topic; do not make random nonsense.
- Keep the rejected answer concise.
- If the user wrote in English or Roman Nepali, wrong_language may use Devanagari/Hindi-like text.
- If failure_type is raw_url_citation, include a raw URL instead of [S#] citation.
- If failure_type is over_refusal, refuse even though the chosen answer had supported content.
- If failure_type is hallucinated_contact, invent a plausible phone/email/name not present in sources.
"""


FAILURE_TYPES = [
    "wrong_source",
    "wrong_locality",
    "wrong_language",
    "hallucinated_contact",
    "over_refusal",
    "generic_answer",
    "ignored_history",
    "unsupported_claim",
    "raw_url_citation",
]


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


def compact(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def sources_text(sources: list[dict[str, Any]], limit: int) -> str:
    lines: list[str] = []
    for src in sources[:8]:
        sid = src.get("source_ref") or f"S{src.get('rank')}"
        lines.append(f"[{sid}] {src.get('label') or 'SOURCE'}")
        if src.get("host"):
            lines.append(f"Host: {src.get('host')}")
        if src.get("url"):
            lines.append(f"URL: {src.get('url')}")
        if src.get("title"):
            lines.append(f"Title: {src.get('title')}")
        lines.append(f"Excerpt: {compact(src.get('snippet') or '', limit)}")
        lines.append("")
    return "\n".join(lines).strip()


def history_text(history: list[dict[str, Any]]) -> str:
    if not history:
        return "(none)"
    out = []
    for turn in history[-8:]:
        role = turn.get("role") or "user"
        content = compact(str(turn.get("content") or ""), 800)
        if content:
            out.append(f"{role}: {content}")
    return "\n".join(out) or "(none)"


def pick_failure(rec: dict[str, Any], rng: random.Random) -> str:
    q = (rec.get("question") or "").lower()
    lang = rec.get("question_lang")
    answerability = (rec.get("contract") or {}).get("answerability")
    weighted = ["generic_answer", "unsupported_claim", "raw_url_citation"]
    if answerability in {"answer", "partial"}:
        weighted.extend(["over_refusal", "wrong_source"])
    if rec.get("history"):
        weighted.append("ignored_history")
    if any(w in q for w in ["jiri", "khandbari", "sankhuwasabha", "dolakha", "municipality", "ward"]):
        weighted.append("wrong_locality")
    if any(w in q for w in ["contact", "phone", "officer", "helpdesk", "complaint", "manpower"]):
        weighted.append("hallucinated_contact")
    if lang in {"english", "roman_nepali"}:
        weighted.append("wrong_language")
    return rng.choice(weighted)


def build_prompt(rec: dict[str, Any], failure_type: str, snippet_chars: int) -> str:
    contract = rec.get("contract") or {}
    return "\n".join([
        f"Failure type to create: {failure_type}",
        "",
        f"Question language: {rec.get('question_lang')}",
        f"Conversation history:\n{history_text(rec.get('history') or [])}",
        "",
        f"Latest user question: {rec.get('question')}",
        "",
        f"Approved answerability: {contract.get('answerability')}",
        f"Approved relevant source IDs: {contract.get('relevant_source_ids')}",
        f"Approved missing: {contract.get('missing')}",
        "",
        f"Approved chosen answer:\n{contract.get('answer') or rec.get('answer')}",
        "",
        f"Retrieved sources:\n{sources_text(rec.get('sources') or [], snippet_chars)}",
        "",
        "Return the rejected-answer JSON.",
    ])


def validate_pair(rec: dict[str, Any], pair: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if pair.get("failure_type") not in FAILURE_TYPES:
        issues.append("bad_failure_type")
    rejected = pair.get("rejected")
    chosen = (rec.get("contract") or {}).get("answer") or rec.get("answer")
    if not isinstance(rejected, str) or not rejected.strip():
        issues.append("empty_rejected")
    elif rejected.strip() == (chosen or "").strip():
        issues.append("rejected_equals_chosen")
    if not pair.get("why_rejected"):
        issues.append("missing_why_rejected")
    return issues


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contracts", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--provider", choices=["meridian", "deepseek"], default="meridian")
    ap.add_argument("--model", default="claude-sonnet-4-6")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--snippet-chars", type=int, default=700)
    args = ap.parse_args()

    rows = [r for r in load_jsonl(Path(args.contracts)) if not r.get("validation_issues") and not r.get("error")]
    if args.limit:
        rows = rows[: args.limit]
    out_path = Path(args.out)
    done: set[str] = set()
    if args.resume and out_path.exists():
        done = {str(r.get("id")) for r in load_jsonl(out_path) if r.get("id")}
    elif out_path.exists():
        out_path.unlink()

    rng = random.Random(args.seed)
    failures = 0
    warnings = 0
    for idx, rec in enumerate(rows, 1):
        rec_id = str(rec.get("id") or idx)
        if rec_id in done:
            print(f"[{idx:04d}/{len(rows)}] SKIP {rec_id}", flush=True)
            continue
        failure_type = pick_failure(rec, rng)
        prompt = build_prompt(rec, failure_type, args.snippet_chars)
        try:
            t0 = time.time()
            if args.provider == "meridian":
                raw = call_meridian(SYSTEM, prompt, args.model, args.timeout)
            else:
                raw = call_deepseek(SYSTEM, prompt, args.model, args.timeout)
            pair = extract_json(raw)
            elapsed_ms = int((time.time() - t0) * 1000)
            issues = validate_pair(rec, pair)
        except Exception as e:
            failures += 1
            pair = {"failure_type": failure_type, "rejected": "", "why_rejected": "", "error": str(e)}
            raw = ""
            elapsed_ms = 0
            issues = ["distill_error"]

        if issues:
            warnings += 1
        row = {
            "id": rec_id,
            "source": "v5_preference_pair_teacher",
            "teacher_provider": args.provider,
            "teacher_model": args.model,
            "question": rec.get("question"),
            "history": rec.get("history") or [],
            "question_lang": rec.get("question_lang"),
            "topic": rec.get("topic"),
            "answerability": (rec.get("contract") or {}).get("answerability"),
            "chosen": (rec.get("contract") or {}).get("answer") or rec.get("answer"),
            "rejected": pair.get("rejected"),
            "failure_type": pair.get("failure_type") or failure_type,
            "why_rejected": pair.get("why_rejected"),
            "validation_issues": issues,
            "teacher_ms": elapsed_ms,
            "raw_teacher": raw if issues else None,
        }
        append_jsonl(out_path, row)
        status = "OK" if not issues else "WARN"
        print(f"[{idx:04d}/{len(rows)}] {status} {rec_id} {','.join(issues)}", flush=True)

    print(f"wrote: {args.out}")
    print(f"errors: {failures}/{len(rows)}")
    print(f"validation issues: {warnings}/{len(rows)}")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
