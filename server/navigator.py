"""Deterministic service-navigator layer for SpeakGov.

This module is intentionally small and inspectable. It does not try to answer
government questions; it resolves the user's case enough to decide how retrieval
should run and when the system should ask follow-up instead of letting the
composer improvise.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any


DEVANAGARI_RE = re.compile(r"[\u0900-\u097f]")
TOKEN_RE = re.compile(r"[\w\u0900-\u097f]+", re.U)
DISTRICT_DATA_PATH = Path(os.environ.get("DISTRICT_DATA_PATH", "corpora/nepal_districts.jsonl"))

GOV_DOMAIN_HINTS = (
    "citizenship", "nagarikta", "passport", "rahadani", "national id",
    "birth", "death", "marriage", "divorce", "registration", "pan", "vat",
    "tax", "driving", "license", "police", "clearance", "land", "malpot",
    "municipality", "ward", "dao", "cdo", "jilla prashasan", "office",
    "room", "document", "documents", "government service", "government office",
    "sarkari", "sarkari office", "phone", "contact", "officer", "mayor",
    "helpdesk", "sifarish", "sifaris",
    "नागरिकता", "राहदानी", "पासपोर्ट", "राष्ट्रिय परिचयपत्र", "जन्म", "मृत्यु",
    "विवाह", "दर्ता", "प्यान", "कर", "सवारी", "लाइसेन्स", "प्रहरी",
    "मालपोत", "जग्गा", "नगरपालिका", "गाउँपालिका", "वडा", "जिल्ला प्रशासन",
    "सरकारी", "कार्यालय", "सेवा", "कागजात", "कोठा", "काम",
    "सम्पर्क", "फोन", "अधिकारी", "सिफारिश", "सिफारिस",
)

NOISY_BIRTH_REGISTRATION_ALIASES: tuple[str, ...] = (
    # Common ASR/typing variants of जन्म दर्ता. Keep these in the resolver so
    # noisy Nepali inputs still route to the event-registration mini-flow.
    "जनमदता",
    "जनमदाता",
    "जनम दता",
    "जनमदर्ता",
    "जनम दर्ता",
    "जन्मदता",
    "जन्मदाता",
    "जन्म दता",
    "जन्मदरता",
    "जन्मदर्त",
    "जन्मदर्ल",
    "जन्मदार्त",
    "जन्मदार््त",
)

SERVICE_ALIASES: dict[str, tuple[str, ...]] = {
    "citizenship": (
        "citizenship", "citizen certificate", "nagarikta", "nagrita",
        "nagrikta", "nagarita", "नागरिकता",
    ),
    "passport": ("passport", "rahadani", "राहदानी", "पासपोर्ट"),
    "national_id": (
        "national id", "nid", "national identity", "identity card",
        "rastriya parichayapatra", "parichayapatra", "parichaya patra",
        "राष्ट्रिय परिचयपत्र", "परिचयपत्र",
    ),
    "vital_registration": (
        "vital registration", "civil registration", "event registration",
        "birth registration", "birth certificate", "janma darta",
        "janmadarta", "death registration", "marriage registration",
        "divorce registration", "जन्म दर्ता", "जन्मदर्ता", "मृत्यु दर्ता",
        *NOISY_BIRTH_REGISTRATION_ALIASES,
        "विवाह दर्ता", "सम्बन्ध विच्छेद", "घटना दर्ता", "पञ्जीकरण",
    ),
    "pan_tax": ("pan", "vat", "ird", "tax", "kar", "स्थायी लेखा", "करदाता"),
    "driving_license": (
        "driving license", "driving licence", "license", "licence",
        "savari", "chalak", "सवारी चालक", "अनुमतिपत्र", "लाइसेन्स",
    ),
    "police_clearance": (
        "police clearance", "police report", "character certificate",
        "clearance report", "चारित्रिक", "चालचलन",
    ),
    "foreign_employment": (
        "foreign employment", "labor permit", "labour permit", "shram",
        "manpower", "manpower agency", "recruitment agency", "employment agency",
        "वैदेशिक रोजगार", "श्रम", "म्यानपावर",
    ),
    "land": (
        "land tax", "land revenue", "land", "malpot", "jagga", "lalpurja",
        "tiro", "मालपोत", "जग्गा", "लालपुर्जा", "तिरो",
    ),
    "municipality_service": (
        "municipality", "ward", "palika", "nagarpalika", "gaupalika",
        "नगरपालिका", "गाउँपालिका", "वडा",
    ),
}

SERVICE_QUERY_TERMS: dict[str, tuple[str, ...]] = {
    "citizenship": ("citizenship", "nagarikta", "नागरिकता", "जिल्ला प्रशासन कार्यालय", "ward recommendation"),
    "passport": ("passport", "rahadani", "राहदानी", "पासपोर्ट"),
    "national_id": ("national identity card", "national id", "राष्ट्रिय परिचयपत्र", "pre enrollment"),
    "vital_registration": ("event registration", "birth death marriage registration", "घटना दर्ता", "पञ्जीकरण"),
    "pan_tax": ("PAN", "taxpayer", "IRD", "स्थायी लेखा नम्बर"),
    "driving_license": ("driving license", "सवारी चालक अनुमतिपत्र"),
    "police_clearance": ("police clearance report", "चारित्रिक प्रमाणपत्र", "चालचलन प्रमाणपत्र"),
    "foreign_employment": ("foreign employment", "labor permit", "वैदेशिक रोजगार", "श्रम"),
    "land": ("land revenue", "malpot", "जग्गा", "मालपोत"),
    "municipality_service": ("municipality office", "local government", "नगरपालिका", "वडा कार्यालय"),
}

ACTION_QUERY_TERMS: dict[str, tuple[str, ...]] = {
    "contact": (
        "contact",
        "contact person",
        "contact number",
        "phone",
        "telephone",
        "email",
        "information officer",
        "staff directory",
        "officials",
        "office contact",
        "सम्पर्क",
        "फोन",
        "नम्बर",
        "सूचना अधिकारी",
        "पदाधिकारी",
        "कर्मचारी",
    ),
    "complaint": ("complaint", "grievance", "ujuri", "gunaso", "उजुरी", "गुनासो", "ठगी"),
    "fee": ("fee", "charge", "cost", "शुल्क", "दस्तुर"),
    "status": ("status", "track", "check status", "स्थिति"),
}

SERVICE_AUTHORITY_DOMAINS: dict[str, tuple[str, ...]] = {
    "citizenship": ("moha.gov.np",),
    "passport": ("nepalpassport.gov.np",),
    "national_id": ("donidcr.gov.np",),
    "vital_registration": ("donidcr.gov.np",),
    "pan_tax": ("ird.gov.np",),
    "driving_license": ("dotm.gov.np", "transportmanagement.gov.np"),
    "police_clearance": ("nepalpolice.gov.np",),
    "foreign_employment": ("dofe.gov.np", "feb.gov.np", "moless.gov.np"),
    "land": ("dolma.gov.np", "molcpa.gov.np"),
}

ACTION_ALIASES: dict[str, tuple[str, ...]] = {
    "complaint": (
        "complain", "complaint", "file complaint", "fraud", "cheat",
        "cheated", "scam", "thagiyeko", "thageko", "thagyo", "thagi",
        "thag", "ujuri", "gunaso", "उजुरी",
        "ठगी", "ठगिएको", "ठगेको", "ठग्यो", "ठग", "धोका", "गुनासो",
    ),
    "contact": (
        "phone", "telephone", "contact", "contact person", "helpdesk",
        "officer", "officers", "staff", "who is", "who are", "mayor",
        "information officer", "सूचना अधिकारी", "सम्पर्क", "फोन", "नम्बर",
        "नंबर", "पदाधिकारी", "कर्मचारी", "अधिकारी", "नगर प्रमुख",
    ),
    "apply": (
        "how to", "apply", "get", "make", "banaune", "banauna", "lina",
        "paune", "kasari", "कसरी", "बनाउने", "बनाउन", "लिने", "पाउने",
    ),
    "replace": (
        "lost", "duplicate", "replace", "replacement", "harayo", "haraeko",
        "प्रतिलिपि", "हराएको", "हराए", "बिग्रिएको", "झुत्रो",
    ),
    "correct": ("correct", "correction", "amend", "change", "mistake", "सच्याउने", "संशोधन"),
    "fee": ("fee", "cost", "charge", "price", "शुल्क", "दस्तुर"),
    "status": ("status", "track", "check", "स्थिति"),
}

SERVICE_SOURCE_CLASSES: dict[str, dict[str, list[str]]] = {
    "contact": {
        "primary": ["office_contact_page", "information_officer_page", "staff_directory", "verified_officer_interview"],
        "secondary": ["general_notice", "office_profile"],
    },
    "complaint": {
        "primary": ["complaint_channel", "department_helpdesk", "office_contact_page", "latest_notice"],
        "secondary": ["verified_staff_interview", "verified_citizen_interview"],
    },
    "apply": {
        "primary": ["citizen_charter", "service_page", "latest_circular", "form_instruction"],
        "secondary": ["verified_staff_interview", "verified_citizen_interview"],
    },
    "replace": {
        "primary": ["service_page", "citizen_charter", "latest_circular"],
        "secondary": ["verified_staff_interview", "verified_citizen_interview"],
    },
    "correct": {
        "primary": ["service_page", "citizen_charter", "latest_circular", "form_instruction"],
        "secondary": ["verified_staff_interview", "verified_citizen_interview"],
    },
    "fee": {
        "primary": ["latest_fee_table", "dated_notice", "service_page"],
        "secondary": ["citizen_charter"],
    },
    "status": {
        "primary": ["status_portal", "service_page", "office_contact_page"],
        "secondary": ["latest_notice"],
    },
    "default": {
        "primary": ["service_page", "citizen_charter", "official_directory"],
        "secondary": ["verified_human_practical_note"],
    },
}

SERVICE_EXTRA_SLOT_RULES: tuple[dict[str, Any], ...] = (
    {
        "service": "passport",
        "markers": ("child", "minor", "nabalak", "नाबालक", "बच्चा"),
        "missing": ("applicant_age_or_minor_context",),
    },
    {
        "service": "land",
        "markers": ("tiro", "tax", "revenue", "malpot", "तिरो", "कर", "मालपोत"),
        "requires_location": True,
        "missing": ("municipality_or_district",),
    },
    {
        "service": "municipality_service",
        "action": "contact",
        "markers": ("officer", "staff", "contact person", "phone", "mayor", "helpdesk", "अधिकारी", "सम्पर्क", "फोन"),
        "requires_location": True,
        "missing": ("municipality_or_district",),
    },
)

CITIZENSHIP_CASE_ALIASES: dict[str, tuple[str, ...]] = {
    "first_time": ("first time", "new citizenship", "naya", "naya nagarikta", "नयाँ"),
    "duplicate_lost": ACTION_ALIASES["replace"],
    "correction": ACTION_ALIASES["correct"],
    "minor": ("minor", "nabalak", "नाबालक"),
}

OFFICE_ALIASES: dict[str, tuple[str, ...]] = {
    "dao": ("dao", "cdo", "district administration", "district administration office", "jilla prashasan", "जिल्ला प्रशासन"),
}

GENERIC_INTAKE_GOV_HINTS = (
    "government office", "government service", "office task", "sarkari office",
    "sarkari kaam", "sarkari service", "सरकारी कार्यालय", "सरकारी सेवा",
    "सरकारी काम", "कार्यालयको काम", "कार्यालयमा काम", "सरकारी काममा",
)

GENERIC_INTAKE_UNCERTAINTY_HINTS = (
    "don't know which", "do not know which", "dont know which",
    "which office", "which room", "which document", "which fee",
    "what document", "what fee", "right questions", "first ask",
    "ask me the right", "guide me", "कुन कार्यालय", "कुन कोठा",
    "कुन कागजात", "कति शुल्क", "सही प्रश्न", "पहिले", "सोध",
    "थाहा छैन", "थाहा छैन्",
)

DISTRICT_ALIASES: dict[str, tuple[str, ...]] = {
    "sankhuwasabha": ("sankhuwasabha", "sankhuwasava", "sankhuwasabha district", "संखुवासभा", "सङ्खुवासभा"),
    "dolakha": ("dolakha", "दोलखा"),
    "kathmandu": ("kathmandu", "ktm", "काठमाडौं", "काठमाडौँ"),
    "lalitpur": ("lalitpur", "ललितपुर"),
    "bhaktapur": ("bhaktapur", "भक्तपुर"),
    "kaski": ("kaski", "pokhara", "कास्की", "पोखरा"),
    "chitwan": ("chitwan", "चितवन"),
    "tanahu": ("tanahu", "tanahun", "तनहुँ"),
    "solukhumbu": ("solukhumbu", "सोलुखुम्बु"),
}

DISTRICT_DISPLAY_NP: dict[str, str] = {
    "sankhuwasabha": "संखुवासभा",
    "dolakha": "दोलखा",
    "kathmandu": "काठमाडौं",
    "lalitpur": "ललितपुर",
    "bhaktapur": "भक्तपुर",
    "kaski": "कास्की",
    "chitwan": "चितवन",
    "tanahun": "तनहुँ",
    "tanahu": "तनहुँ",
    "solukhumbu": "सोलुखुम्बु",
}

KNOWN_MUNICIPALITY_ALIASES: dict[str, tuple[str, ...]] = {
    "jiri": ("jiri", "jirimun", "जिरी", "जिरि"),
    "khandbari": ("khandbari", "khandbarimun", "खाँदबारी", "खाँदवारी", "खांदबारी"),
    "dharmadevi": (
        "dharmadevi",
        "dharmadevi municipality",
        "dharmadevimun",
        "धर्मदेवी",
        "धर्मधेवी",
        "धर्मध्यपी",
        "धर्माधिपी",
        "धर्म देवी",
        "धर्मदेव",
        "धर्म देव",
        "धर्मदेवी नगरपालिका",
        "धर्म देवी नगरपालिका",
        "धर्मध्यपी नगरपालिका",
        "धर्माधिपी नगरपालिका",
        "धर्मदेव नगरपालिका",
        "धर्म देव नगरपालिका",
    ),
}

KNOWN_MUNICIPALITY_META: dict[str, tuple[str, str]] = {
    "jiri": ("jirimun.gov.np", "dolakha"),
    "khandbari": ("khandbarimun.gov.np", "sankhuwasabha"),
    "dharmadevi": ("dharmadevimun.gov.np", "sankhuwasabha"),
}

MATH_RE = re.compile(
    r"^\s*(?:what\s+is\s+)?(-?\d+)\s*([+*/xX\-])\s*(-?\d+)\s*"
    r"(?:(?:kati\s+ho|कति\s+हो)\??|\?)?\s*$",
    re.I,
)
WARD_RE = re.compile(r"(?:ward|wada|वडा)\s*(?:no\.?|number|नं\.?)?\s*[-:]?\s*(\d{1,2})|(?:^|\b)([A-Za-z][A-Za-z\-]+)\s*[- ](\d{1,2})(?:\b|$)", re.I)
LOCATION_ONLY_RE = re.compile(
    r"^\s*(?:"
    r"(?:i\s+am|i'?m|mero\s+ghar|ma|म)\s+(?:from|in|बाट|मा)\s+.+|"
    r"(?:from|in)\s+[A-Za-z\u0900-\u097f0-9\-\s]+"
    r")\.?\s*$",
    re.I,
)


@dataclass
class LocalityHit:
    kind: str
    name: str
    domain: str | None = None
    district: str | None = None


@dataclass
class CaseFrame:
    raw_question: str
    resolved_question: str
    language: str
    service: str | None = None
    action: str | None = None
    case_type: str | None = None
    office: str | None = None
    district: str | None = None
    municipality: str | None = None
    ward: str | None = None
    local_domains: list[str] = field(default_factory=list)
    expected_domains: list[str] = field(default_factory=list)
    missing_slots: list[str] = field(default_factory=list)
    needs_followup: bool = False
    memory_only: bool = False
    contextual_followup: bool = False
    off_domain_answer: str | None = None
    retrieval_query: str | None = None
    gaps: list[str] = field(default_factory=list)


def detect_language(text: str) -> str:
    deva = len(DEVANAGARI_RE.findall(text))
    latin = sum(1 for c in text if c.isascii() and c.isalpha())
    if deva and deva >= latin:
        return "devanagari"
    if re.search(r"\b(kasari|kati|garne|garna|banaune|banauna|parcha|chha|cha|ho|ma|ko)\b", text, re.I):
        return "roman_nepali"
    return "english"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in TOKEN_RE.findall(text or "")}


def _contains_any(text_l: str, raw: str, markers: tuple[str, ...]) -> bool:
    toks = _tokens(raw)
    for marker in markers:
        marker_l = marker.lower()
        if DEVANAGARI_RE.search(marker) or " " in marker_l:
            if marker_l in text_l:
                return True
        elif marker_l in toks:
            return True
    return False


@lru_cache(maxsize=4)
def _load_district_rows(path_text: str) -> tuple[dict[str, Any], ...]:
    path = Path(path_text)
    if not path.exists():
        return ()
    rows: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("district"):
                    rows.append(row)
    except OSError:
        return ()
    return tuple(rows)


def _district_alias_map(path: str | Path | None = None) -> dict[str, tuple[str, ...]]:
    out = dict(DISTRICT_ALIASES)
    for row in _load_district_rows(str(path or DISTRICT_DATA_PATH)):
        district = row.get("district")
        aliases = [district, row.get("display_name"), *(row.get("aliases") or [])]
        aliases = [a for a in aliases if isinstance(a, str) and a.strip()]
        if district and aliases:
            merged = [*(out.get(district) or ()), *aliases]
            out[district] = tuple(dict.fromkeys([a.strip() for a in merged]))
    return out


def _detect_service(text: str) -> str | None:
    text_l = _norm(text)
    toks = _tokens(text)
    best_service: str | None = None
    best_score = 0
    service_scores: dict[str, int] = {}
    for service, aliases in SERVICE_ALIASES.items():
        score = 0
        for alias in aliases:
            alias_l = alias.lower()
            if DEVANAGARI_RE.search(alias) or " " in alias_l:
                matched = alias_l in text_l
            else:
                matched = alias_l in toks
            if not matched:
                continue
            if " " in alias_l:
                score += 4
            elif DEVANAGARI_RE.search(alias):
                score += max(1, min(4, len(alias_l) // 2))
            else:
                score += 2 if len(alias_l) >= 5 else 1
        if score:
            service_scores[service] = score
        if score > best_score:
            best_service = service
            best_score = score
    if best_service == "municipality_service":
        # Municipality words often name the place, not the service. Prefer a
        # concrete service signal when it is strong enough, even if the query
        # also contains "नगरपालिका"/"municipality".
        specific_hits = [
            (service, score)
            for service, score in service_scores.items()
            if service != "municipality_service" and score >= 3
        ]
        if specific_hits:
            return max(specific_hits, key=lambda item: item[1])[0]
    if best_service:
        return best_service
    if _contains_any(text_l, text, GOV_DOMAIN_HINTS):
        return "municipality_service"
    return None


def _detect_action(text: str) -> str | None:
    text_l = _norm(text)
    for action, aliases in ACTION_ALIASES.items():
        if _contains_any(text_l, text, aliases):
            return action
    return None


def _contact_role_query_terms(text: str) -> tuple[str, ...]:
    text_l = _norm(text)
    if "सूचना अधिकारी" in text or "information officer" in text_l:
        return ("information officer", "सूचना अधिकारी")
    if "नगर प्रमुख" in text or "mayor" in text_l:
        return ("mayor", "नगर प्रमुख")
    if "उप प्रमुख" in text or "deputy mayor" in text_l:
        return ("deputy mayor", "उप प्रमुख")
    if "प्रमुख प्रशासकीय" in text or "chief administrative" in text_l:
        return ("chief administrative officer", "प्रमुख प्रशासकीय अधिकृत")
    return ()


def _detect_case_type(service: str | None, text: str) -> str | None:
    if service != "citizenship":
        return None
    text_l = _norm(text)
    for case_type, aliases in CITIZENSHIP_CASE_ALIASES.items():
        if _contains_any(text_l, text, aliases):
            return case_type
    return None


def _detect_office(text: str) -> str | None:
    text_l = _norm(text)
    for office, aliases in OFFICE_ALIASES.items():
        if _contains_any(text_l, text, aliases):
            return office
    return None


def _is_generic_intake_request(text: str) -> bool:
    """Detect broad helpdesk prompts that should ask intake first.

    These are not fee/contact/service questions yet. They are "I am lost in a
    government office; ask me the right questions" prompts, common in WhatsApp
    and kiosk demos. Letting the fee/contact words drive retrieval sends Nepali
    users into random sources before we know the actual service.
    """
    text_l = _norm(text)
    return (
        _contains_any(text_l, text, GENERIC_INTAKE_GOV_HINTS)
        and _contains_any(text_l, text, GENERIC_INTAKE_UNCERTAINTY_HINTS)
    )


def _district_from_text(text: str, districts_path: str | Path | None = None) -> str | None:
    text_l = _norm(text)
    for district, aliases in _district_alias_map(districts_path).items():
        if _contains_any(text_l, text, aliases):
            return district
    return None


def _district_row(district: str | None, path: str | Path | None = None) -> dict[str, Any] | None:
    if not district:
        return None
    for row in _load_district_rows(str(path or DISTRICT_DATA_PATH)):
        if row.get("district") == district:
            return row
    return None


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def dao_domain_for_district(district: str | None, districts_path: str | Path | None = None) -> str | None:
    if not district:
        return None
    row = _district_row(district, districts_path)
    domains = (row or {}).get("dao_domains") or []
    if domains:
        return str(domains[0])
    return f"dao{_slug(district)}.moha.gov.np"


def _load_registry_localities(registry_path: str | Path | None) -> dict[str, LocalityHit]:
    out: dict[str, LocalityHit] = {}
    if not registry_path:
        return out
    path = Path(registry_path)
    if not path.exists():
        return out
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (row.get("status") or "active") != "active":
                    continue
                office_type = (row.get("office_type") or "").lower()
                domain = row.get("domain") or ""
                if "local" not in office_type and not domain.endswith("mun.gov.np"):
                    continue
                name_en = row.get("name_en") or ""
                name_np = row.get("name_np") or ""
                source_id = row.get("source_id") or ""
                names = [name_en, name_np, domain.split(".")[0], source_id.replace("_gov_np", "")]
                clean_name = re.sub(r"\b(municipality|rural municipality|gaupalika|nagarpalika)\b", "", name_en, flags=re.I).strip()
                if clean_name:
                    names.append(clean_name)
                for name in names:
                    key = _norm(name)
                    if len(key) < 3:
                        continue
                    out[key] = LocalityHit(kind="municipality", name=clean_name or name_en or key, domain=domain)
    except OSError:
        return out
    return out


def _municipality_from_text(text: str, registry_path: str | Path | None) -> LocalityHit | None:
    text_l = _norm(text)
    for name, aliases in KNOWN_MUNICIPALITY_ALIASES.items():
        if _contains_any(text_l, text, aliases):
            domain, district = KNOWN_MUNICIPALITY_META.get(name, (None, None))
            return LocalityHit(kind="municipality", name=name, domain=domain, district=district)
    registry_hits = _load_registry_localities(registry_path)
    best: tuple[int, LocalityHit] | None = None
    for key, hit in registry_hits.items():
        if not key:
            continue
        if re.fullmatch(r"[a-z0-9_-]+", key):
            matched = re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", text_l) is not None
        else:
            matched = key in text_l
        if matched:
            score = len(key)
            if best is None or score > best[0]:
                best = (score, hit)
    return best[1] if best else None


def _ward_from_text(text: str) -> str | None:
    m = WARD_RE.search(text or "")
    if not m:
        return None
    return next((g for g in m.groups() if g and g.isdigit()), None)


def _is_location_only_statement(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped or "?" in stripped:
        return False
    if not LOCATION_ONLY_RE.match(stripped):
        return False
    return len(TOKEN_RE.findall(stripped)) <= 12


def _is_location_answer(
    text: str,
    *,
    district: str | None = None,
    municipality: LocalityHit | None = None,
    ward: str | None = None,
) -> bool:
    """Detect compact answers that are meant to fill a previous location slot."""
    stripped = (text or "").strip()
    if not stripped or "?" in stripped:
        return False
    if not (district or municipality or ward):
        return False
    text_l = _norm(stripped)
    if _contains_any(
        text_l,
        stripped,
        (
            "phone", "contact", "number", "officer", "mayor", "who", "what",
            "when", "where", "how", "fee", "document", "documents",
            "established", "population", "area", "सूचना अधिकारी", "सम्पर्क",
            "फोन", "नम्बर", "नगर प्रमुख", "को हो", "कति", "कसरी", "कागजात",
            "शुल्क", "स्थापना",
        ),
    ):
        return False
    if _is_location_only_statement(stripped):
        return True
    tokens = TOKEN_RE.findall(stripped)
    if len(tokens) > 8:
        return False
    if not municipality:
        return bool(district or ward)
    service = _detect_service(stripped)
    action = _detect_action(stripped)
    return service in {None, "municipality_service"} and action is None


def _simple_math_answer(question: str, lang: str) -> str | None:
    q = question.strip().replace("×", "x")
    m = MATH_RE.match(q)
    if not m:
        return None
    a = int(m.group(1))
    op = m.group(2)
    b = int(m.group(3))
    if op == "+":
        value: int | float = a + b
    elif op == "-":
        value = a - b
    elif op in ("*", "x", "X"):
        value = a * b
    else:
        if b == 0:
            value = float("inf")
        else:
            value = a / b
    if lang == "devanagari":
        return f"{a} {op} {b} = {value}। म मुख्य रूपमा नेपालका सरकारी सेवा, कागजात, कार्यालय, प्रक्रिया र सम्पर्कमा सहयोग गर्न बनाइएको हुँ।"
    if lang == "roman_nepali":
        return f"{a} {op} {b} = {value}. Ma mainly Nepal ko government services, documents, offices, process, ra contacts ma help garna baneko ho."
    return f"{a} {op} {b} = {value}. I am mainly built to help with Nepal government services, documents, offices, procedures, and contacts."


def _history_text(history: list[Any] | None) -> str:
    parts: list[str] = []
    for turn in (history or [])[-6:]:
        role = getattr(turn, "role", None) if not isinstance(turn, dict) else turn.get("role")
        content = getattr(turn, "content", None) if not isinstance(turn, dict) else turn.get("content")
        if role == "user" and content:
            parts.append(str(content))
    return "\n".join(parts)


def _merge(values: list[str], extra: str | None) -> list[str]:
    if extra and extra not in values:
        values.append(extra)
    return values


def resolve_case(
    question: str,
    history: list[Any] | None = None,
    *,
    registry_path: str | Path | None = None,
    districts_path: str | Path | None = None,
) -> CaseFrame:
    history_raw = _history_text(history)
    combined = f"{history_raw}\n{question}".strip()
    lang = detect_language(question)
    generic_intake = _is_generic_intake_request(question)
    off_domain = None
    if not _contains_any(_norm(question), question, GOV_DOMAIN_HINTS):
        off_domain = _simple_math_answer(question, lang)

    question_service = _detect_service(question)
    history_service = _detect_service(history_raw)
    service = question_service or _detect_service(combined)
    question_action = _detect_action(question)
    history_action = _detect_action(history_raw)
    action = question_action or (None if question_service else _detect_action(combined))
    if generic_intake and service in {None, "municipality_service"}:
        service = None
        action = None
    case_type = _detect_case_type(service, question) or _detect_case_type(service, combined)
    office = _detect_office(question) or _detect_office(combined)
    district = _district_from_text(question, districts_path) or _district_from_text(combined, districts_path)
    muni_hit = _municipality_from_text(question, registry_path) or _municipality_from_text(combined, registry_path)
    if not district and muni_hit and muni_hit.district:
        district = muni_hit.district
    ward = _ward_from_text(question) or _ward_from_text(combined)

    contextual_followup = False
    if (
        history_raw
        and history_service
        and history_service != "municipality_service"
        and question_service in {None, "municipality_service"}
        and question_action is None
        and _is_location_answer(question, district=district, municipality=muni_hit, ward=ward)
    ):
        service = history_service
        action = history_action or _detect_action(combined)
        case_type = _detect_case_type(service, history_raw) or _detect_case_type(service, combined)
        office = _detect_office(history_raw) or office
        contextual_followup = True

    if service is None and action == "contact" and (district or muni_hit or office):
        service = "municipality_service"

    local_domains: list[str] = []
    if muni_hit and muni_hit.domain:
        _merge(local_domains, muni_hit.domain)

    expected_domains: list[str] = []
    for d in SERVICE_AUTHORITY_DOMAINS.get(service or "", ()):
        _merge(expected_domains, d)
    for d in local_domains:
        _merge(expected_domains, d)
    if office == "dao" or service in {"citizenship", "passport", "national_id"}:
        dao_domain = dao_domain_for_district(district, districts_path)
        if dao_domain:
            _merge(expected_domains, dao_domain)

    missing: list[str] = []
    memory_only = False
    if service is None and not off_domain:
        if (district or muni_hit or ward) and _is_location_only_statement(question):
            memory_only = True
        elif generic_intake or _contains_any(_norm(question), question, GOV_DOMAIN_HINTS):
            missing.append("service")
    if service in {"citizenship", "passport", "national_id", "vital_registration"} and action in {None, "apply"}:
        if not district and not muni_hit and service in {"citizenship", "vital_registration"}:
            missing.append("municipality_or_district")
        if service == "citizenship" and not case_type:
            missing.append("citizenship_case_type")
        if service == "citizenship" and district and not muni_hit and not ward:
            missing.append("municipality_or_ward")

    needs_followup = bool(missing)

    query_bits = [question]
    if service:
        query_bits.extend(SERVICE_QUERY_TERMS.get(service, ()))
    if action == "complaint":
        query_bits.extend(("complaint", "grievance", "उजुरी", "गुनासो", "ठगी"))
    if action:
        query_bits.extend(ACTION_QUERY_TERMS.get(action, ()))
    if service == "municipality_service" and action == "contact":
        query_bits.extend(_contact_role_query_terms(combined))
    if office == "dao":
        query_bits.extend(("District Administration Office", "जिल्ला प्रशासन कार्यालय"))
    if district:
        query_bits.append(district)
        dao_domain = dao_domain_for_district(district, districts_path)
        if dao_domain and (office == "dao" or service in {"citizenship", "passport", "national_id"}):
            query_bits.append(dao_domain)
    if muni_hit:
        query_bits.append(muni_hit.name)
        query_bits.append(f"{muni_hit.name} municipality")
        if muni_hit.domain:
            query_bits.append(muni_hit.domain)
    if ward:
        query_bits.extend((f"ward {ward}", f"वडा {ward}"))
    retrieval_query = " ".join(dict.fromkeys(bit for bit in query_bits if bit))

    gaps: list[str] = []
    if service and district and dao_domain_for_district(district, districts_path):
        gaps.append(f"check_source:{dao_domain_for_district(district, districts_path)}")

    return CaseFrame(
        raw_question=question,
        resolved_question=combined,
        language=lang,
        service=service,
        action=action,
        case_type=case_type,
        office=office,
        district=district,
        municipality=muni_hit.name if muni_hit else None,
        ward=ward,
        local_domains=local_domains,
        expected_domains=expected_domains,
        missing_slots=missing,
        needs_followup=needs_followup,
        memory_only=memory_only,
        contextual_followup=contextual_followup,
        off_domain_answer=off_domain,
        retrieval_query=retrieval_query,
        gaps=gaps,
    )


def merge_unique(values: list[str], additions: list[str] | tuple[str, ...]) -> list[str]:
    out = list(values)
    for value in additions:
        if value and value not in out:
            out.append(value)
    return out


def _extra_missing_slots(frame: CaseFrame) -> list[str]:
    missing: list[str] = []
    text = frame.resolved_question or frame.raw_question
    text_l = _norm(text)
    for rule in SERVICE_EXTRA_SLOT_RULES:
        if rule.get("service") != frame.service:
            continue
        if rule.get("action") and rule.get("action") != frame.action:
            continue
        markers = tuple(rule.get("markers") or ())
        if markers and not _contains_any(text_l, text, markers):
            continue
        if rule.get("requires_location") and (frame.district or frame.municipality or frame.ward):
            continue
        missing = merge_unique(missing, tuple(rule.get("missing") or ()))
    return missing


def planner_missing_slots(frame: CaseFrame) -> list[str]:
    return merge_unique(list(frame.missing_slots), _extra_missing_slots(frame))


def planner_decision(frame: CaseFrame, missing_slots: list[str] | None = None) -> str:
    missing = missing_slots if missing_slots is not None else planner_missing_slots(frame)
    if frame.off_domain_answer:
        return "off_domain_light_answer"
    if frame.memory_only:
        return "ack_memory"
    if missing:
        return "partial_answer_plus_followup"
    if frame.action == "complaint":
        return "complaint_handoff_or_retrieve"
    if frame.action == "contact":
        return "contact_handoff_or_retrieve"
    return "retrieve_then_answer"


def planner_followup_questions(frame: CaseFrame, missing_slots: list[str] | None = None) -> list[str]:
    missing = missing_slots if missing_slots is not None else planner_missing_slots(frame)
    questions: list[str] = []
    lang = frame.language
    if "service" in missing:
        questions.append({
            "devanagari": "कुन सरकारी सेवा वा कागजातबारे सोध्नुभएको हो?",
            "roman_nepali": "Kun government service ya document ko barema sodhnu bhayeko ho?",
        }.get(lang, "Which government service or document is this about?"))
    if "municipality_or_district" in missing:
        questions.append({
            "devanagari": "कुन जिल्ला वा नगर/गाउँपालिका हो?",
            "roman_nepali": "Kun district ya municipality/gaupalika ho?",
        }.get(lang, "Which district or municipality/rural municipality is this for?"))
    if "municipality_or_ward" in missing:
        questions.append({
            "devanagari": "कुन नगर/गाउँपालिका र वडा हो?",
            "roman_nepali": "Kun municipality/gaupalika ra ward ho?",
        }.get(lang, "Which municipality/rural municipality and ward is this for?"))
    if "citizenship_case_type" in missing:
        questions.append({
            "devanagari": "नयाँ नागरिकता, प्रतिलिपि/हराएको, संशोधन, नाबालक, वा अर्को केस हो?",
            "roman_nepali": "Yo first-time, duplicate/lost, correction, minor, ki aru case ho?",
        }.get(lang, "Is this first-time citizenship, duplicate/lost, correction, minor, or another case?"))
    if "applicant_age_or_minor_context" in missing:
        questions.append({
            "devanagari": "आवेदक नाबालक हो? दुवै अभिभावकका कागजात उपलब्ध छन्?",
            "roman_nepali": "Applicant minor ho? Dui parent/guardian ko documents available cha?",
        }.get(lang, "Is the applicant a minor, and are both parents/guardians' documents available?"))
    return list(dict.fromkeys(questions))


def planner_source_classes(frame: CaseFrame) -> dict[str, list[str]]:
    action_key = frame.action or "default"
    if action_key not in SERVICE_SOURCE_CLASSES:
        action_key = "default"
    out = {
        "primary": list(SERVICE_SOURCE_CLASSES[action_key]["primary"]),
        "secondary": list(SERVICE_SOURCE_CLASSES[action_key]["secondary"]),
    }
    if frame.service in {"citizenship", "vital_registration"} and frame.municipality:
        out["primary"] = merge_unique(out["primary"], ["local_municipality_service_page", "ward_contact"])
    if frame.service == "foreign_employment" and frame.action in {"complaint", "contact"}:
        out["primary"] = merge_unique(out["primary"], ["complaint_channel", "department_helpdesk"])
    if frame.service == "passport" and _contains_any(
        _norm(frame.raw_question),
        frame.raw_question,
        ("abroad", "qatar", "doha", "embassy", "lost", "कतार", "दोहा", "विदेश", "राजदूतावास"),
    ):
        out["primary"] = merge_unique(out["primary"], ["embassy_contact_page", "mission_notice"])
    return out


def planner_expected_domains(frame: CaseFrame) -> list[str]:
    domains = list(frame.expected_domains)
    raw = frame.raw_question.lower()
    if frame.service == "passport" and any(
        marker in raw for marker in ("abroad", "qatar", "doha", "embassy", "lost")
    ):
        domains = merge_unique(domains, ("mofa.gov.np", "nepalembassy.gov.np"))
    return domains


def planner_contract(frame: CaseFrame) -> dict[str, Any]:
    missing_slots = planner_missing_slots(frame)
    decision = planner_decision(frame, missing_slots)
    followups = planner_followup_questions(frame, missing_slots)
    frame_dict = asdict(frame)
    frame_dict["missing_slots"] = missing_slots
    frame_dict["needs_followup"] = bool(missing_slots)
    frame_dict["decision"] = decision
    frame_dict["followup_questions"] = followups
    return {
        "schema_version": "service_navigator_planner_v1",
        "language": frame.language,
        "decision": decision,
        "case_frame": frame_dict,
        "service": frame.service,
        "action": frame.action,
        "case_type": frame.case_type,
        "office": frame.office,
        "location": {
            "district": frame.district,
            "municipality": frame.municipality,
            "ward": frame.ward,
            "local_domains": list(frame.local_domains),
        },
        "missing_slots": missing_slots,
        "followup_questions": followups,
        "source_classes": planner_source_classes(frame),
        "expected_domains": planner_expected_domains(frame),
        "retrieval_query": frame.retrieval_query,
        "gaps": list(frame.gaps),
    }


def host_matches(host: str | None, domains: list[str] | tuple[str, ...]) -> bool:
    if not host:
        return False
    host_l = host.lower().strip()
    return any(host_l == d.lower() or host_l.endswith("." + d.lower()) for d in domains)


def filter_gov_results_for_frame(frame: CaseFrame, gov_results: list[dict]) -> list[dict]:
    """Remove location-conflicting local/DAO sources.

    Federal authority sources remain available. Local and DAO sources are only
    kept when they match the resolved local domain or the derived district DAO
    domain. This prevents a Tanahu DAO page from answering a Sankhuwasabha case.
    """
    if not gov_results:
        return gov_results
    if not frame.district and not frame.local_domains:
        return gov_results

    allowed_local = set(frame.local_domains)
    dao_domain = dao_domain_for_district(frame.district)
    if dao_domain:
        allowed_local.add(dao_domain)

    filtered: list[dict] = []
    for row in gov_results:
        host = (row.get("host") or urllib.parse.urlsplit(row.get("url") or "").netloc).lower()
        if frame.action == "contact" and allowed_local:
            if host_matches(host, tuple(allowed_local)):
                filtered.append(row)
            continue
        is_dao = host.endswith(".moha.gov.np") and host.startswith("dao")
        is_local = host.endswith("mun.gov.np") or host.endswith("mun.gov.np")
        if is_dao or is_local:
            if host_matches(host, tuple(allowed_local)):
                filtered.append(row)
            continue
        filtered.append(row)
    return filtered


def filter_tacit_results_for_frame(frame: CaseFrame, tacit_results: list[dict]) -> list[dict]:
    """Remove citizen-interview claims from the wrong local office.

    Tacit claims are useful for practical office details, but they are also the
    easiest source type to misuse across locations. If the resolver found a
    municipality/district, only keep local tacit claims from that local domain
    or district DAO. Federal/generic tacit records without an office domain are
    left alone.
    """
    if not tacit_results:
        return tacit_results
    if not frame.district and not frame.local_domains:
        return tacit_results

    allowed_local = set(frame.local_domains)
    dao_domain = dao_domain_for_district(frame.district)
    if dao_domain:
        allowed_local.add(dao_domain)
    if not allowed_local:
        return tacit_results

    filtered: list[dict] = []
    for row in tacit_results:
        office = row.get("office") or {}
        host = (office.get("domain") or urllib.parse.urlsplit(row.get("office_url") or "").netloc).lower()
        if not host:
            filtered.append(row)
            continue
        is_local = host.endswith("mun.gov.np") or (host.endswith(".moha.gov.np") and host.startswith("dao"))
        if is_local and not host_matches(host, tuple(allowed_local)):
            continue
        filtered.append(row)
    return filtered


def is_contact_intent(frame: CaseFrame) -> bool:
    return frame.action == "contact" or frame.office == "dao"


def should_force_no_source_for_location(frame: CaseFrame, gov_results: list[dict]) -> bool:
    if not (frame.district or frame.local_domains):
        return False
    if not is_contact_intent(frame):
        return False
    expected = [d for d in frame.expected_domains if d not in SERVICE_AUTHORITY_DOMAINS.get(frame.service or "", ())]
    if not expected:
        return False
    return not any(host_matches(g.get("host"), tuple(expected)) for g in gov_results)


def followup_answer(frame: CaseFrame, gov_results: list[dict] | None = None) -> str | None:
    missing_slots = planner_missing_slots(frame)
    if not missing_slots and not frame.memory_only:
        return None

    gov_results = gov_results or []
    source_url = ""
    if gov_results:
        source_url = gov_results[0].get("url") or ""

    if frame.memory_only:
        bits: list[str] = []
        if frame.municipality:
            bits.append(frame.municipality)
        if frame.district:
            bits.append(frame.district)
        if frame.ward:
            bits.append(f"ward {frame.ward}")
        place = ", ".join(bits) or "that location"
        if frame.language == "devanagari":
            return f"ठीक छ, मैले {place} लाई यो कुराकानीको स्थानका रूपमा राखेँ। कुन सरकारी सेवा चाहिएको हो?"
        if frame.language == "roman_nepali":
            return f"Thik cha, maile {place} lai yo chat ko location context ma rakhe. Kun government service chahiyeko ho?"
        return f"Noted: {place}. Which government service do you need help with?"

    service_label_en = {
        "citizenship": "citizenship",
        "passport": "passport",
        "national_id": "national ID",
        "vital_registration": "vital/event registration",
    }.get(frame.service or "", "this service")
    service_label_ne = {
        "citizenship": "नागरिकता",
        "passport": "राहदानी",
        "national_id": "राष्ट्रिय परिचयपत्र",
        "vital_registration": "घटना दर्ता",
    }.get(frame.service or "", "यो सेवा")
    service_label_ro = {
        "citizenship": "nagarikta",
        "passport": "passport",
        "national_id": "national ID",
        "vital_registration": "vital/event registration",
    }.get(frame.service or "", "yo service")
    office_line = ""
    if frame.service == "citizenship" and frame.district:
        if frame.language == "devanagari":
            district_label = DISTRICT_DISPLAY_NP.get(frame.district, frame.district)
            office_line = f"जिल्ला-स्तरमा जाँच गर्ने कार्यालय जिल्ला प्रशासन कार्यालय {district_label} हो।"
        elif frame.language == "roman_nepali":
            office_line = f"District-level office hernu parne District Administration Office {frame.district.title()} ho."
        else:
            office_line = f"The district-level office to check is District Administration Office {frame.district.title()}."
    elif frame.service == "vital_registration" and frame.municipality:
        if frame.language == "devanagari":
            office_line = f"{frame.municipality} का लागि सम्बन्धित वडा/स्थानीय पञ्जिकाधिकारीबाट सुरु हुन्छ।"
        elif frame.language == "roman_nepali":
            office_line = f"{frame.municipality} ko lagi relevant ward/local registrar bata suru huncha."
        else:
            office_line = f"The local office usually starts at the relevant ward/local registrar for {frame.municipality}."
    if source_url:
        office_line = f"{office_line} I also found a relevant official source [{source_url}].".strip()

    if frame.language == "devanagari":
        lines = [f"यसका लागि केही विवरण चाहिन्छ, किनकि {service_label_ne} केसअनुसार फरक पर्छ।"]
        asks: list[str] = []
        if "municipality_or_district" in missing_slots:
            asks.append("नगरपालिका/गाउँपालिका र वडा कुन हो?")
        if "municipality_or_ward" in missing_slots:
            asks.append("कुन नगरपालिका/गाउँपालिका र वडा?")
        if "citizenship_case_type" in missing_slots:
            asks.append("पहिलो पटक, प्रतिलिपि/हराएको, सच्याउने, वा नाबालक केस?")
        if "applicant_age_or_minor_context" in missing_slots:
            asks.append("आवेदक नाबालक हो? दुवै अभिभावकका कागजात उपलब्ध छन्?")
        if "service" in missing_slots:
            asks.append("कुन सेवा चाहिएको हो?")
        lines.extend(f"{i}. {ask}" for i, ask in enumerate(asks, 1))
        if office_line:
            lines.append(office_line)
        return "\n".join(lines)

    if frame.language == "roman_nepali":
        lines = [f"Yo answer {service_label_ro} ko exact case anusar farak parcha, so short details chahinchha."]
        asks = []
        if "municipality_or_district" in missing_slots:
            asks.append("Kun municipality/gaupalika ra ward?")
        if "municipality_or_ward" in missing_slots:
            asks.append("Kun municipality/gaupalika ra ward?")
        if "citizenship_case_type" in missing_slots:
            asks.append("First-time, duplicate/lost, correction, ki minor case?")
        if "applicant_age_or_minor_context" in missing_slots:
            asks.append("Applicant minor ho? Dui parent/guardian ko documents available cha?")
        if "service" in missing_slots:
            asks.append("Kun government service chahiyeko ho?")
        lines.extend(f"{i}. {ask}" for i, ask in enumerate(asks, 1))
        if office_line:
            lines.append(office_line)
        return "\n".join(lines)

    lines = [f"I need a few details because {service_label_en} depends on the exact case."]
    asks = []
    if "municipality_or_district" in missing_slots:
        asks.append("Which municipality/rural municipality and ward?")
    if "municipality_or_ward" in missing_slots:
        asks.append("Which municipality/rural municipality and ward?")
    if "citizenship_case_type" in missing_slots:
        asks.append("Is this first-time citizenship, duplicate/lost, correction, minor, or another case?")
    if "applicant_age_or_minor_context" in missing_slots:
        asks.append("Is the applicant a minor, and are both parents/guardians' documents available?")
    if "service" in missing_slots:
        asks.append("Which government service do you need?")
    lines.extend(f"{i}. {ask}" for i, ask in enumerate(asks, 1))
    if office_line:
        lines.append(office_line)
    return "\n".join(lines)


def location_no_source_answer(frame: CaseFrame) -> str:
    place = frame.district.title() if frame.district else (frame.municipality or "that office")
    if frame.language == "devanagari":
        return f"मैले {place} का लागि मिल्ने आधिकारिक स्थानीय स्रोत फेला पारिनँ। गलत जिल्लाको स्रोत प्रयोग गर्नु ठीक हुँदैन, त्यसैले कृपया कार्यालयको आधिकारिक साइट/सम्पर्क पुष्टि गर्नुहोस्।"
    if frame.language == "roman_nepali":
        return f"{place} ko matching official local source bhetina. Arko district ko source use garnu hudaina, so official office site/contact confirm garnu parcha."
    return f"I could not find a matching official local source for {place}. I should not use another district's source for this, so the official office site/contact needs to be confirmed."
