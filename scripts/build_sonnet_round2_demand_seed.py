#!/usr/bin/env python3
"""Build a Sonnet RAG-contract seed from citizen demand rows.

The demand pool contains noisy Reddit-derived text. This script keeps the
realistic phrasing, but only uses rows already classified as actionable
questions. It also avoids placeholder "authority" labels in expected domains,
because the RAG contract validator treats expected domains strictly.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


ACTIONABLE_CLASSES = {"yes_procedure", "yes_info"}

CATEGORY_TO_SERVICE = {
    "birth_registration": "vital_registration",
    "business": "company_registration",
    "citizenship": "citizenship",
    "driving_license": "driving_license",
    "education": "education",
    "land": "land",
    "pan_vat": "pan_tax",
    "passport": "passport",
    "police": "police",
    "tax": "tax_customs",
    "visa_immigration": "visa_immigration",
}

SERVICE_TO_TOPIC = {
    "company_registration": "company_registration",
    "driving_license": "driving_license",
    "education": "education",
    "foreign_employment": "foreign_employment",
    "municipality_service": "municipality_contact",
    "pan_tax": "pan_tax",
    "tax_customs": "tax_customs",
    "vital_registration": "vital_registration",
    "visa_immigration": "immigration",
}

PLACEHOLDER_AUTHORITY_RE = re.compile(
    r"\b("
    r"district administration offices|local municipality websites|"
    r"province transport office websites|malpot offices|hello sarkar|"
    r"relevant ministry/department"
    r")\b",
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


def used_demand_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    used: set[str] = set()
    for row in load_jsonl(path):
        did = row.get("demand_id")
        if did:
            used.add(str(did))
    return used


def clean_question(text: str, limit: int) -> str:
    text = re.sub(r"https?://\S+", " ", text or "")
    text = re.sub(r"\[removed\]|\[deleted\]", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text

    cut = text[:limit].rstrip()
    # Prefer ending at a natural sentence/question boundary, but do not cut too
    # aggressively; the messy details are useful resolver supervision.
    boundary = max(cut.rfind(x) for x in [".", "?", "!", "।"])
    if boundary >= int(limit * 0.55):
        cut = cut[: boundary + 1]
    return cut.rstrip() + " ..."


def question_lang(row: dict[str, Any], question: str) -> str:
    lang = row.get("language")
    if lang == "devanagari":
        return "devanagari"
    if lang in {"roman_nepali", "code_mixed"}:
        return "roman_nepali"
    deva = sum(1 for c in question if "ऀ" <= c <= "ॿ")
    latin = sum(1 for c in question if c.isascii() and c.isalpha())
    if deva > latin * 0.5:
        return "devanagari"
    return "roman_nepali"


def concrete_domains(domains: list[str]) -> list[str]:
    out: list[str] = []
    for raw in domains or []:
        dom = str(raw).strip().lower()
        if not dom or PLACEHOLDER_AUTHORITY_RE.search(dom):
            continue
        dom = re.sub(r"^https?://", "", dom).split("/")[0]
        if "." not in dom or " " in dom:
            continue
        if dom not in out:
            out.append(dom)
    return out


def infer_extra_domains(row: dict[str, Any]) -> list[str]:
    text = " ".join(
        str(row.get(k) or "")
        for k in ["raw_query", "canonical_query", "category", "rationale"]
    ).lower()
    extras: list[str] = []

    def add(*domains: str) -> None:
        for domain in domains:
            if domain not in extras:
                extras.append(domain)

    if re.search(r"\b(vote|voter|election|मतदाता|भोट)\b", text):
        add("election.gov.np")
    if re.search(r"\b(mobile|phone|sim|ncell|ntc|mdms|telecom)\b", text):
        add("nta.gov.np")
    if re.search(r"\b(customs|bhansar|भन्सार|import|duty|mdms|mobile)\b", text):
        add("customs.gov.np")
    if re.search(r"\b(parking|newroad|bir hospital|महानगर)\b", text):
        add("kathmandu.gov.np")
    if re.search(r"\b(tms|demat|kyc|broker)\b", text):
        add("sebon.gov.np")
    if re.search(r"\b(saudi|ksa|embassy|mofa|foreign affairs|परराष्ट्र)\b", text):
        add("mofa.gov.np")
    if re.search(r"\b(work permit|labor permit|labour permit|foreign emp|dofe|श्रम)\b", text):
        add("dofe.gov.np", "feb.gov.np")
    if re.search(r"\b(vaccine|covid|hospital|स्वास्थ्य)\b", text):
        add("mohp.gov.np", "edcd.gov.np")
    if re.search(r"\b(forest|रुख|वन कार्यालय)\b", text):
        add("mofe.gov.np", "dofsc.gov.np")
    if re.search(r"\b(youtube|channel|media|च्यानल)\b", text):
        add("doind.gov.np")
    if re.search(r"\b(tu|tribhuvan|transcript|ascol)\b", text):
        add("tuexam.edu.np", "tu.edu.np")
    return extras


def service_for(row: dict[str, Any]) -> str:
    category = str(row.get("category") or "other")
    text = " ".join(str(row.get(k) or "") for k in ["raw_query", "canonical_query"]).lower()
    if category == "other":
        if re.search(r"\b(vote|voter|election|मतदाता|भोट)\b", text):
            return "election"
        if re.search(r"\b(mobile|phone|sim|ncell|ntc|mdms|telecom)\b", text):
            return "telecom"
        if re.search(r"\b(customs|bhansar|भन्सार|import|duty)\b", text):
            return "tax_customs"
        if re.search(r"\b(embassy|mofa|saudi|ksa|workers|परराष्ट्र)\b", text):
            return "foreign_employment"
        if re.search(r"\b(work permit|labor permit|labour permit|foreign emp|dofe|श्रम)\b", text):
            return "foreign_employment"
        if re.search(r"\b(vaccine|covid|hospital|स्वास्थ्य)\b", text):
            return "health"
        if re.search(r"\b(forest|रुख|वन कार्यालय)\b", text):
            return "forest"
        if re.search(r"\b(youtube|channel|media|च्यानल)\b", text):
            return "media_registration"
        if re.search(r"\b(parking|municipal|ward|महानगर)\b", text):
            return "municipality_service"
    return CATEGORY_TO_SERVICE.get(category, category if category != "other" else "government_service")


def build_rows(
    demand_rows: list[dict[str, Any]],
    used_ids: set[str],
    *,
    include_no_format: bool,
    max_rows: int,
    question_limit: int,
) -> list[dict[str, Any]]:
    allowed = set(ACTIONABLE_CLASSES)
    if include_no_format:
        allowed.add("no_format")

    out: list[dict[str, Any]] = []
    for row in demand_rows:
        did = str(row.get("demand_id") or "")
        if not did or did in used_ids:
            continue
        cls = row.get("class")
        if cls not in allowed:
            continue
        if cls == "no_format" and row.get("category") == "other":
            continue
        question = clean_question(str(row.get("raw_query") or row.get("canonical_query") or ""), question_limit)
        if not question:
            continue
        service = service_for(row)
        topic = SERVICE_TO_TOPIC.get(service, service)
        extra_domains = infer_extra_domains(row)
        expected_domains = concrete_domains(row.get("suggested_authority_domains") or [])
        # "other" demand rows often carry generic placeholders like OPMCM /
        # Hello Sarkar. When we infer a concrete authority, prefer that so the
        # distillation validator does not bless generic source routing.
        if row.get("category") == "other" and extra_domains:
            expected_domains = [d for d in expected_domains if d not in {"opmcm.gov.np"}]
        for domain in extra_domains:
            if domain not in expected_domains:
                expected_domains.append(domain)
        if expected_domains == ["opmcm.gov.np"]:
            expected_domains = []

        out.append(
            {
                "id": f"round2_demand_{did}",
                "service": service,
                "topic": topic,
                "question": question,
                "question_lang": question_lang(row, question),
                "expected_behavior": "answer_or_partial",
                "expected_domains": expected_domains,
                "priority": "p1" if cls in ACTIONABLE_CLASSES else "p2",
                "notes": (
                    f"Sonnet Round 2 citizen-demand seed from {row.get('category')}: "
                    f"{row.get('canonical_query')}"
                ),
                "demand_id": did,
                "raw_query": row.get("raw_query"),
                "canonical_query": row.get("canonical_query"),
                "demand_class": cls,
                "demand_weight": row.get("weight"),
            }
        )

    out.sort(key=lambda r: (-float(r.get("demand_weight") or 0), r["topic"], r["id"]))
    if max_rows:
        out = out[:max_rows]
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demand", default="eval/citizen_query_demand_seed.jsonl")
    ap.add_argument("--exclude-used", default="eval/service_eval_v5_pilot100.jsonl")
    ap.add_argument("--out", default="eval/round2_sonnet_demand85_20260513.jsonl")
    ap.add_argument("--max-rows", type=int, default=0)
    ap.add_argument("--question-limit", type=int, default=700)
    ap.add_argument("--include-no-format", action="store_true")
    args = ap.parse_args()

    demand_rows = load_jsonl(Path(args.demand))
    rows = build_rows(
        demand_rows,
        used_demand_ids(Path(args.exclude_used)),
        include_no_format=args.include_no_format,
        max_rows=args.max_rows,
        question_limit=args.question_limit,
    )
    write_jsonl(Path(args.out), rows)

    print(f"wrote: {args.out}")
    print(f"rows: {len(rows)}")
    print("topics:")
    for topic, n in Counter(r["topic"] for r in rows).most_common():
        print(f"  {topic}: {n}")
    print("langs:")
    for lang, n in Counter(r["question_lang"] for r in rows).most_common():
        print(f"  {lang}: {n}")
    no_expected = sum(1 for r in rows if not r.get("expected_domains"))
    print(f"without expected_domains: {no_expected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
