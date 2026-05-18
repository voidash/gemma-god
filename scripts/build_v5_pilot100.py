#!/usr/bin/env python3
"""Build a 100-row v5 pilot seed.

The hand-authored expanded seed currently has 70 rows. This tops it up with
30 citizen-demand rows, mapped to the same eval schema used by the v5 distiller.
The added rows intentionally avoid categories without a retrieval topic route
yet, so this pilot measures v5 contract quality rather than known missing
router classes.

The citizen-demand file keeps raw social snippets for provenance, but those
snippets are often rants, comments, or article excerpts. For SFT seed quality,
the pilot asks normalized questions derived from those snippets and stores the
raw text only as metadata.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_BASE = Path("eval/service_eval_expanded_v5_seed.jsonl")
DEFAULT_DEMAND = Path("eval/citizen_query_demand_seed.jsonl")
DEFAULT_OUT = Path("eval/service_eval_v5_pilot100.jsonl")


QUOTAS = {
    "passport": 5,
    "citizenship": 5,
    "driving_license": 4,
    "land": 4,
    "pan_vat": 3,
    "police": 3,
    "birth_registration": 2,
    "business": 2,
    "visa_immigration": 2,
}


QUESTION_OVERRIDES = {
    "1saj8iu": "Minor accident bhayo, traffic police le mero license ra bill book liyeko cha. Official process aba ke garne?",
    "1sajm4o": "Can I settle a minor scooter accident privately if traffic police already took my license and bill book?",
    "k1ipild": "private company lai nonprofit organization ma convert/register garna kun office process ho?",
    "1reg07f": "CDO office staff asked for a bribe during my citizenship process. Where can I complain officially?",
    "iwfw872": "Nepali citizenship tyagera foreign citizenship liyeko manche le feri Nepali citizenship lina milcha?",
    "l5vtxvu": "जन्मदर्तामा नाम फरक छ भने नागरिकता बनाउनुअघि नयाँ जन्मदर्ता वा सच्याउने प्रक्रिया के हो?",
    "nskv0wy": "VAT लाग्ने कारोबारमा bill issue गर्दा VAT registration चाहिन्छ कि के नियम छ?",
    "1nzhi6p": "My mother's name is printed wrong on my citizenship certificate. How do I correct it?",
    "1pm9cpi": "NID biometric bhayepachi detail mistake kasari sachyaune?",
    "kwzoa2a": "Malpot ma purano land transfer record kasari verify garne?",
    "1o08fuj": "Kathmandu ma passport renew garne process ke ho?",
    "lbvmehx": "If my citizenship or passport details were leaked online, which government office should I contact?",
    "lxv2qqf": "Driving license online application kasari bharne?",
    "1ovt6de": "Kitta cut hunu bhanda agadi ko jagga naksa Napi ma paincha ki Malpot ma?",
    "lbjnkfd": "Nagarik app bata banako PAN card ma Nepali name mistake cha. Correction kasari garne?",
    "1otprlw": "District passport slot paako chaina. Urgent passport ko appointment ra required documents ke ke ho?",
    "1qct881": "Passport dispatch bhayeko status dekhiyo but DAO message aayena. Passport kasari collect garne?",
    "iq8vu4l": "Foreign employment ma jana shram swikriti/approval process ke ho?",
    "l5vvtpa": "Document anusar naam milayera जन्मदर्ता बनाउन ward office ma nibedan garna milcha?",
    "kfdwrxg": "Individual/proprietorship business register garna ke documents chaincha?",
    "1pn8mj2": "License biometric visit pachi written exam date miss bhayo bhane retrial/reapply process ke huncha?",
    "1sbc0vk": "Driving license form ma citizenship number ko zero छुट्यो. Office visit ma correction garna milcha?",
    "k49pcy7": "Malpot ma legalized property transfer document dispute भए कुन official process हुन्छ?",
    "ezz5zqw": "Individual PAN lina ke documents lagnu parcha, agent chaincha ki chaina?",
    "1oj1zig": "Lalitpur passport renewal appointment dates online available छैनन् भने के गर्ने?",
    "khsa77l": "Foreign employment bata farkeka workers ko official support process ke cha?",
}

DOMAIN_OVERRIDES = {
    "lbvmehx": ["nepalpassport.gov.np", "mofa.gov.np", "moha.gov.np", "donidcr.gov.np"],
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def compact(text: str, limit: int = 520) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip() + "?"


def looks_like_question(text: str) -> bool:
    t = (text or "").lower()
    if "?" in t:
        return True
    return bool(re.search(r"\b(how|what|where|which|can|kasari|kati|kata|kaha|ke|kun|garne|line|lina)\b", t))


def choose_question(row: dict[str, Any]) -> str:
    demand_id = row.get("demand_id") or ""
    if demand_id in QUESTION_OVERRIDES:
        return QUESTION_OVERRIDES[demand_id]
    canonical = compact(row.get("canonical_query") or "")
    raw = compact(row.get("raw_query") or "")
    if canonical:
        return canonical
    if 30 <= len(raw) <= 420 and looks_like_question(raw):
        return raw
    return raw


def map_demand(row: dict[str, Any]) -> dict[str, Any] | None:
    category = row.get("category")
    canonical = (row.get("canonical_query") or "").lower()

    if category == "passport":
        service, topic = "passport", "passport"
        domains = ["nepalpassport.gov.np", "mofa.gov.np"]
    elif category == "citizenship":
        if "national id" in canonical or "national identity" in canonical:
            service, topic = "national_id", "national_id"
            domains = ["donidcr.gov.np"]
        else:
            service, topic = "citizenship", "citizenship"
            domains = ["moha.gov.np", "donidcr.gov.np"]
    elif category == "birth_registration":
        service, topic = "vital_registration", "birth_registration"
        domains = ["donidcr.gov.np"]
    elif category == "pan_vat":
        service, topic = "pan_tax", "pan_tax"
        domains = ["ird.gov.np"]
    elif category == "driving_license":
        service, topic = "driving_license", "driving_license"
        domains = ["dotm.gov.np", "transportmanagement.gov.np"]
    elif category == "police":
        service, topic = "police", "police"
        domains = ["nepalpolice.gov.np"]
    elif category == "land":
        service, topic = "land", "land"
        domains = ["dolma.gov.np", "molcpa.gov.np"]
    elif category == "business":
        if "company" not in canonical:
            return None
        service, topic = "company_registration", "company_registration"
        domains = ["ocr.gov.np"]
    elif category == "visa_immigration":
        if "foreign employment" not in canonical:
            return None
        service, topic = "foreign_employment", "foreign_employment"
        domains = ["dofe.gov.np", "feb.gov.np"]
    else:
        return None

    demand_id = row.get("demand_id") or "unknown"
    domains = DOMAIN_OVERRIDES.get(demand_id, domains)
    return {
        "id": f"demand_{demand_id}",
        "service": service,
        "topic": topic,
        "question": choose_question(row),
        "expected_behavior": "answer_or_partial",
        "expected_domains": domains,
        "priority": "p1",
        "notes": f"Citizen-demand top-up from {category}: {row.get('canonical_query')}",
        "demand_id": demand_id,
        "raw_query": row.get("raw_query"),
        "canonical_query": row.get("canonical_query"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=str(DEFAULT_BASE))
    ap.add_argument("--demand", default=str(DEFAULT_DEMAND))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    base = load_jsonl(Path(args.base))
    demand = load_jsonl(Path(args.demand))
    existing_ids = {row.get("id") for row in base}
    selected: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()

    for row in demand:
        category = row.get("category")
        if counts[category] >= QUOTAS.get(category, 0):
            continue
        mapped = map_demand(row)
        if not mapped:
            continue
        if mapped["id"] in existing_ids:
            continue
        selected.append(mapped)
        counts[category] += 1
        if len(selected) >= 30:
            break

    if len(selected) != 30:
        raise SystemExit(f"wanted 30 top-up rows, got {len(selected)}; counts={dict(counts)}")

    out = base + selected
    if len(out) != 100:
        raise SystemExit(f"expected 100 total rows, got {len(out)}")
    write_jsonl(Path(args.out), out)
    print(f"wrote {args.out}: base={len(base)} topup={len(selected)} total={len(out)}")
    print("top-up categories:")
    for category, n in sorted(counts.items()):
        print(f"  {category}: {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
