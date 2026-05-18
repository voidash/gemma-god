#!/usr/bin/env python3
"""Distill v6 planner/composer contracts from live RAG retrieval.

v5 exposed source selection and answerability. v6 makes the intended product
behavior explicit: resolve the user's case first, decide whether to ask a
follow-up, route source classes/domains, then compose only source-grounded
facts. This is for training/eval data generation, not for serving directly.

Example:
    python3 scripts/distill_planner_composer_v6.py \
        --base-url http://<k2-tailnet-ip>:8000 \
        --questions eval/service_eval_expanded_v5_seed.jsonl \
        --provider meridian \
        --model claude-sonnet-4-6 \
        --out corpora/sft_v6_planner_composer_contracts.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
from dataclasses import asdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from build_v5_dialogue_contracts import (  # noqa: E402
    REGISTRY_PATH,
    DISTRICTS_PATH,
    expected_domains_for,
    followup_questions_for,
    merge_unique,
    service_rule_missing,
    source_classes_for,
)
from distill_rag_contract_v5 import (  # noqa: E402
    ANSWER_SOURCE_REF_RE,
    SOURCE_ID_RE,
    append_jsonl,
    call_deepseek,
    call_meridian,
    detect_lang,
    extract_json,
    has_hindi_artifact,
    load_jsonl,
    post_json,
    write_jsonl,
    _host_matches,
)
from server.navigator import CaseFrame, resolve_case  # noqa: E402


RAW_URL_RE = re.compile(r"https?://|www\.", re.I)
CHAIN_OF_THOUGHT_RE = re.compile(
    r"\b(thinking process|chain of thought|my reasoning|reasoning:|analysis:|thought:|i think step by step)\b",
    re.I,
)
CJK_THAI_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\u0e00-\u0e7f]")
PHONEISH_RE = re.compile(r"(?:\+?\d[\d\s().-]{5,}\d)")

ANSWERABILITY = {"answer", "partial", "follow_up", "refuse", "off_domain"}
NEXT_ACTIONS = {"answer", "ask_follow_up", "source_discovery", "refuse", "off_domain"}
GAP_TYPES = {"need_source", "need_interview", "need_alias", "need_contact", "need_slot", "other"}


SYSTEM = """\
You are creating supervised training contracts for SpeakGov, a Nepal government-service navigator.

SpeakGov is not a generic RAG Q&A bot. It must:
- resolve/intake the user's case before answering;
- remember details from chat history;
- ask compact follow-up questions when the case is ambiguous;
- route sources based on the user's exact question, location, office, and service;
- include useful contacts when sources support them;
- use named human practical sources when provided and relevant;
- state uncertainty and gaps instead of inventing facts.

Return ONLY valid JSON with this schema:
{
  "schema_version": "planner_composer_v6",
  "case_frame": {
    "service": "service name or null",
    "action": "apply|replace|correct|contact|fee|status|complaint|other|null",
    "location": {
      "country": null,
      "province": null,
      "district": null,
      "municipality": null,
      "ward": null,
      "embassy_or_mission": null
    },
    "case_type": null,
    "person_context": null,
    "known_slots": {},
    "missing_slots": []
  },
  "source_plan": {
    "needed_source_classes": [],
    "relevant_source_ids": [],
    "irrelevant_source_ids": [],
    "source_notes": []
  },
  "answerability": "answer|partial|follow_up|refuse|off_domain",
  "facts": [
    {"claim": "one atomic claim supported by sources", "source_ids": ["S1"]}
  ],
  "contacts": [
    {"name": null, "role": null, "office": null, "phone": null, "email": null, "source_ids": ["S1"], "confidence": "high|medium|low"}
  ],
  "uncertainty": [],
  "gaps": [
    {"type": "need_source|need_interview|need_alias|need_contact|need_slot|other", "description": "specific gap"}
  ],
  "followup_questions": [],
  "recommended_next_action": "answer|ask_follow_up|source_discovery|refuse|off_domain",
  "final_answer": "plain chat answer in the user's language, cited with [S#] for source-backed facts"
}

Rules:
- Use only the provided Sources for factual claims, contacts, fees, dates, offices, names, phone numbers, emails, and document lists.
- Cite source-backed facts with source IDs like [S1]. Never cite raw URLs.
- Do not write raw URLs anywhere in final_answer, facts, contacts, uncertainty, gaps, or notes.
- Do not invent source IDs.
- Do not invent officer names, phone numbers, addresses, fees, deadlines, or document lists.
- If the user asks for an exact contact/name/phone and the sources do not contain it, mark partial and state the gap.
- If the user's case needs missing details before a safe final checklist, answerability must be follow_up or partial, and followup_questions must be a compact checklist.
- A follow-up can still include supported routing/contact context.
- If sources answer only part of the question, answerability must be partial.
- Refuse only when no source meaningfully addresses an in-scope high-risk question or the request is unsafe.
- Harmless off-domain questions get a brief answer plus a scope note; set answerability=off_domain.
- Be location-strict: do not use a local/municipality/DAO source for a different place than the user asked about.
- Prefer the newest/current official source when sources conflict. Treat interviews as practical guidance, not legal authority.
- Match the user's language/script. Never answer in Hindi. For Roman Nepali, use Latin script and avoid Hindi artifacts like "hamare paas", "aap", "nahi", "sakta hai", "kijiye", or "hai".
- Do not include markdown fences or commentary outside JSON.
"""


def source_ref(src: dict[str, Any], idx: int) -> str:
    ref = src.get("source_ref") or f"S{src.get('rank') or idx}"
    return str(ref) if SOURCE_ID_RE.fullmatch(str(ref)) else f"S{idx}"


def compact_text(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def source_pack(retrieve_resp: dict[str, Any], max_snippet_chars: int) -> tuple[str, set[str], dict[str, str], dict[str, str]]:
    lines = ["Sources:"]
    valid_ids: set[str] = set()
    sid_text: dict[str, str] = {}
    sid_host: dict[str, str] = {}
    for idx, src in enumerate(retrieve_resp.get("sources") or [], 1):
        sid = source_ref(src, idx)
        valid_ids.add(sid)
        label = src.get("label") or ("CITIZEN INTERVIEW" if src.get("is_tacit") else "GOV.NP")
        url = src.get("url") or ""
        host = src.get("host") or urllib.parse.urlparse(url).netloc
        title = src.get("title") or ""
        snippet = compact_text(src.get("snippet") or src.get("text") or "", max_snippet_chars)
        sid_text[sid] = " ".join(x for x in [title, snippet] if x)
        sid_host[sid] = (host or "").lower()
        lines.append(f"\n[{sid}] {label}")
        if host:
            lines.append(f"Host: {host}")
        if url:
            lines.append(f"URL: {url}")
        if title:
            lines.append(f"Title: {title}")
        lines.append(f"Excerpt: {snippet}")
    if not valid_ids:
        lines.append("(no candidate sources surfaced)")
    return "\n".join(lines), valid_ids, sid_text, sid_host


def history_text(history: list[dict[str, Any]], limit: int = 8) -> str:
    if not history:
        return "(none)"
    out: list[str] = []
    for turn in history[-limit:]:
        role = str(turn.get("role") or "user")
        content = re.sub(r"\s+", " ", str(turn.get("content") or "")).strip()
        if content:
            out.append(f"{role}: {content}")
    return "\n".join(out) if out else "(none)"


def language_instruction(lang: str) -> str:
    if lang == "devanagari":
        return "Write the final answer and follow-up questions in Devanagari Nepali."
    if lang == "roman_nepali":
        return (
            "Write the final answer and follow-up questions in Roman Nepali using Latin script only. "
            "Do not use Devanagari sentences and do not use Hindi phrasing."
        )
    return "Write the final answer and follow-up questions in English."


def resolve_planner_hint(rec: dict[str, Any]) -> tuple[CaseFrame, dict[str, Any]]:
    frame = resolve_case(
        rec.get("question") or "",
        rec.get("history") or [],
        registry_path=REGISTRY_PATH,
        districts_path=DISTRICTS_PATH,
    )
    extra_missing, extra_questions = service_rule_missing(frame)
    missing_slots = merge_unique(list(frame.missing_slots), extra_missing)
    followups = followup_questions_for(frame, missing_slots, extra_questions) if missing_slots else []
    expected_domains = merge_unique(expected_domains_for(frame), rec.get("expected_domains") or [])
    hint = {
        "resolved_case_frame": asdict(frame),
        "extra_missing_slots": extra_missing,
        "all_missing_slots": missing_slots,
        "suggested_followup_questions": followups,
        "suggested_source_classes": source_classes_for(frame),
        "expected_domains": expected_domains,
    }
    return frame, hint


def iter_source_ids(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    return []


def _str_values(obj: Any) -> list[str]:
    values: list[str] = []
    if isinstance(obj, str):
        values.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            values.extend(_str_values(v))
    elif isinstance(obj, list):
        for v in obj:
            values.extend(_str_values(v))
    return values


def _phone_values(obj: Any) -> list[str]:
    phones: list[str] = []
    for text in _str_values(obj):
        phones.extend(m.group(0).strip() for m in PHONEISH_RE.finditer(text))
    return phones


def _norm_phone(text: str) -> str:
    return re.sub(r"\D+", "", text or "")


def _contains_phone(source_texts: list[str], phone: str) -> bool:
    wanted = _norm_phone(phone)
    if len(wanted) < 6:
        return True
    return any(wanted in _norm_phone(text) for text in source_texts)


def validate_contract(
    contract: dict[str, Any],
    valid_ids: set[str],
    sid_text: dict[str, str],
    sid_host: dict[str, str],
    expected_lang: str,
    expected_domains: list[str],
    planner_hint: dict[str, Any],
) -> list[str]:
    issues: list[str] = []
    if contract.get("schema_version") != "planner_composer_v6":
        issues.append("bad_schema_version")

    answerability = contract.get("answerability")
    if answerability not in ANSWERABILITY:
        issues.append("bad_answerability")

    next_action = contract.get("recommended_next_action")
    if next_action not in NEXT_ACTIONS:
        issues.append("bad_recommended_next_action")

    case_frame = contract.get("case_frame")
    if not isinstance(case_frame, dict):
        issues.append("bad_case_frame")
        case_frame = {}
    location = case_frame.get("location")
    if not isinstance(location, dict):
        issues.append("bad_location")
        location = {}
    missing_slots = case_frame.get("missing_slots")
    if not isinstance(missing_slots, list):
        issues.append("bad_missing_slots")
        missing_slots = []

    source_plan = contract.get("source_plan")
    if not isinstance(source_plan, dict):
        issues.append("bad_source_plan")
        source_plan = {}
    used_sids: set[str] = set()
    for key in ("relevant_source_ids", "irrelevant_source_ids"):
        refs = source_plan.get(key)
        if not isinstance(refs, list):
            issues.append(f"bad_source_plan_{key}")
            continue
        for sid in refs:
            if sid not in valid_ids:
                issues.append(f"unknown_{key}:{sid}")
            elif key == "relevant_source_ids":
                used_sids.add(str(sid))

    facts = contract.get("facts")
    if not isinstance(facts, list):
        issues.append("bad_facts")
        facts = []
    for i, fact in enumerate(facts):
        if not isinstance(fact, dict):
            issues.append(f"bad_fact:{i}")
            continue
        if not str(fact.get("claim") or "").strip():
            issues.append(f"empty_fact_claim:{i}")
        sids = iter_source_ids(fact.get("source_ids"))
        if not sids:
            issues.append(f"bad_fact_source_ids:{i}")
        for sid in sids:
            if sid not in valid_ids:
                issues.append(f"unknown_fact_source:{sid}")
            else:
                used_sids.add(sid)

    contacts = contract.get("contacts")
    if not isinstance(contacts, list):
        issues.append("bad_contacts")
        contacts = []
    for i, contact in enumerate(contacts):
        if not isinstance(contact, dict):
            issues.append(f"bad_contact:{i}")
            continue
        sids = iter_source_ids(contact.get("source_ids"))
        if not sids:
            issues.append(f"bad_contact_source_ids:{i}")
        for sid in sids:
            if sid not in valid_ids:
                issues.append(f"unknown_contact_source:{sid}")
            else:
                used_sids.add(sid)
        phone = contact.get("phone")
        if isinstance(phone, str) and phone.strip():
            source_texts = [sid_text.get(sid, "") for sid in sids if sid in sid_text]
            if source_texts and not _contains_phone(source_texts, phone):
                issues.append(f"contact_phone_not_in_sources:{i}")

    for key in ("uncertainty", "followup_questions"):
        if not isinstance(contract.get(key), list):
            issues.append(f"bad_{key}")
    gaps = contract.get("gaps")
    if not isinstance(gaps, list):
        issues.append("bad_gaps")
        gaps = []
    for i, gap in enumerate(gaps):
        if not isinstance(gap, dict):
            issues.append(f"bad_gap:{i}")
            continue
        if gap.get("type") not in GAP_TYPES:
            issues.append(f"bad_gap_type:{i}")

    followups = contract.get("followup_questions") if isinstance(contract.get("followup_questions"), list) else []
    final_answer = contract.get("final_answer")
    if not isinstance(final_answer, str) or not final_answer.strip():
        issues.append("empty_final_answer")
        final_answer = ""
    for sid in ANSWER_SOURCE_REF_RE.findall(final_answer):
        if sid not in valid_ids:
            issues.append(f"unknown_answer_source:{sid}")
        else:
            used_sids.add(sid)

    if answerability in {"answer", "partial"} and facts and not ANSWER_SOURCE_REF_RE.search(final_answer):
        issues.append("answer_missing_source_ref")
    if answerability == "answer" and (missing_slots or gaps):
        issues.append("answer_has_blocking_missing_or_gaps")
    if answerability == "follow_up":
        if not followups:
            issues.append("followup_without_questions")
        if next_action != "ask_follow_up":
            issues.append("followup_wrong_next_action")
    if next_action == "ask_follow_up" and not followups:
        issues.append("ask_followup_without_questions")
    if answerability == "off_domain" and used_sids:
        issues.append("off_domain_used_sources")
    if answerability == "refuse" and facts:
        issues.append("refuse_has_facts")

    if expected_domains and answerability in {"answer", "partial", "follow_up"} and used_sids:
        if not any(_host_matches(sid_host.get(sid, ""), expected_domains) for sid in used_sids):
            issues.append("expected_domain_missing")
        for sid in sorted(used_sids):
            host = sid_host.get(sid, "")
            if host and not _host_matches(host, expected_domains):
                issues.append(f"unexpected_domain_source:{sid}:{host}")

    for path_name, obj in (
        ("final_answer", final_answer),
        ("facts", facts),
        ("contacts", contacts),
        ("uncertainty", contract.get("uncertainty")),
        ("gaps", gaps),
        ("followup_questions", followups),
        ("source_notes", source_plan.get("source_notes")),
    ):
        for text in _str_values(obj):
            if RAW_URL_RE.search(text):
                issues.append(f"raw_url_in_{path_name}")
                break
            if CHAIN_OF_THOUGHT_RE.search(text):
                issues.append(f"chain_of_thought_in_{path_name}")
                break
            if CJK_THAI_RE.search(text):
                issues.append(f"foreign_script_in_{path_name}")
                break

    if final_answer and not _answer_matches_lang(final_answer, expected_lang):
        issues.append("answer_language_mismatch")
    if final_answer and has_hindi_artifact(final_answer, expected_lang):
        issues.append("answer_hindi_artifact")
    for question in followups:
        if not isinstance(question, str):
            continue
        if not _answer_matches_lang(question, expected_lang):
            issues.append("followup_language_mismatch")
        if has_hindi_artifact(question, expected_lang):
            issues.append("followup_hindi_artifact")

    source_texts_all = list(sid_text.values())
    for phone in _phone_values(final_answer):
        if not _contains_phone(source_texts_all, phone):
            issues.append("answer_phone_not_in_sources")
            break

    suggested_missing = set(planner_hint.get("all_missing_slots") or [])
    if suggested_missing and answerability == "answer":
        issues.append("deterministic_missing_but_answer")
    return sorted(set(issues))


def _answer_matches_lang(answer: str, expected_lang: str) -> bool:
    # Inline wrapper keeps this script robust against v5 helper changes.
    if expected_lang == "devanagari":
        return bool(re.search(r"[\u0900-\u097F]", answer))
    if expected_lang == "roman_nepali":
        return not bool(re.search(r"[\u0900-\u097F]", answer))
    if expected_lang == "english":
        deva = len(re.findall(r"[\u0900-\u097F]", answer))
        latin = sum(1 for c in answer if c.isascii() and c.isalpha())
        return latin >= max(10, deva)
    return True


def distill_one(
    base_url: str,
    rec: dict[str, Any],
    provider: str,
    model: str,
    top_k_tacit: int,
    top_k_gov: int,
    timeout: int,
    max_snippet_chars: int,
) -> dict[str, Any]:
    frame, planner_hint = resolve_planner_hint(rec)
    retrieve_payload = {
        "question": frame.retrieval_query or frame.resolved_question or rec["question"],
        "top_k_tacit": int(rec.get("top_k_tacit", top_k_tacit)),
        "top_k_gov": int(rec.get("top_k_gov", top_k_gov)),
        "history": rec.get("history") or [],
    }
    retrieve_resp = post_json(f"{base_url.rstrip('/')}/retrieve", retrieve_payload, timeout=timeout)
    sources_text, valid_ids, sid_text, sid_host = source_pack(retrieve_resp, max_snippet_chars)
    question_lang = rec.get("question_lang") or frame.language or detect_lang(rec["question"])

    expected_domains = planner_hint.get("expected_domains") or []
    expected_domains_text = ""
    if expected_domains:
        expected_domains_text = (
            "Expected authoritative domains for this seed/case: "
            f"{', '.join(expected_domains)}\n"
            "If retrieved local sources are from a different office/place, mark them irrelevant or partial.\n\n"
        )

    user = (
        f"Conversation history:\n{history_text(rec.get('history') or [])}\n\n"
        f"Latest user question: {rec['question'].strip()}\n\n"
        f"Question language: {question_lang}\n"
        f"Language instruction: {language_instruction(question_lang)}\n\n"
        f"Deterministic planner hint:\n{json.dumps(planner_hint, ensure_ascii=False, indent=2)}\n\n"
        f"Retrieval request used:\n{json.dumps(retrieve_payload, ensure_ascii=False)}\n\n"
        f"Retrieval quality:\n{json.dumps(retrieve_resp.get('quality') or {}, ensure_ascii=False)}\n\n"
        f"{expected_domains_text}"
        f"{sources_text}\n\n"
        "Return the v6 JSON contract only."
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
        expected_domains=expected_domains,
        planner_hint=planner_hint,
    )
    return {
        "id": rec.get("id"),
        "source": "v6_planner_composer_teacher",
        "teacher_provider": provider,
        "teacher_model": model,
        "question": rec["question"],
        "history": rec.get("history") or [],
        "question_lang": question_lang,
        "topic": rec.get("topic") or rec.get("service") or retrieve_resp.get("quality", {}).get("topic"),
        "seed_expected_behavior": rec.get("expected_behavior"),
        "seed_expected_domains": rec.get("expected_domains") or [],
        "planner_hint": planner_hint,
        "retrieve_payload": retrieve_payload,
        "retrieve_quality": retrieve_resp.get("quality"),
        "sources": retrieve_resp.get("sources") or [],
        "contract": contract,
        "answer": contract.get("final_answer"),
        "validation_issues": issues,
        "teacher_ms": teacher_ms,
        "raw_teacher": raw if issues else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--questions", default="eval/service_eval_expanded_v5_seed.jsonl")
    ap.add_argument("--out", default="corpora/sft_v6_planner_composer_contracts.jsonl")
    ap.add_argument("--provider", choices=["meridian", "deepseek"], default="meridian")
    ap.add_argument("--model", default="")
    ap.add_argument("--top-k-tacit", type=int, default=4)
    ap.add_argument("--top-k-gov", type=int, default=8)
    ap.add_argument("--timeout", type=int, default=150)
    ap.add_argument("--offset", type=int, default=0)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-snippet-chars", type=int, default=1000)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--fail-on-issues", action="store_true")
    args = ap.parse_args()

    model = args.model
    if not model:
        model = "claude-sonnet-4-6" if args.provider == "meridian" else "deepseek-v4-flash"

    rows = load_jsonl(Path(args.questions))
    if args.offset:
        rows = rows[args.offset :]
    if args.limit:
        rows = rows[: args.limit]
    if not rows:
        print("no questions to distill", file=sys.stderr)
        return 1

    out_path = Path(args.out)
    done_ids: set[str] = set()
    out: list[dict[str, Any]] = []
    if args.resume and out_path.exists():
        out = load_jsonl(out_path)
        done_ids = {str(r.get("id")) for r in out if r.get("id")}
    elif out_path.exists():
        out_path.unlink()

    failures = 0
    for i, rec in enumerate(rows, 1):
        rec_id = str(rec.get("id") or "")
        if rec_id and rec_id in done_ids:
            print(f"[{i:03d}/{len(rows)}] SKIP {rec.get('id')} already_done", flush=True)
            continue
        try:
            distilled = distill_one(
                args.base_url,
                rec,
                provider=args.provider,
                model=model,
                top_k_tacit=args.top_k_tacit,
                top_k_gov=args.top_k_gov,
                timeout=args.timeout,
                max_snippet_chars=args.max_snippet_chars,
            )
        except Exception as e:
            failures += 1
            distilled = {
                "id": rec.get("id"),
                "question": rec.get("question"),
                "source": "v6_planner_composer_teacher",
                "teacher_provider": args.provider,
                "teacher_model": model,
                "error": str(e),
                "validation_issues": ["distill_error"],
            }
            print(f"[{i:03d}/{len(rows)}] ERROR {rec.get('id')} {e}", flush=True)
        out.append(distilled)
        append_jsonl(out_path, distilled)
        status = "OK" if not distilled.get("validation_issues") else "WARN"
        issues = ",".join(distilled.get("validation_issues") or [])
        print(f"[{i:03d}/{len(rows)}] {status} {rec.get('id')} {issues}", flush=True)

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
