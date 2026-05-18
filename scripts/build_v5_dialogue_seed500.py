#!/usr/bin/env python3
"""Generate a 500-row v5 dialogue-planner seed set.

The seed is intentionally template-based and expectation-heavy. It is not final
SFT data by itself; it is an audit input for `build_v5_dialogue_contracts.py`.
Rows cover resolver/intake behavior: follow-up decisions, memory carryover,
question-dependent source routing, contact handoff, and language/script control.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.navigator import dao_domain_for_district  # noqa: E402


DISTRICTS = [
    ("sankhuwasabha", "Sankhuwasabha"),
    ("dolakha", "Dolakha"),
    ("kathmandu", "Kathmandu"),
    ("lalitpur", "Lalitpur"),
    ("bhaktapur", "Bhaktapur"),
    ("kaski", "Kaski"),
    ("chitwan", "Chitwan"),
    ("tanahu", "Tanahu"),
    ("solukhumbu", "Solukhumbu"),
]

MUNICIPALITIES = [
    {"key": "jiri", "name": "Jiri", "domain": "jirimun.gov.np", "district": "dolakha"},
    {"key": "khandbari", "name": "Khandbari", "domain": "khandbarimun.gov.np", "district": "sankhuwasabha"},
]

SERVICE_DOMAINS = {
    "passport": ["nepalpassport.gov.np"],
    "passport_abroad": ["nepalpassport.gov.np", "mofa.gov.np", "nepalembassy.gov.np"],
    "vital_registration": ["donidcr.gov.np"],
    "pan_tax": ["ird.gov.np"],
    "driving_license": ["dotm.gov.np", "transportmanagement.gov.np"],
    "police_clearance": ["nepalpolice.gov.np"],
    "foreign_employment": ["dofe.gov.np", "feb.gov.np", "moless.gov.np"],
    "land": ["dolma.gov.np", "molcpa.gov.np"],
    "national_id": ["donidcr.gov.np"],
}


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def uniq(values: list[str]) -> list[str]:
    return list(dict.fromkeys(v for v in values if v))


def dao_domains(district_key: str) -> list[str]:
    return [dao_domain_for_district(district_key) or f"dao{district_key}.moha.gov.np"]


def add(
    rows: list[dict[str, Any]],
    *,
    id: str,
    question: str,
    decision: str,
    service: str | None = None,
    missing: list[str] | None = None,
    domains: list[str] | None = None,
    history: list[dict[str, str]] | None = None,
    priority: str = "p1",
    notes: str = "",
) -> None:
    rows.append({
        "id": id,
        "question": question,
        "history": history or [],
        "expected_decision": decision,
        "expected_missing_slots": missing or [],
        **({"expected_service": service} if service else {}),
        "expected_domains": domains or [],
        "priority": priority,
        "notes": notes,
    })


def build_rows(limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    # Citizenship: district known, but municipality/ward and case type still matter.
    citizenship_qs = [
        ("en", "How to get citizenship in {district}?"),
        ("en", "What is the process for nagarikta in {district}?"),
        ("roman", "{district_l} ma nagarikta banauna k garne?"),
        ("roman", "{district_l} ko citizenship banauna kaha jane?"),
        ("ne", "{district_np} मा नागरिकता कसरी बनाउने?"),
    ]
    district_np = {
        "sankhuwasabha": "संखुवासभा",
        "dolakha": "दोलखा",
        "kathmandu": "काठमाडौं",
        "lalitpur": "ललितपुर",
        "bhaktapur": "भक्तपुर",
        "kaski": "कास्की",
        "chitwan": "चितवन",
        "tanahu": "तनहुँ",
        "solukhumbu": "सोलुखुम्बु",
    }
    for dkey, dname in DISTRICTS:
        domains = ["moha.gov.np", *dao_domains(dkey)]
        for lang, tmpl in citizenship_qs:
            add(
                rows,
                id=f"dlg500_citizenship_ambiguous_{dkey}_{lang}_{len(rows)}",
                question=tmpl.format(district=dname, district_l=dkey, district_np=district_np[dkey]),
                decision="partial_answer_plus_followup",
                service="citizenship",
                missing=["municipality_or_ward", "citizenship_case_type"],
                domains=domains,
                priority="p0",
                notes="District alone is not enough for a safe citizenship checklist.",
            )

    # Memory: user gives location first, then asks a short service question.
    for muni in MUNICIPALITIES:
        for ward in range(1, 8):
            district = muni["district"]
            history = [
                {"role": "user", "content": f"I am from {muni['name']}-{ward}."},
                {"role": "assistant", "content": "Got it. I will use that location for the next government-service question."},
            ]
            add(
                rows,
                id=f"dlg500_memory_citizenship_{muni['key']}_{ward}",
                question="Now how do I make citizenship?",
                history=history,
                decision="partial_answer_plus_followup",
                service="citizenship",
                missing=["citizenship_case_type"],
                domains=["moha.gov.np", muni["domain"], *dao_domains(district)],
                priority="p0",
                notes="Carry municipality/ward from history and only ask unresolved case type.",
            )
            add(
                rows,
                id=f"dlg500_memory_passport_{muni['key']}_{ward}",
                question="passport ko status kasari herne?",
                history=history,
                decision="retrieve_then_answer",
                service="passport",
                domains=SERVICE_DOMAINS["passport"],
                notes="Use memory without turning passport status into a local citizenship answer.",
            )
            add(
                rows,
                id=f"dlg500_memory_location_ack_{muni['key']}_{ward}",
                question=f"I am from {muni['name']}-{ward}.",
                decision="ack_memory",
                domains=[muni["domain"]],
                notes="Location-only turn should update memory, not answer a service.",
            )

    # Citizenship with local location and case type is ready for retrieval.
    citizenship_cases = [
        ("lost", "I lost my citizenship in {muni}-{ward}. How do I get duplicate?", "replace"),
        ("correction", "My citizenship has wrong age in {muni}-{ward}. How do I correct it?", "correct"),
        ("minor", "{muni}-{ward} ma nabalak nagarikta kasari banaune?", "apply"),
    ]
    for muni in MUNICIPALITIES:
        for ward in range(1, 8):
            for slug, question, _action in citizenship_cases:
                add(
                    rows,
                    id=f"dlg500_citizenship_{slug}_{muni['key']}_{ward}",
                    question=question.format(muni=muni["name"], ward=ward),
                    decision="retrieve_then_answer",
                    service="citizenship",
                    domains=["moha.gov.np", muni["domain"], *dao_domains(muni["district"])],
                    notes="Locality and citizenship case type are known.",
                )

    # Vital registration: known local office versus ambiguous no-location queries.
    vital_services = [
        ("birth", "How do I get a birth certificate in {muni}?"),
        ("death", "death registration in {muni} kasari garne?"),
        ("marriage", "{muni} ma marriage registration garna k chaincha?"),
        ("birth_ne", "{muni_np} मा जन्म दर्ता कसरी गर्ने?"),
    ]
    muni_np = {"jiri": "जिरी", "khandbari": "खाँदबारी"}
    for muni in MUNICIPALITIES:
        for slug, tmpl in vital_services:
            add(
                rows,
                id=f"dlg500_vital_{slug}_{muni['key']}",
                question=tmpl.format(muni=muni["name"], muni_np=muni_np[muni["key"]]),
                decision="retrieve_then_answer",
                service="vital_registration",
                domains=[*SERVICE_DOMAINS["vital_registration"], muni["domain"]],
                priority="p0",
                notes="Known municipality should route to DoNIDCR plus local source.",
            )
    for idx, question in enumerate([
        "janma darta kasari garne?",
        "How do I register a birth certificate?",
        "मृत्यु दर्ता कसरी गर्ने?",
        "marriage registration ko process k ho?",
        "vital registration kaha garne?",
    ] * 8):
        add(
            rows,
            id=f"dlg500_vital_ambiguous_{idx}",
            question=question,
            decision="partial_answer_plus_followup",
            service="vital_registration",
            missing=["municipality_or_district"],
            domains=SERVICE_DOMAINS["vital_registration"],
            notes="Vital registration generally needs local office context.",
        )

    # Local contact/person routing.
    contact_qs = [
        "who is the helpdesk officer in {muni} municipality?",
        "{muni} municipality phone number",
        "{muni} ko mayor ko contact number?",
        "{muni_np} नगरपालिकाको सूचना अधिकारी को हो?",
        "{muni} ward office contact person",
    ]
    for muni in MUNICIPALITIES:
        for idx, tmpl in enumerate(contact_qs):
            add(
                rows,
                id=f"dlg500_contact_known_{muni['key']}_{idx}",
                question=tmpl.format(muni=muni["name"], muni_np=muni_np[muni["key"]]),
                decision="contact_handoff_or_retrieve",
                service="municipality_service",
                domains=[muni["domain"]],
                priority="p0",
                notes="Known local contact query should prefer staff/contact sources.",
            )
    for idx, question in enumerate([
        "municipality phone number",
        "ward office contact person ko number chahiyo",
        "mayor phone number",
        "नगरपालिकाको सूचना अधिकारी को हो?",
        "helpdesk officer ko contact kaha paune?",
    ] * 8):
        add(
            rows,
            id=f"dlg500_contact_unknown_location_{idx}",
            question=question,
            decision="partial_answer_plus_followup",
            service="municipality_service",
            missing=["municipality_or_district"],
            notes="Contact/person questions need the relevant office location if none is given.",
        )

    # Foreign employment and manpower-agency complaints.
    manpower_qs = [
        "who to contact when i got cheated by manpower agency?",
        "manpower agency le thagyo bhane kaslai contact garne?",
        "foreign employment agency fraud complaint kaha garne?",
        "वैदेशिक रोजगारमा म्यानपावरले ठगेको छ, कहाँ उजुरी गर्ने?",
        "labor permit issue ma complaint kaslai garne?",
    ]
    for idx, question in enumerate(manpower_qs * 10):
        add(
            rows,
            id=f"dlg500_foreign_employment_complaint_{idx}",
            question=question,
            decision="contact_handoff_or_retrieve",
            service="foreign_employment",
            domains=SERVICE_DOMAINS["foreign_employment"],
            priority="p0",
            notes="Complaint/contact flow must keep the user's script and route to foreign-employment sources.",
        )

    # Passport flows.
    passport_qs = [
        ("apply", "How do I apply for a new passport in Nepal?", "retrieve_then_answer", [], SERVICE_DOMAINS["passport"]),
        ("status", "passport ko status kasari herne?", "retrieve_then_answer", [], SERVICE_DOMAINS["passport"]),
        ("minor", "I need passport for my child. What documents are needed?", "partial_answer_plus_followup", ["applicant_age_or_minor_context"], SERVICE_DOMAINS["passport"]),
        ("lost_qatar", "I lost my Nepali passport in Qatar. Who should I contact?", "contact_handoff_or_retrieve", [], SERVICE_DOMAINS["passport_abroad"]),
        ("embassy", "passport lost abroad embassy contact?", "contact_handoff_or_retrieve", [], SERVICE_DOMAINS["passport_abroad"]),
    ]
    for idx in range(12):
        for slug, question, decision, missing, domains in passport_qs:
            add(
                rows,
                id=f"dlg500_passport_{slug}_{idx}",
                question=question,
                decision=decision,
                service="passport",
                missing=missing,
                domains=domains,
                notes="Passport service/action routing.",
            )

    # Land/malpot.
    land_ambiguous = [
        "jagga ko tiro tirna kaha jane?",
        "land tax payment kaha garne?",
        "malpot tirna kun office jane?",
        "जग्गाको मालपोत कहाँ तिर्ने?",
    ]
    for idx, question in enumerate(land_ambiguous * 8):
        add(
            rows,
            id=f"dlg500_land_ambiguous_{idx}",
            question=question,
            decision="partial_answer_plus_followup",
            service="land",
            missing=["municipality_or_district"],
            domains=SERVICE_DOMAINS["land"],
            notes="Land tax/routing depends on location.",
        )
    for dkey, dname in DISTRICTS:
        add(
            rows,
            id=f"dlg500_land_district_{dkey}",
            question=f"Where do I pay land revenue in {dname}?",
            decision="retrieve_then_answer",
            service="land",
            domains=SERVICE_DOMAINS["land"],
            notes="District given; retrieve official land/malpot source.",
        )

    # PAN, VAT, tax, police, driving license, national ID.
    service_rows = [
        ("pan_apply", "PAN number kasari banaune?", "pan_tax", SERVICE_DOMAINS["pan_tax"]),
        ("pan_online", "Can I apply for PAN online in Nepal?", "pan_tax", SERVICE_DOMAINS["pan_tax"]),
        ("vat", "When does a small business need VAT registration?", "pan_tax", SERVICE_DOMAINS["pan_tax"]),
        ("tax_clearance", "How can my company get a tax clearance certificate?", "pan_tax", SERVICE_DOMAINS["pan_tax"]),
        ("police_apply", "How do I apply for police clearance report in Nepal?", "police_clearance", SERVICE_DOMAINS["police_clearance"]),
        ("police_abroad", "I am abroad and need Nepal police clearance. Can I apply online?", "police_clearance", SERVICE_DOMAINS["police_clearance"]),
        ("police_reprint", "police clearance report feri print garna milcha?", "police_clearance", SERVICE_DOMAINS["police_clearance"]),
        ("license_apply", "How do I apply for a driving license in Nepal?", "driving_license", SERVICE_DOMAINS["driving_license"]),
        ("license_retrial", "I failed my driving license trial. How do I apply for retrial?", "driving_license", SERVICE_DOMAINS["driving_license"]),
        ("license_visit", "लाइसेन्सको visit date कसरी लिने?", "driving_license", SERVICE_DOMAINS["driving_license"]),
        ("nid_apply", "How do I apply for national ID card?", "national_id", SERVICE_DOMAINS["national_id"]),
        ("nid_pre", "rastriya parichayapatra pre enrollment kasari garne?", "national_id", SERVICE_DOMAINS["national_id"]),
    ]
    for idx in range(10):
        for slug, question, service, domains in service_rows:
            add(
                rows,
                id=f"dlg500_{slug}_{idx}",
                question=question,
                decision="retrieve_then_answer",
                service=service,
                domains=domains,
                notes="Direct service question ready for retrieval.",
            )

    # Harmless off-domain math should not become a hard refusal.
    math_qs = ["2 + 2?", "what is 12 * 4?", "10 - 3?", "18 / 2?", "7 x 6?"] * 6
    for idx, question in enumerate(math_qs):
        add(
            rows,
            id=f"dlg500_offdomain_math_{idx}",
            question=question,
            decision="off_domain_light_answer",
            notes="Answer lightly and steer back to government services.",
        )

    # Keep deterministic order but cap to requested size.
    seen: set[str] = set()
    unique_rows: list[dict[str, Any]] = []
    for row in rows:
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        unique_rows.append(row)
        if len(unique_rows) >= limit:
            break
    if len(unique_rows) < limit:
        raise SystemExit(f"only generated {len(unique_rows)} rows, requested {limit}")
    return unique_rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="eval/service_dialogue_v5_seed500.jsonl")
    ap.add_argument("--limit", type=int, default=500)
    args = ap.parse_args()
    rows = build_rows(args.limit)
    write_jsonl(ROOT / args.out, rows)
    print("=== build v5 dialogue seed ===")
    print(f"rows: {len(rows)}")
    print(f"out: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
