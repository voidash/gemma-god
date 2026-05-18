#!/usr/bin/env python3
"""Build v5 dialogue-planner contracts from service-navigation seed cases.

This script does not call a teacher model and does not retrieve documents. It
turns hand-authored dialogue seeds into inspectable planner supervision:
resolved slots, missing slots, source-routing hints, follow-up questions, and
the deterministic user-facing follow-up/ack/off-domain answer where applicable.

The goal is to train and evaluate the "questioning machine" separately from the
RAG composer. RAG answer contracts still come from `distill_rag_contract_v5.py`.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.navigator import CaseFrame, followup_answer, resolve_case  # noqa: E402


REGISTRY_PATH = ROOT / "corpora" / "source_registry.jsonl"
DISTRICTS_PATH = ROOT / "corpora" / "nepal_districts.jsonl"

LATIN_TO_DEVANAGARI_SAFE_RE = re.compile(r"[\u0900-\u097f]")


SERVICE_SLOT_RULES: tuple[dict[str, Any], ...] = (
    {
        "service": "passport",
        "question_any": ("child", "minor", "nabalak", "नाबालक", "बच्चा"),
        "missing": ("applicant_age_or_minor_context",),
        "questions": {
            "english": "Is the applicant a minor, and are both parents/guardians available with their citizenship/passport documents?",
            "roman_nepali": "Applicant minor ho? Dui parent/guardian ko citizenship/passport documents available cha?",
            "devanagari": "आवेदक नाबालक हो? दुवै अभिभावकको नागरिकता/राहदानी कागजात उपलब्ध छन्?",
        },
    },
    {
        "service": "land",
        "question_any": ("tiro", "tax", "revenue", "malpot", "तिरो", "कर", "मालपोत"),
        "requires_location": True,
        "missing": ("municipality_or_district",),
        "questions": {
            "english": "Which district or municipality is the land in?",
            "roman_nepali": "Jagga kun district ya municipality ma cha?",
            "devanagari": "जग्गा कुन जिल्ला वा नगर/गाउँपालिकामा पर्छ?",
        },
    },
    {
        "service": "municipality_service",
        "action": "contact",
        "question_any": ("officer", "staff", "contact person", "phone", "mayor", "helpdesk", "अधिकारी", "सम्पर्क", "फोन"),
        "requires_location": True,
        "missing": ("municipality_or_district",),
        "questions": {
            "english": "Which office or section do you need: mayor/chair, information officer, ward office, or service helpdesk?",
            "roman_nepali": "Kun contact chahiyo: mayor/chair, information officer, ward office, ki service helpdesk?",
            "devanagari": "कुन सम्पर्क चाहिएको हो: नगर/गाउँ प्रमुख, सूचना अधिकारी, वडा कार्यालय, वा सेवा हेल्पडेस्क?",
        },
    },
)

SERVICE_SOURCE_CLASSES: dict[str, dict[str, list[str]]] = {
    "contact": {
        "primary": ["office_contact_page", "information_officer_page", "staff_directory", "verified_officer_interview"],
        "secondary": ["general_notice", "office_profile"],
    },
    "apply": {
        "primary": ["citizen_charter", "service_page", "latest_circular", "form_instruction"],
        "secondary": ["verified_staff_interview", "verified_citizen_interview"],
    },
    "replace": {
        "primary": ["service_page", "citizen_charter", "latest_circular"],
        "secondary": ["verified_staff_interview", "verified_citizen_interview"],
    },
    "fee": {
        "primary": ["latest_fee_table", "dated_notice", "service_page"],
        "secondary": ["citizen_charter"],
    },
    "default": {
        "primary": ["service_page", "citizen_charter", "official_directory"],
        "secondary": ["verified_human_practical_note"],
    },
}


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


def contains_any(text: str, markers: tuple[str, ...]) -> bool:
    text_l = (text or "").lower()
    return any(marker.lower() in text_l for marker in markers)


def merge_unique(values: list[str], additions: list[str] | tuple[str, ...]) -> list[str]:
    out = list(values)
    for value in additions:
        if value and value not in out:
            out.append(value)
    return out


def service_rule_missing(frame: CaseFrame) -> tuple[list[str], list[str]]:
    """Return extra planner slots/questions not yet modeled by navigator.py."""
    missing: list[str] = []
    questions: list[str] = []
    text = frame.resolved_question or frame.raw_question
    for rule in SERVICE_SLOT_RULES:
        if rule.get("service") != frame.service:
            continue
        if rule.get("action") and rule.get("action") != frame.action:
            continue
        if rule.get("question_any") and not contains_any(text, tuple(rule["question_any"])):
            continue
        if rule.get("requires_location") and (frame.district or frame.municipality or frame.ward):
            continue
        missing = merge_unique(missing, tuple(rule.get("missing") or ()))
        # The canonical follow-up wording is produced from missing slot IDs
        # below, so these rules only add planner slots. Keeping wording in one
        # place avoids duplicate asks such as two location questions.
    return missing, questions


def decision_for(frame: CaseFrame, missing_slots: list[str]) -> str:
    if frame.off_domain_answer:
        return "off_domain_light_answer"
    if frame.memory_only:
        return "ack_memory"
    if missing_slots:
        return "partial_answer_plus_followup"
    if frame.action == "contact":
        return "contact_handoff_or_retrieve"
    return "retrieve_then_answer"


def source_classes_for(frame: CaseFrame) -> dict[str, list[str]]:
    action_key = frame.action or "default"
    if action_key not in SERVICE_SOURCE_CLASSES:
        action_key = "default"
    source_classes = {
        "primary": list(SERVICE_SOURCE_CLASSES[action_key]["primary"]),
        "secondary": list(SERVICE_SOURCE_CLASSES[action_key]["secondary"]),
    }
    if frame.service in {"citizenship", "vital_registration"} and frame.municipality:
        source_classes["primary"] = merge_unique(source_classes["primary"], ["local_municipality_service_page", "ward_contact"])
    if frame.service == "foreign_employment" and frame.action == "contact":
        source_classes["primary"] = merge_unique(source_classes["primary"], ["complaint_channel", "department_helpdesk"])
    if frame.service == "passport" and contains_any(frame.raw_question, ("abroad", "qatar", "embassy", "lost")):
        source_classes["primary"] = merge_unique(source_classes["primary"], ["embassy_contact_page", "mission_notice"])
    return source_classes


def expected_domains_for(frame: CaseFrame) -> list[str]:
    domains = list(frame.expected_domains)
    raw = frame.raw_question.lower()
    if frame.service == "passport" and contains_any(raw, ("abroad", "qatar", "embassy", "lost")):
        domains = merge_unique(domains, ("mofa.gov.np", "nepalembassy.gov.np"))
    return domains


def followup_questions_for(frame: CaseFrame, missing_slots: list[str], extra_questions: list[str]) -> list[str]:
    questions: list[str] = []
    lang = frame.language
    if "service" in missing_slots:
        questions.append({
            "devanagari": "कुन सरकारी सेवा वा कागजातबारे सोध्नुभएको हो?",
            "roman_nepali": "Kun government service ya document ko barema sodhnu bhayeko ho?",
        }.get(lang, "Which government service or document is this about?"))
    if "municipality_or_district" in missing_slots:
        questions.append({
            "devanagari": "कुन जिल्ला वा नगर/गाउँपालिका हो?",
            "roman_nepali": "Kun district ya municipality/gaupalika ho?",
        }.get(lang, "Which district or municipality/rural municipality is this for?"))
    if "municipality_or_ward" in missing_slots:
        questions.append({
            "devanagari": "कुन नगर/गाउँपालिका र वडा हो?",
            "roman_nepali": "Kun municipality/gaupalika ra ward ho?",
        }.get(lang, "Which municipality/rural municipality and ward is this for?"))
    if "citizenship_case_type" in missing_slots:
        questions.append({
            "devanagari": "नयाँ नागरिकता, प्रतिलिपि/हराएको, संशोधन, नाबालक, वा अर्को केस हो?",
            "roman_nepali": "Yo first-time, duplicate/lost, correction, minor, ki aru case ho?",
        }.get(lang, "Is this first-time citizenship, duplicate/lost, correction, minor, or another case?"))
    if "applicant_age_or_minor_context" in missing_slots:
        questions.append({
            "devanagari": "आवेदक नाबालक हो? दुवै अभिभावकका कागजात उपलब्ध छन्?",
            "roman_nepali": "Applicant minor ho? Dui parent/guardian ko documents available cha?",
        }.get(lang, "Is the applicant a minor, and are both parents/guardians' documents available?"))
    return merge_unique(questions, extra_questions)


def assistant_text_for(
    frame: CaseFrame,
    decision: str,
    missing_slots: list[str],
    followup_questions: list[str],
) -> str:
    if decision == "off_domain_light_answer" and frame.off_domain_answer:
        return frame.off_domain_answer
    if decision == "ack_memory":
        if frame.language == "devanagari":
            return "ठीक छ। अर्को सरकारी सेवा प्रश्नमा यो स्थान विवरण प्रयोग गर्छु।"
        if frame.language == "roman_nepali":
            return "Thik cha. Aba next government-service question ma yo location detail use garchu."
        return "Got it. I will use that location for the next government-service question."
    if decision == "partial_answer_plus_followup":
        built_in = followup_answer(frame, gov_results=[])
        if built_in:
            return built_in
        service_label = (frame.service or "this service").replace("_", " ")
        if frame.language == "devanagari":
            lines = [f"यसका लागि केही विवरण चाहिन्छ, किनकि {service_label} केसअनुसार फरक पर्छ।"]
        elif frame.language == "roman_nepali":
            lines = [f"Yo answer case anusar farak parcha, so short details chahinchha."]
        else:
            lines = [f"I need a few details because {service_label} depends on the exact case."]
        lines.extend(f"{idx}. {question}" for idx, question in enumerate(followup_questions, 1))
        if frame.expected_domains:
            if frame.language == "devanagari":
                lines.append("अन्तिम checklist दिनुअघि यो केससँग मिल्ने आधिकारिक स्रोत प्रयोग गर्छु।")
            elif frame.language == "roman_nepali":
                lines.append("Final checklist dinu aghi yo case sanga milne official source use garchu.")
            else:
                lines.append("I will use the relevant official source for this case before giving the final checklist.")
        return "\n".join(lines)
    return ""


def frame_public_dict(frame: CaseFrame, missing_slots: list[str], decision: str, followup_questions: list[str]) -> dict[str, Any]:
    data = asdict(frame)
    data["missing_slots"] = missing_slots
    data["needs_followup"] = bool(missing_slots)
    data["decision"] = decision
    data["followup_questions"] = followup_questions
    return data


def validate_record(seed: dict[str, Any], contract: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    expected_decision = seed.get("expected_decision")
    if expected_decision and contract.get("decision") != expected_decision:
        issues.append(f"decision:{contract.get('decision')}!=expected:{expected_decision}")
    expected_service = seed.get("expected_service")
    service = contract.get("case_frame", {}).get("service")
    if expected_service and service != expected_service:
        issues.append(f"service:{service}!=expected:{expected_service}")
    expected_missing = seed.get("expected_missing_slots") or []
    actual_missing = contract.get("case_frame", {}).get("missing_slots") or []
    for slot in expected_missing:
        if slot not in actual_missing:
            issues.append(f"missing_slot_absent:{slot}")
    for domain in seed.get("expected_domains") or []:
        if domain not in (contract.get("expected_domains") or []):
            issues.append(f"expected_domain_absent:{domain}")
    if contract.get("decision") == "partial_answer_plus_followup" and not contract.get("followup_questions"):
        issues.append("followup_decision_without_questions")
    answer = contract.get("assistant_answer") or ""
    if contract.get("language") in {"english", "roman_nepali"} and len(LATIN_TO_DEVANAGARI_SAFE_RE.findall(answer)) > 15:
        issues.append("wrong_script_in_assistant_answer")
    return issues


def build_contract(seed: dict[str, Any]) -> dict[str, Any]:
    frame = resolve_case(
        seed.get("question") or "",
        seed.get("history") or [],
        registry_path=REGISTRY_PATH,
        districts_path=DISTRICTS_PATH,
    )
    extra_missing, extra_questions = service_rule_missing(frame)
    missing_slots = merge_unique(list(frame.missing_slots), extra_missing)
    decision = decision_for(frame, missing_slots)
    followup_questions = followup_questions_for(frame, missing_slots, extra_questions) if missing_slots else []
    assistant_answer = assistant_text_for(frame, decision, missing_slots, followup_questions)
    expected_domains = expected_domains_for(frame)
    contract = {
        "id": seed.get("id"),
        "question": seed.get("question"),
        "history": seed.get("history") or [],
        "language": frame.language,
        "decision": decision,
        "case_frame": frame_public_dict(frame, missing_slots, decision, followup_questions),
        "retrieval_query": frame.retrieval_query,
        "expected_domains": expected_domains,
        "seed_expected_domains": seed.get("expected_domains") or [],
        "source_classes": source_classes_for(frame),
        "followup_questions": followup_questions,
        "assistant_answer": assistant_answer,
        "gaps": frame.gaps,
        "seed_notes": seed.get("notes"),
        "priority": seed.get("priority"),
    }
    contract["validation_issues"] = validate_record(seed, contract)
    return contract


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", default="eval/service_dialogue_v5_seed.jsonl")
    ap.add_argument("--out", default="corpora/sft_v5_dialogue_contract_seed.jsonl")
    ap.add_argument("--fail-on-issues", action="store_true")
    args = ap.parse_args()

    seed_rows = load_jsonl(ROOT / args.seed)
    contracts = [build_contract(row) for row in seed_rows]
    write_jsonl(ROOT / args.out, contracts)

    issue_rows = [row for row in contracts if row.get("validation_issues")]
    print("=== v5 dialogue contract build ===")
    print(f"seed rows: {len(seed_rows)}")
    print(f"contracts: {len(contracts)}")
    print(f"issue rows: {len(issue_rows)}")
    by_decision: dict[str, int] = {}
    for row in contracts:
        by_decision[row["decision"]] = by_decision.get(row["decision"], 0) + 1
    for decision, count in sorted(by_decision.items()):
        print(f"  {decision}: {count}")
    if issue_rows:
        for row in issue_rows:
            print(f"ISSUE {row.get('id')}: {', '.join(row.get('validation_issues') or [])}")
        if args.fail_on_issues:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
