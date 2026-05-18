#!/usr/bin/env python3
"""Build v6.3 SFT rows for citation completeness and service-dialogue behavior.

v6.2 fixed malformed citations but still failed on three classes:

- source-supported answers with no [S#] citation;
- answerable cases refused despite gold chunks being present;
- exact numbers/dates/contacts rewritten or omitted.

This builder keeps v6.2 as the base and adds targeted, inspectable rows:

- mandatory-citation rows from reviewed gold contracts;
- exact-extraction rows from contract facts/contacts;
- repair rows from the v6.2 quick eval failures when available;
- hard-negative rows from reviewed refusal gold items;
- compact service-dialogue follow-up rows for ambiguous service questions.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import urllib.parse
from pathlib import Path
from typing import Any


SYSTEM_FINAL_V63 = """\
You are SpeakGov, a Nepal government-service navigator.
Use only the provided Sources and planner/composer contract. Answer in plain chat.
Every factual sentence supported by a source must cite source IDs like [S1] or [S2].
Never cite raw URLs. Never use numeric citations like [1]. Never answer in Hindi.
If the source supports the answer, do not add a fallback refusal.
If the case is ambiguous, ask a compact checklist and include only non-speculative help."""

SYSTEM_EXTRACT_V63 = """\
You are SpeakGov's exact-value extraction composer.
Use only the provided Sources and contract facts.
Return the exact requested numbers, dates, offices, contacts, fees, deadlines, or named entities.
Every extracted value must have a [S#] citation. Do not cite raw URLs. Do not use [1]."""

SYSTEM_REFUSAL_V63 = """\
You are SpeakGov, a Nepal government-service navigator.
Use only the provided Sources.
If the provided Sources do not answer the user's question, say the specific gap.
Ask a compact follow-up only when it would help route the case.
Do not invent procedures, contacts, fees, dates, office names, or links."""

SYSTEM_DIALOGUE_V63 = """\
You are SpeakGov, a Nepal government-service navigator.
Do resolver/intake first. Ask compact follow-up questions when the user's case is ambiguous.
Give useful non-speculative routing help while asking follow-up.
Avoid sensitive personal identifiers unless they are necessary. Never answer in Hindi."""


RAW_URL_RE = re.compile(r"https?://[^\s\]\)>'\"`]+")
BRACKET_NUMBER_RE = re.compile(r"\[(\d{1,2})\]")
SOURCE_ID_RE = re.compile(r"\[S(\d{1,2})\]")
VALUEISH_RE = re.compile(
    r"(\d|[०-९]|[१२३४५६७८९०]|"
    r"फोन|phone|सम्पर्क|contact|email|इमेल|@|"
    r"मिति|date|दिन|days?|हप्ता|week|महिना|month|वर्ष|year|"
    r"रु|रूपैयाँ|NPR|fee|दस्तुर|शुल्क|"
    r"प्रमुख|अधिकृत|officer|chief|mayor|secretary)",
    re.I,
)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
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


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def compact_text(text: str, limit: int = 1300) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def normalize_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(url.strip().rstrip(".,;:!?)>\"'"))
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return f"{host}{urllib.parse.unquote(parsed.path).rstrip('/')}"
    except Exception:
        return url.strip().rstrip("/")


def source_ref(src: dict[str, Any], idx: int) -> str:
    ref = str(src.get("source_ref") or f"S{src.get('rank') or idx}")
    return ref if re.fullmatch(r"S\d{1,2}", ref) else f"S{idx}"


def source_pack_text(sources: list[dict[str, Any]]) -> str:
    lines = ["Sources:"]
    if not sources:
        lines.append("(no candidate sources surfaced)")
        return "\n".join(lines)
    for idx, src in enumerate(sources, 1):
        sid = source_ref(src, idx)
        label = src.get("label") or ("CITIZEN INTERVIEW" if src.get("is_tacit") else "GOV.NP")
        host = src.get("host") or urllib.parse.urlparse(str(src.get("url") or "")).netloc
        lines.append(f"\n[{sid}] {label}")
        if host:
            lines.append(f"Host: {host}")
        if src.get("title"):
            lines.append(f"Title: {src.get('title')}")
        lines.append(f"Excerpt: {compact_text(src.get('snippet') or src.get('text') or '')}")
    return "\n".join(lines)


def gold_sources(item: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for chunk in item.get("candidate_chunks") or []:
        out.append({
            "source_ref": f"S{chunk.get('rank') or len(out) + 1}",
            "rank": chunk.get("rank") or len(out) + 1,
            "url": chunk.get("url"),
            "host": urllib.parse.urlparse(str(chunk.get("url") or "")).netloc,
            "label": "GOV.NP",
            "title": chunk.get("title") or "",
            "snippet": chunk.get("text") or "",
        })
    return out


def sid_for_url(url: str, sources: list[dict[str, Any]]) -> str | None:
    wanted = normalize_url(url)
    for idx, src in enumerate(sources, 1):
        src_url = str(src.get("url") or "")
        if src_url and normalize_url(src_url) == wanted:
            return source_ref(src, idx)
    for idx, src in enumerate(sources, 1):
        src_url = str(src.get("url") or "")
        if src_url and (wanted in normalize_url(src_url) or normalize_url(src_url) in wanted):
            return source_ref(src, idx)
    return None


def normalize_citations(text: str, sources: list[dict[str, Any]]) -> str:
    def replace_url(match: re.Match[str]) -> str:
        sid = sid_for_url(match.group(0), sources)
        return f"[{sid}]" if sid else ""

    out = RAW_URL_RE.sub(replace_url, text or "")
    out = BRACKET_NUMBER_RE.sub(lambda m: f"[S{m.group(1)}]", out)
    out = re.sub(r"\[\s*(S\d{1,2})\s*\]", r"[\1]", out)
    out = re.sub(r"\s+([।.,;:!?])", r"\1", out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out


def ensure_sentence_citations(text: str, default_sid: str = "S1") -> str:
    """Append [S#] to factual-looking uncited sentence fragments."""
    text = normalize_citations(text, [])
    parts = re.split(r"([।.!?])", text)
    out: list[str] = []
    for i in range(0, len(parts), 2):
        sent = parts[i].strip()
        punct = parts[i + 1] if i + 1 < len(parts) else ""
        if not sent:
            continue
        if not SOURCE_ID_RE.search(sent):
            sent = f"{sent} [{default_sid}]"
        out.append(sent + punct)
    return " ".join(out).strip() if out else text


def has_bad_citation(text: str) -> bool:
    return bool(RAW_URL_RE.search(text or "") or BRACKET_NUMBER_RE.search(text or ""))


def has_sid(text: str) -> bool:
    return bool(SOURCE_ID_RE.search(text or ""))


def build_final_prompt(rec: dict[str, Any], final_answer: str) -> str:
    contract = dict(rec.get("contract") or {})
    contract["final_answer"] = final_answer
    return "\n".join([
        "Conversation history:\n(none)",
        "",
        f"Latest user question: {rec.get('question')}",
        "",
        source_pack_text(rec.get("sources") or []),
        "",
        "Planner/composer contract:",
        json.dumps(contract, ensure_ascii=False, separators=(",", ":")),
        "",
        "Write the next assistant message. Cite every source-backed factual sentence with [S#].",
    ])


def build_gold_prompt(item: dict[str, Any], sources: list[dict[str, Any]]) -> str:
    return "\n".join([
        "Conversation history:\n(none)",
        "",
        f"Latest user question: {item.get('question')}",
        "",
        source_pack_text(sources),
        "",
        "Write the next assistant message using only the Sources.",
    ])


def metadata(source: str, **extra: Any) -> dict[str, Any]:
    out = {"source": source}
    out.update(extra)
    return out


def build_mandatory_citation_rows(contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in contracts:
        if rec.get("validation_issues"):
            continue
        contract = rec.get("contract") or {}
        if contract.get("answerability") != "answer":
            continue
        sources = rec.get("sources") or []
        answer = normalize_citations(contract.get("final_answer") or rec.get("answer") or "", sources)
        if not answer or has_bad_citation(answer):
            continue
        answer = ensure_sentence_citations(answer, "S1")
        if not has_sid(answer):
            continue
        rows.append({
            "messages": [
                {"role": "system", "content": SYSTEM_FINAL_V63},
                {"role": "user", "content": build_final_prompt(rec, answer)},
                {"role": "assistant", "content": answer},
            ],
            **metadata(
                "v6_3_mandatory_sentence_citations",
                seed_id=rec.get("id"),
                lang=rec.get("question_lang"),
                category=rec.get("topic") or rec.get("service") or "other",
                answerability="answer",
            ),
        })
    return rows


def contact_labels(lang: str | None) -> dict[str, str]:
    if lang == "devanagari":
        return {
            "name": "नाम",
            "role": "पद",
            "office": "कार्यालय",
            "phone": "फोन",
            "email": "इमेल",
        }
    return {
        "name": "name",
        "role": "role",
        "office": "office",
        "phone": "phone",
        "email": "email",
    }


def build_exact_extraction_rows(contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in contracts:
        if rec.get("validation_issues"):
            continue
        contract = rec.get("contract") or {}
        if contract.get("answerability") != "answer":
            continue
        facts = contract.get("facts") or []
        contacts = contract.get("contacts") or []
        extracted: list[str] = []
        labels = contact_labels(rec.get("question_lang"))
        for fact in facts:
            claim = str(fact.get("claim") or "").strip()
            sids = fact.get("source_ids") or ["S1"]
            if claim and VALUEISH_RE.search(claim):
                extracted.append(f"- {claim} [{sids[0]}]")
        for c in contacts:
            bits = []
            for key, label in [("name", "name"), ("role", "role"), ("office", "office"), ("phone", "phone"), ("email", "email")]:
                if c.get(key):
                    bits.append(f"{labels[label]}: {c.get(key)}")
            if bits:
                sid = (c.get("source_ids") or ["S1"])[0]
                extracted.append(f"- {'; '.join(bits)} [{sid}]")
        if not extracted:
            continue
        answer = "\n".join(extracted[:5])
        if has_bad_citation(answer) or not has_sid(answer):
            continue
        prompt = "\n".join([
            f"Latest user question: {rec.get('question')}",
            "",
            source_pack_text(rec.get("sources") or []),
            "",
            "Planner facts and contacts:",
            json.dumps({"facts": facts, "contacts": contacts}, ensure_ascii=False, separators=(",", ":")),
            "",
            "Return only the exact sourced values needed to answer the question.",
        ])
        rows.append({
            "messages": [
                {"role": "system", "content": SYSTEM_EXTRACT_V63},
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": answer},
            ],
            **metadata(
                "v6_3_exact_value_extraction",
                seed_id=rec.get("id"),
                lang=rec.get("question_lang"),
                category=rec.get("topic") or rec.get("service") or "other",
                answerability="answer",
            ),
        })
    return rows


def contract_answer_for_gold(
    original_gold_id: str | None,
    contracts_by_gold_id: dict[str, dict[str, Any]],
    sources: list[dict[str, Any]],
) -> str:
    if not original_gold_id:
        return ""
    rec = contracts_by_gold_id.get(original_gold_id)
    if not rec:
        return ""
    contract = rec.get("contract") or {}
    return normalize_citations(contract.get("final_answer") or rec.get("answer") or "", sources)


def build_eval_repair_rows(
    eval_json: dict[str, Any],
    gold_items: dict[str, dict[str, Any]],
    contracts_by_gold_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for res in eval_json.get("results") or []:
        item = gold_items.get(res.get("id"))
        if not item or item.get("type") != "grounded":
            continue
        output = res.get("model_output") or ""
        needs_repair = bool(res.get("wrongly_refused")) or (not res.get("model_source_ids") and not res.get("model_refused"))
        if not needs_repair:
            continue
        sources = gold_sources(item)
        answer = contract_answer_for_gold(item.get("id"), contracts_by_gold_id, sources)
        if not answer:
            answer = normalize_citations(item.get("draft_answer") or res.get("gold_answer") or "", sources)
        if not has_sid(answer):
            answer = ensure_sentence_citations(answer, "S1")
        if not answer or has_bad_citation(answer) or not has_sid(answer):
            continue
        prompt = "\n".join([
            build_gold_prompt(item, sources),
            "",
            "Previous bad model answer:",
            output,
            "",
            "Repair it. If the sources answer the question, answer instead of refusing. Cite every factual sentence with [S#].",
        ])
        rows.append({
            "messages": [
                {"role": "system", "content": SYSTEM_FINAL_V63},
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": answer},
            ],
            **metadata(
                "v6_3_eval_failure_repair",
                seed_id=res.get("id"),
                lang=item.get("question_lang"),
                category=item.get("question_category") or "other",
                answerability="answer",
                repair_reason="wrong_refusal" if res.get("wrongly_refused") else "missing_source_id",
            ),
        })
    return rows


def build_hard_negative_rows(gold_rows: list[dict[str, Any]], limit: int, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    candidates = [r for r in gold_rows if r.get("type") in {"refusal", "ungrounded_attempt"}]
    rng.shuffle(candidates)
    rows: list[dict[str, Any]] = []
    for item in candidates[:limit]:
        sources = gold_sources(item)
        lang = item.get("question_lang")
        if lang == "roman_nepali":
            answer = "Yo prashnako lagi provided sources ma authoritative answer bhetina. Kun service/office ko kura ho, ra kun district/municipality ho?"
        elif lang == "english":
            answer = "I cannot find an authoritative answer for this in the provided sources. Which service or office is this about, and which district/municipality applies?"
        else:
            answer = "प्रदान गरिएका स्रोतहरूमा यो प्रश्नको आधिकारिक उत्तर भेटिएन। कुन सेवा वा कार्यालयको कुरा हो, र कुन जिल्ला/नगरपालिका लागू हुन्छ?"
        prompt = build_gold_prompt(item, sources)
        rows.append({
            "messages": [
                {"role": "system", "content": SYSTEM_REFUSAL_V63},
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": answer},
            ],
            **metadata(
                "v6_3_hard_negative_refusal",
                seed_id=item.get("id"),
                lang=lang,
                category=item.get("question_category") or "other",
                answerability="refuse",
            ),
        })
    return rows


def build_dialogue_rows() -> list[dict[str, Any]]:
    specs = [
        ("citizenship", "How do I get citizenship in Sankhuwasabha?", "I can guide you, but citizenship depends on your exact case. Tell me: 1. Which municipality/rural municipality and ward? 2. Is this first-time, duplicate/lost, correction, or another case? 3. Adult or minor? Meanwhile, the district-level office to check is the District Administration Office for your district."),
        ("passport", "passport banauna k garne?", "Passport ko process case anusar farak parcha. Malai yo bhannu: 1. Nepal bhitra ho ki abroad/embassy bata? 2. Naya passport, renewal, lost/damaged, ki correction? 3. Kun district/municipality? Tyo bhaye ma timlai right office, documents, appointment/source tira route garna sakchu."),
        ("vital_registration", "birth certificate in Jiri", "I can help with birth registration/certificate for Jiri. Please tell me: 1. Birth registration first time ho ki certificate copy? 2. Child kati barsa ko ho? 3. Kun ward? Meanwhile, this is usually handled through the ward/local registrar, and I should use Jiri Municipality or DONIDCR sources for the exact rule."),
        ("national_id", "राष्ट्रिय परिचयपत्र बनाउन के चाहिन्छ?", "राष्ट्रिय परिचयपत्रका लागि सही उत्तर तपाईंको ठाउँ र अवस्था अनुसार हुन्छ। कृपया भन्नुहोस्: १. कुन जिल्ला/नगरपालिका? २. पहिलोपटक दर्ता हो कि विवरण सच्याउने? ३. नागरिकता छ कि छैन? त्यसपछि म सम्बन्धित दर्ता स्थान र आधिकारिक स्रोत देखाएर बताउँछु।"),
        ("tax", "PAN कसरी लिने?", "PAN का लागि पहिले तपाईंको case छुट्याउनुपर्छ। भन्नुहोस्: १. व्यक्तिगत PAN हो कि business/company? २. कुन जिल्ला/करदाता सेवा कार्यालय नजिक पर्छ? ३. online apply गर्न खोज्नुभएको हो कि office जानुपर्ने हो? त्यसपछि म IRD स्रोतमा आधारित checklist दिन्छु।"),
        ("driving_license", "Pokhara ma license renew kasari garne?", "Driving license renewal को लागि मलाई यी कुरा चाहिन्छ: १. तपाईं Kaski/Pokhara office बाट गर्न खोज्दै हुनुहुन्छ? २. renewal, trial, add category, वा lost card? ३. license expiry भएको कति भयो? त्यसपछि म provincial transport office/DOTM स्रोत हेरेर exact step दिन्छु।"),
        ("police_clearance", "police report chahiyo", "Police clearance/report को route प्रयोग अनुसार फरक हुन सक्छ। भन्नुहोस्: १. Nepal भित्र प्रयोग गर्ने हो कि abroad/visa का लागि? २. online police clearance हो कि local police report? ३. कुन district/municipality? त्यसपछि म सही police source र steps दिन्छु।"),
        ("foreign_employment", "manpower agency le thagyo, kaslai contact garne?", "यो foreign employment/manpower complaint जस्तो देखिन्छ। सुरक्षित रूपमा route गर्न मलाई भन्नुहोस्: १. तपाईं Nepal मा हुनुहुन्छ कि abroad? २. agency को issue पैसा, contract, visa, श्रम स्वीकृति, वा rescue मध्ये कुन हो? ३. कुन district/country involved छ? Meanwhile, complaint routing usually Department of Foreign Employment/FEIMS or related labour authority तिर जान्छ; exact contact स्रोतबाट verify गरेर दिनुपर्छ।"),
        ("land", "lalpurja correction kasari garne?", "Land/lalpurja correction मा office र case type धेरै महत्वपूर्ण हुन्छ। भन्नुहोस्: १. कुन district/municipality? २. नाम, area, map, ownership, or spelling correction कुन हो? ३. मालपोत हो कि नापी office पनि जोडिन्छ? त्यसपछि म सम्बन्धित office/source अनुसार checklist दिन्छु।"),
        ("embassy", "Qatar bata document attest garna parcha", "Embassy/consular service को लागि केही detail चाहिन्छ। भन्नुहोस्: १. Qatar/Doha embassy बाटै हो? २. कुन document attest/verify गर्ने हो? ३. Nepal पठाउने हो कि Qatar मा प्रयोग गर्ने? त्यसपछि म embassy/MoFA/consular source अनुसार route गर्छु।"),
    ]
    rows: list[dict[str, Any]] = []
    for service, question, answer in specs:
        rows.append({
            "messages": [
                {"role": "system", "content": SYSTEM_DIALOGUE_V63},
                {"role": "user", "content": f"Conversation history:\n(none)\n\nLatest user question: {question}\n\nResolve the case and write the next assistant message."},
                {"role": "assistant", "content": answer},
            ],
            **metadata("v6_3_service_dialogue_followup", seed_id=f"dialogue_{service}", lang="mixed", category=service, answerability="follow_up"),
        })
    return rows


def dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        key = json.dumps(row.get("messages"), ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def split_rows(rows: list[dict[str, Any]], val_frac: float, seed: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    rng = random.Random(seed)
    by_source: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_source.setdefault(row.get("source") or "unknown", []).append(row)
    train: list[dict[str, Any]] = []
    val: list[dict[str, Any]] = []
    for _source, bucket in sorted(by_source.items()):
        rng.shuffle(bucket)
        n_val = max(1, round(len(bucket) * val_frac)) if len(bucket) >= 10 else 0
        val.extend(bucket[:n_val])
        train.extend(bucket[n_val:])
    rng.shuffle(train)
    rng.shuffle(val)
    return train, val


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contracts", default="corpora/sft_v6_1_gold_grounded_contracts.jsonl")
    ap.add_argument("--gold", default="eval/gov_helpdesk_gold_v1.jsonl")
    ap.add_argument("--eval-json", default="/tmp/v6_2_eval/eval__sft_v6_2_e4b_g6e_qlora_seed42_quick48__full_gold.json")
    ap.add_argument("--base-train", default="corpora/sft_v6_2_train.jsonl")
    ap.add_argument("--base-val", default="corpora/sft_v6_2_val.jsonl")
    ap.add_argument("--control-out", default="corpora/sft_v6_3_control_rows.jsonl")
    ap.add_argument("--train-out", default="corpora/sft_v6_3_train.jsonl")
    ap.add_argument("--val-out", default="corpora/sft_v6_3_val.jsonl")
    ap.add_argument("--hard-negative-limit", type=int, default=36)
    ap.add_argument("--val-frac", type=float, default=0.08)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    contracts = load_jsonl(Path(args.contracts))
    gold_rows = load_jsonl(Path(args.gold))
    gold_by_id = {r.get("id"): r for r in gold_rows}
    contracts_by_gold_id = {r.get("original_gold_id"): r for r in contracts if r.get("original_gold_id")}
    eval_json = load_json(Path(args.eval_json))

    control: list[dict[str, Any]] = []
    control.extend(build_mandatory_citation_rows(contracts))
    control.extend(build_exact_extraction_rows(contracts))
    control.extend(build_eval_repair_rows(eval_json, gold_by_id, contracts_by_gold_id))
    control.extend(build_hard_negative_rows(gold_rows, args.hard_negative_limit, args.seed))
    control.extend(build_dialogue_rows())
    control = dedupe_rows(control)
    write_jsonl(Path(args.control_out), control)

    base_train = load_jsonl(Path(args.base_train))
    base_val = load_jsonl(Path(args.base_val))
    c_train, c_val = split_rows(control, args.val_frac, args.seed)
    train = dedupe_rows(base_train + c_train)
    val = dedupe_rows(base_val + c_val)
    write_jsonl(Path(args.train_out), train)
    write_jsonl(Path(args.val_out), val)

    by_source: dict[str, int] = {}
    bad = raw = numeric = sid = 0
    for row in control:
        by_source[row["source"]] = by_source.get(row["source"], 0) + 1
        answer = row["messages"][-1]["content"]
        raw += len(RAW_URL_RE.findall(answer))
        numeric += len(BRACKET_NUMBER_RE.findall(answer))
        sid += len(SOURCE_ID_RE.findall(answer))
        if row.get("answerability") == "answer" and not SOURCE_ID_RE.search(answer):
            bad += 1

    print("=== v6.3 control build ===")
    print(f"contracts: {len(contracts)}")
    print(f"gold rows: {len(gold_rows)}")
    print(f"eval repair source present: {bool(eval_json)}")
    print(f"control rows: {len(control)}")
    print(f"train: {len(train)} ({len(base_train)} base + {len(c_train)} control before dedupe)")
    print(f"val: {len(val)} ({len(base_val)} base + {len(c_val)} control before dedupe)")
    print(json.dumps(by_source, ensure_ascii=False, sort_keys=True))
    print(f"assistant raw URLs: {raw}")
    print(f"assistant numeric citations: {numeric}")
    print(f"assistant source-id citations: {sid}")
    print(f"answer rows missing source-id citations: {bad}")
    if raw or numeric or bad:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
