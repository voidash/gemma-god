#!/usr/bin/env python3
"""Build a citizen-search demand seed from classified Reddit gov questions.

This is not training data. It is a compact planning artifact: what people
actually ask, how often each service category appears, and which authority
domains should be covered before we expect RAG to answer those questions.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_IN = Path("corpora/reddit_gov_questions_classified.jsonl")
DEFAULT_OUT = Path("eval/citizen_query_demand_seed.jsonl")
DEFAULT_SUMMARY = Path("eval/reports/citizen_query_demand_summary.json")
DEFAULT_MARKDOWN = Path("eval/reports/citizen_query_demand_summary.md")

ACTIONABLE_CLASSES = {"yes_procedure", "yes_info"}

AUTHORITY_DOMAINS: dict[str, list[str]] = {
    "passport": ["nepalpassport.gov.np", "mofa.gov.np"],
    "citizenship": ["donidcr.gov.np", "moha.gov.np", "district administration offices"],
    "birth_registration": ["donidcr.gov.np", "local municipality websites"],
    "pan_vat": ["ird.gov.np"],
    "tax": ["ird.gov.np", "customs.gov.np"],
    "driving_license": ["dotm.gov.np", "province transport office websites"],
    "police": ["nepalpolice.gov.np", "traffic.nepalpolice.gov.np"],
    "land": ["dolma.gov.np", "survey.gov.np", "malpot offices"],
    "education": ["moest.gov.np", "neb.gov.np", "ctevt.org.np"],
    "business": ["ocr.gov.np", "doind.gov.np", "ird.gov.np"],
    "visa_immigration": ["immigration.gov.np", "dofe.gov.np", "feb.gov.np", "mofa.gov.np"],
    "other": ["opmcm.gov.np", "hello sarkar", "relevant ministry/department"],
}

QUERY_TEMPLATES: dict[str, list[tuple[re.Pattern[str], str, str]]] = {
    "passport": [
        (re.compile(r"\brenew|expire|expiry|नवीकरण", re.I), "passport renewal process in Nepal", "procedure"),
        (re.compile(r"\bappointment|date|slot", re.I), "passport appointment date and required documents", "procedure"),
        (re.compile(r"\blost|hack|stolen|हराएको", re.I), "what to do if passport details are lost or misused", "procedure"),
    ],
    "citizenship": [
        (re.compile(r"\bnid|national identity|nin|राष्ट्रिय परिचय", re.I), "national ID detail correction after biometric in Nepal", "procedure"),
        (re.compile(r"\bwrong|mistake|amend|correction|galti|गल्ती", re.I), "citizenship certificate correction process in Nepal", "procedure"),
        (re.compile(r"\bdifferent city|kathmandu|district|jilla|जिल्ला", re.I), "can I make citizenship from a different district", "procedure"),
        (re.compile(r"\bnagrik app|नागरिक एप", re.I), "citizenship record not found in Nagarik app what to do", "procedure"),
    ],
    "birth_registration": [
        (re.compile(r"birth|janma|जन्म", re.I), "birth registration certificate process at ward office", "procedure"),
    ],
    "pan_vat": [
        (re.compile(r"\bpan\b|प्यान", re.I), "PAN card correction process in Nepal", "procedure"),
        (re.compile(r"\bvat\b|भ्याट", re.I), "VAT registration and billing rules in Nepal", "info"),
    ],
    "tax": [
        (re.compile(r"\bcustom|bhansar|भन्सार", re.I), "customs duty rules for personal goods in Nepal", "info"),
        (re.compile(r"\btax|कर", re.I), "tax payment and taxpayer portal process in Nepal", "procedure"),
    ],
    "driving_license": [
        (re.compile(r"\btrial|written|fail|retrial", re.I), "driving license retrial and written test process in Nepal", "procedure"),
        (re.compile(r"\brenew|expire", re.I), "driving license renewal process in Nepal", "procedure"),
        (re.compile(r"\blicen[cs]e|sawari|सवारी", re.I), "driving license online application process in Nepal", "procedure"),
    ],
    "police": [
        (re.compile(r"\baccident|traffic|bill book|insurance", re.I), "minor traffic accident process and traffic police documents in Nepal", "procedure"),
        (re.compile(r"\bclearance|police report|चारित्रिक", re.I), "police clearance certificate process in Nepal", "procedure"),
        (re.compile(r"\bharassment|complain|case|उजुरी", re.I), "how to file a police complaint in Nepal", "procedure"),
    ],
    "land": [
        (re.compile(r"\bnaksa|map|blueprint|नक्सा", re.I), "where to get land naksa or kitta map in Nepal", "procedure"),
        (re.compile(r"\bmalpot|napi|kitta|जग्गा", re.I), "land ownership and transfer records at malpot or napi office", "procedure"),
    ],
    "education": [
        (re.compile(r"\bsee\b|secondary education", re.I), "private SEE exam eligibility and exam center process", "info"),
        (re.compile(r"\btransfer|college", re.I), "college transfer criteria in Nepal", "info"),
        (re.compile(r"\bscholarship|scholorship|छात्रवृत्ति", re.I), "government scholarship eligibility in Nepal", "info"),
    ],
    "business": [
        (re.compile(r"\bcompany|media|non.?profit|private", re.I), "company registration and nonprofit conversion process in Nepal", "procedure"),
        (re.compile(r"\bpaid post|advertisement|ad", re.I), "online advertisement disclosure rules for media companies in Nepal", "info"),
    ],
    "visa_immigration": [
        (re.compile(r"\bvisa|immigration", re.I), "Nepal immigration visa process and required documents", "procedure"),
        (re.compile(r"\bforeign employment|work|labou?r|worker|श्रम", re.I), "foreign employment approval and worker return support in Nepal", "procedure"),
    ],
}

DEFAULT_CANONICAL: dict[str, tuple[str, str]] = {
    "passport": ("passport application or renewal process in Nepal", "procedure"),
    "citizenship": ("citizenship certificate application or correction process in Nepal", "procedure"),
    "birth_registration": ("birth registration certificate process at ward office", "procedure"),
    "pan_vat": ("PAN or VAT registration and correction process in Nepal", "procedure"),
    "tax": ("tax and customs rules for citizens in Nepal", "info"),
    "driving_license": ("driving license application and renewal process in Nepal", "procedure"),
    "police": ("police report or traffic police procedure in Nepal", "procedure"),
    "land": ("land records, naksa, and malpot process in Nepal", "procedure"),
    "education": ("education exam, transfer, and scholarship rules in Nepal", "info"),
    "business": ("company registration and business compliance process in Nepal", "procedure"),
    "visa_immigration": ("immigration and foreign employment process in Nepal", "procedure"),
    "other": ("government service complaint or information request in Nepal", "info"),
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def clean_text(text: str) -> str:
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def candidate_weight(row: dict[str, Any]) -> float:
    cls = row.get("class")
    base = 1.0 if cls in ACTIONABLE_CLASSES else 0.25
    score = row.get("score") or 0
    try:
        score_f = float(score)
    except Exception:
        score_f = 0.0
    return round(base * (1.0 + math.log1p(max(0.0, score_f)) / 3.0), 4)


def canonicalize(category: str, text: str) -> tuple[str, str]:
    for pattern, query, intent in QUERY_TEMPLATES.get(category, []):
        if pattern.search(text):
            return query, intent
    return DEFAULT_CANONICAL.get(category, DEFAULT_CANONICAL["other"])


def should_include(row: dict[str, Any], include_no_format: bool) -> bool:
    cls = row.get("class")
    category = (row.get("category") or "other").strip() or "other"
    if cls in ACTIONABLE_CLASSES:
        return True
    return bool(include_no_format and cls == "no_format" and category != "other")


def build_seed(rows: list[dict[str, Any]], include_no_format: bool) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if not should_include(row, include_no_format):
            continue
        category = (row.get("category") or "other").strip() or "other"
        raw = clean_text(row.get("body") or "")
        if not raw:
            continue
        canonical, intent = canonicalize(category, raw)
        out.append(
            {
                "demand_id": row.get("id"),
                "category": category,
                "class": row.get("class"),
                "intent": intent,
                "language": row.get("lang"),
                "kind": row.get("kind"),
                "reddit_score": row.get("score"),
                "weight": candidate_weight(row),
                "canonical_query": canonical,
                "raw_query": raw[:1200],
                "suggested_authority_domains": AUTHORITY_DOMAINS.get(
                    category, AUTHORITY_DOMAINS["other"]
                ),
                "rationale": row.get("rationale"),
            }
        )
    out.sort(key=lambda r: (-float(r["weight"]), r["category"], str(r["demand_id"])))
    return out


def summarize(seed: list[dict[str, Any]]) -> dict[str, Any]:
    count_by_cat: Counter[str] = Counter()
    weight_by_cat: Counter[str] = Counter()
    query_counts: dict[str, Counter[str]] = defaultdict(Counter)
    examples: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for r in seed:
        cat = r["category"]
        count_by_cat[cat] += 1
        weight_by_cat[cat] += float(r["weight"])
        query_counts[cat][r["canonical_query"]] += 1
        if len(examples[cat]) < 5:
            examples[cat].append(
                {
                    "canonical_query": r["canonical_query"],
                    "raw_query": r["raw_query"][:220],
                    "weight": r["weight"],
                    "suggested_authority_domains": r["suggested_authority_domains"],
                }
            )

    categories = []
    for cat, n in count_by_cat.most_common():
        categories.append(
            {
                "category": cat,
                "count": n,
                "weighted_demand": round(weight_by_cat[cat], 3),
                "top_canonical_queries": query_counts[cat].most_common(8),
                "suggested_authority_domains": AUTHORITY_DOMAINS.get(
                    cat, AUTHORITY_DOMAINS["other"]
                ),
                "examples": examples[cat],
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_candidates": len(seed),
        "categories": categories,
    }


def markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Citizen Query Demand Seed",
        "",
        f"Generated: {summary['generated_at']}",
        f"Candidate queries: {summary['total_candidates']}",
        "",
        "## Top Demand Categories",
        "",
        "| Category | Count | Weighted demand | Priority authority coverage |",
        "| --- | ---: | ---: | --- |",
    ]
    for cat in summary["categories"]:
        domains = ", ".join(cat["suggested_authority_domains"])
        lines.append(
            f"| {cat['category']} | {cat['count']} | "
            f"{cat['weighted_demand']} | {domains} |"
        )
    lines.extend(["", "## Search Families", ""])
    for cat in summary["categories"]:
        lines.append(f"### {cat['category']}")
        for query, n in cat["top_canonical_queries"]:
            lines.append(f"- {query} ({n})")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--classified", default=str(DEFAULT_IN))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--summary-out", default=str(DEFAULT_SUMMARY))
    ap.add_argument("--markdown-out", default=str(DEFAULT_MARKDOWN))
    ap.add_argument(
        "--exclude-no-format",
        action="store_true",
        help="Use only rows classified yes_info/yes_procedure.",
    )
    args = ap.parse_args()

    rows = load_jsonl(Path(args.classified))
    if not rows:
        raise SystemExit(f"no rows loaded from {args.classified}")

    seed = build_seed(rows, include_no_format=not args.exclude_no_format)
    summary = summarize(seed)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in seed) + "\n",
        encoding="utf-8",
    )

    summary_out = Path(args.summary_out)
    summary_out.parent.mkdir(parents=True, exist_ok=True)
    summary_out.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    md_out = Path(args.markdown_out)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.write_text(markdown(summary), encoding="utf-8")

    print(f"wrote seed: {out} ({len(seed)} rows)")
    print(f"wrote summary: {summary_out}")
    print(f"wrote markdown: {md_out}")
    print("top categories:")
    for cat in summary["categories"][:10]:
        print(
            f"- {cat['category']}: count={cat['count']} "
            f"weighted={cat['weighted_demand']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
