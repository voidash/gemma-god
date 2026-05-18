#!/usr/bin/env python3
"""Build v6.4 split-task SFT data.

v6.3 failed because hard negatives, follow-ups, and final grounded answers were
mixed into the same final-composer behavior. v6.4 keeps one Gemma adapter, but
separates the tasks by system prompt:

- planner JSON: may learn follow-up, refusal, source-discovery, and routing;
- answerability JSON: may learn hard negatives from source packs;
- final composer: answerable/partial/follow-up/off-domain only, no hard-negative
  free-form refusals;
- exact extraction: answerable source-backed values only.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.navigator import followup_answer, planner_contract, resolve_case  # noqa: E402


SYSTEM_PLANNER_V64 = """\
You are SpeakGov's planner for Nepal government-service navigation.
Return only compact valid JSON. Resolve the user's service, action, location,
missing slots, follow-up questions, source classes, expected domains, retrieval
query, and gaps. Do not answer the service question in prose."""

SYSTEM_ANSWERABILITY_V64 = """\
You are SpeakGov's answerability and source-routing judge.
Given a user question and Sources, return only compact valid JSON with
answerability, recommended_next_action, relevant_source_ids, missing_slots,
followup_questions, and gaps. Use hard negatives only for this JSON decision
task; do not write a user-facing refusal message."""

SYSTEM_COMPOSER_V64 = """\
You are SpeakGov, a Nepal government-service navigator.
Use only the provided Sources and planner contract. Answer in plain chat.
Cite every source-backed factual sentence with source IDs like [S1].
Never cite raw URLs. Never use numeric citations like [1]. Never answer in Hindi.
If the provided planner says follow-up is needed, ask a compact checklist and
include only non-speculative routing/contact context. If sources answer the
question, do not add a fallback refusal after the answer."""

SYSTEM_EXTRACT_V64 = """\
You are SpeakGov's exact-value extraction composer.
Use only the provided Sources and planner facts. Return exact requested values
such as phone numbers, emails, dates, fees, offices, contacts, and names. Every
extracted value must cite [S#]. Do not cite raw URLs or numeric citations."""

SYSTEM_DIALOGUE_V64 = """\
You are SpeakGov, a Nepal government-service navigator.
Use the provided planner contract to write the next plain-chat assistant
message. Ask compact follow-up questions when ambiguity blocks a safe answer.
Remember chat details. Do not ask for sensitive identifiers unless necessary.
Never answer in Hindi."""


RAW_URL_RE = re.compile(r"https?://[^\s\]\)>'\"`]+", re.I)
BRACKET_NUMBER_RE = re.compile(r"(?<!S)\[(\d{1,2})\]")
SOURCE_ID_RE = re.compile(r"\[S\d{1,2}\]")
REFUSAL_MARKER_RE = re.compile(
    r"मलाई\s+यो\s+प्रश्नको\s+आधिकारिक\s+स्रोत\s+भेटिनँ|"
    r"Yo prashnako adhikarik srot bhetina|"
    r"I cannot find an authoritative source",
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


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def compact_text(text: str, limit: int = 1200) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def history_text(history: list[dict[str, Any]]) -> str:
    if not history:
        return "(none)"
    out: list[str] = []
    for turn in history[-8:]:
        role = str(turn.get("role") or "user")
        content = re.sub(r"\s+", " ", str(turn.get("content") or "")).strip()
        if content:
            out.append(f"{role}: {content}")
    return "\n".join(out) if out else "(none)"


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
        url = str(src.get("url") or "")
        host = src.get("host") or urllib.parse.urlparse(url).netloc
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
        url = str(chunk.get("url") or "")
        out.append({
            "source_ref": f"S{chunk.get('rank') or len(out) + 1}",
            "rank": chunk.get("rank") or len(out) + 1,
            "url": url,
            "host": urllib.parse.urlparse(url).netloc,
            "label": "GOV.NP",
            "title": chunk.get("title") or "",
            "snippet": chunk.get("text") or "",
        })
    return out


def compact_planner_contract(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": contract.get("schema_version"),
        "language": contract.get("language"),
        "decision": contract.get("decision"),
        "service": contract.get("service"),
        "action": contract.get("action"),
        "case_type": contract.get("case_type"),
        "office": contract.get("office"),
        "location": contract.get("location") or {},
        "missing_slots": contract.get("missing_slots") or [],
        "followup_questions": contract.get("followup_questions") or [],
        "source_classes": contract.get("source_classes") or {},
        "expected_domains": contract.get("expected_domains") or [],
        "retrieval_query": contract.get("retrieval_query"),
        "gaps": contract.get("gaps") or [],
    }


def metadata(source: str, **extra: Any) -> dict[str, Any]:
    out = {"source": source}
    out.update(extra)
    return out


def assistant_text(row: dict[str, Any]) -> str:
    messages = row.get("messages") or []
    if not messages:
        return ""
    return str(messages[-1].get("content") or "")


def clone_with_source(row: dict[str, Any], source: str) -> dict[str, Any]:
    out = dict(row)
    out["source"] = source
    return out


def keep_base_row(row: dict[str, Any]) -> bool:
    src = row.get("source") or ""
    ans = row.get("answerability")
    if src == "v6_planner_composer_contract_json":
        return True
    if src == "v6_planner_composer_final_answer":
        return ans in {"answer", "partial", "follow_up", "off_domain"}
    if src.startswith("v6_2_"):
        return ans == "answer"
    return ans != "refuse"


def positive_v63_row(row: dict[str, Any]) -> dict[str, Any] | None:
    src = row.get("source") or ""
    if src == "v6_3_hard_negative_refusal":
        return None
    if src not in {
        "v6_3_mandatory_sentence_citations",
        "v6_3_exact_value_extraction",
        "v6_3_eval_failure_repair",
        "v6_3_service_dialogue_followup",
    }:
        return None
    ans = row.get("answerability")
    if ans == "refuse":
        return None
    return clone_with_source(row, src.replace("v6_3_", "v6_4_positive_"))


def planner_prompt(question: str, history: list[dict[str, Any]]) -> str:
    return "\n".join([
        f"Conversation history:\n{history_text(history)}",
        "",
        f"Latest user question: {question}",
        "",
        "Return the service navigator planner JSON.",
    ])


def build_planner_rows(seed_rows: list[dict[str, Any]], seed_name: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in seed_rows:
        question = str(rec.get("question") or "").strip()
        if not question:
            continue
        history = rec.get("history") or []
        frame = resolve_case(question, history, registry_path=ROOT / "corpora" / "sources_tiered.jsonl")
        contract = compact_planner_contract(planner_contract(frame))
        rows.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PLANNER_V64},
                {"role": "user", "content": planner_prompt(question, history)},
                {"role": "assistant", "content": json.dumps(contract, ensure_ascii=False, separators=(",", ":"))},
            ],
            **metadata(
                "v6_4_planner_json",
                seed_id=rec.get("id"),
                seed_name=seed_name,
                lang=contract.get("language"),
                category=contract.get("service") or rec.get("service") or rec.get("topic") or "other",
                answerability="planner",
                recommended_next_action=contract.get("decision"),
            ),
        })
    return rows


def build_dialogue_rows(seed_rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in seed_rows:
        question = str(rec.get("question") or "").strip()
        if not question:
            continue
        history = rec.get("history") or []
        frame = resolve_case(question, history, registry_path=ROOT / "corpora" / "sources_tiered.jsonl")
        contract = compact_planner_contract(planner_contract(frame))
        answer = frame.off_domain_answer or followup_answer(frame, [])
        if not answer:
            continue
        rows.append({
            "messages": [
                {"role": "system", "content": SYSTEM_DIALOGUE_V64},
                {"role": "user", "content": "\n".join([
                    f"Conversation history:\n{history_text(history)}",
                    "",
                    f"Latest user question: {question}",
                    "",
                    "Planner contract:",
                    json.dumps(contract, ensure_ascii=False, separators=(",", ":")),
                    "",
                    "Write the next assistant message.",
                ])},
                {"role": "assistant", "content": answer},
            ],
            **metadata(
                "v6_4_dialogue_response",
                seed_id=rec.get("id"),
                lang=contract.get("language"),
                category=contract.get("service") or rec.get("service") or rec.get("topic") or "other",
                answerability="follow_up" if contract.get("missing_slots") else "off_domain",
                recommended_next_action=contract.get("decision"),
            ),
        })
        if len(rows) >= limit:
            break
    return rows


def answerability_prompt(item: dict[str, Any], sources: list[dict[str, Any]]) -> str:
    return "\n".join([
        f"Latest user question: {item.get('question')}",
        "",
        source_pack_text(sources),
        "",
        "Return answerability/source-routing JSON only.",
    ])


def build_answerability_hard_negative_rows(gold_rows: list[dict[str, Any]], limit: int, seed: int) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    candidates = [r for r in gold_rows if r.get("type") in {"refusal", "ungrounded_attempt"}]
    rng.shuffle(candidates)
    rows: list[dict[str, Any]] = []
    for item in candidates[:limit]:
        sources = gold_sources(item)
        assistant = {
            "answerability": "refuse",
            "recommended_next_action": "source_discovery",
            "relevant_source_ids": [],
            "missing_slots": [],
            "followup_questions": [],
            "gaps": [{
                "type": "need_source",
                "description": "provided sources do not meaningfully answer the user's question",
            }],
        }
        rows.append({
            "messages": [
                {"role": "system", "content": SYSTEM_ANSWERABILITY_V64},
                {"role": "user", "content": answerability_prompt(item, sources)},
                {"role": "assistant", "content": json.dumps(assistant, ensure_ascii=False, separators=(",", ":"))},
            ],
            **metadata(
                "v6_4_answerability_hard_negative_json",
                seed_id=item.get("id"),
                lang=item.get("question_lang"),
                category=item.get("question_category") or "other",
                answerability="refuse_json",
                recommended_next_action="source_discovery",
            ),
        })
    return rows


def normalize_systems(row: dict[str, Any]) -> dict[str, Any]:
    src = row.get("source") or ""
    messages = [dict(m) for m in (row.get("messages") or [])]
    if not messages:
        return row
    if src.startswith("v6_4_positive_v6_3_exact") or src == "v6_4_positive_exact_value_extraction":
        messages[0]["content"] = SYSTEM_EXTRACT_V64
    elif src.startswith("v6_4_positive_") or src.startswith("v6_2_") or src == "v6_planner_composer_final_answer":
        messages[0]["content"] = SYSTEM_COMPOSER_V64
    out = dict(row)
    out["messages"] = messages
    return out


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
    for _, bucket in sorted(by_source.items()):
        rng.shuffle(bucket)
        n_val = max(1, round(len(bucket) * val_frac)) if len(bucket) >= 12 else 0
        val.extend(bucket[:n_val])
        train.extend(bucket[n_val:])
    rng.shuffle(train)
    rng.shuffle(val)
    return train, val


def quality_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_source: dict[str, int] = {}
    by_answerability: dict[str, int] = {}
    final_refusals = 0
    raw_urls = 0
    numeric_cites = 0
    source_ids = 0
    composer_refuse_rows = 0
    for row in rows:
        src = str(row.get("source") or "")
        by_source[src] = by_source.get(src, 0) + 1
        ans = str(row.get("answerability"))
        by_answerability[ans] = by_answerability.get(ans, 0) + 1
        text = assistant_text(row)
        raw_urls += len(RAW_URL_RE.findall(text))
        numeric_cites += len(BRACKET_NUMBER_RE.findall(text))
        source_ids += len(SOURCE_ID_RE.findall(text))
        is_freeform_composer = (
            src == "v6_planner_composer_final_answer"
            or src.startswith("v6_2_")
            or src.startswith("v6_4_positive_")
            or src == "v6_4_dialogue_response"
        )
        if is_freeform_composer and row.get("answerability") in {"refuse", "refuse_json"}:
            composer_refuse_rows += 1
        if is_freeform_composer and REFUSAL_MARKER_RE.search(text):
            final_refusals += 1
    return {
        "by_source": by_source,
        "by_answerability": by_answerability,
        "assistant_raw_urls": raw_urls,
        "assistant_numeric_citations": numeric_cites,
        "assistant_source_id_citations": source_ids,
        "freeform_composer_refusal_marker_rows": final_refusals,
        "freeform_composer_refuse_rows": composer_refuse_rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-train", default="corpora/sft_v6_2_train.jsonl")
    ap.add_argument("--base-val", default="corpora/sft_v6_2_val.jsonl")
    ap.add_argument("--v63-controls", default="corpora/sft_v6_3_control_rows.jsonl")
    ap.add_argument("--dialogue-seed", default="eval/service_dialogue_v5_seed500.jsonl")
    ap.add_argument("--pipeline-seed", default="eval/service_navigator_pipeline_smoke.jsonl")
    ap.add_argument("--service-eval-seed", default="eval/service_eval_expanded_v5_seed.jsonl")
    ap.add_argument("--gold", default="eval/gov_helpdesk_gold_v1.jsonl")
    ap.add_argument("--control-out", default="corpora/sft_v6_4_split_control_rows.jsonl")
    ap.add_argument("--train-out", default="corpora/sft_v6_4_train.jsonl")
    ap.add_argument("--val-out", default="corpora/sft_v6_4_val.jsonl")
    ap.add_argument("--hard-negative-limit", type=int, default=48)
    ap.add_argument("--dialogue-response-limit", type=int, default=180)
    ap.add_argument("--val-frac", type=float, default=0.08)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    base_rows = [
        normalize_systems(row)
        for row in [*load_jsonl(ROOT / args.base_train), *load_jsonl(ROOT / args.base_val)]
        if keep_base_row(row)
    ]
    v63_positive = []
    for raw in load_jsonl(ROOT / args.v63_controls):
        positive = positive_v63_row(raw)
        if positive is not None:
            v63_positive.append(normalize_systems(positive))
    dialogue_seed = load_jsonl(ROOT / args.dialogue_seed)
    pipeline_seed = load_jsonl(ROOT / args.pipeline_seed)
    service_eval_seed = load_jsonl(ROOT / args.service_eval_seed)
    planner_rows = build_planner_rows(dialogue_seed, "service_dialogue_v5_seed500")
    planner_rows.extend(build_planner_rows(pipeline_seed, "service_navigator_pipeline_smoke"))
    planner_rows.extend(build_planner_rows(service_eval_seed, "service_eval_expanded_v5_seed"))
    dialogue_rows = build_dialogue_rows(dialogue_seed, args.dialogue_response_limit)
    hard_negative_json = build_answerability_hard_negative_rows(
        load_jsonl(ROOT / args.gold),
        limit=args.hard_negative_limit,
        seed=args.seed,
    )

    control_rows = dedupe_rows([*v63_positive, *planner_rows, *dialogue_rows, *hard_negative_json])
    all_rows = dedupe_rows([*base_rows, *control_rows])
    train, val = split_rows(all_rows, args.val_frac, args.seed)

    write_jsonl(ROOT / args.control_out, control_rows)
    write_jsonl(ROOT / args.train_out, train)
    write_jsonl(ROOT / args.val_out, val)

    summary = quality_summary(all_rows)
    print("=== v6.4 split-task build ===")
    print(f"base kept: {len(base_rows)}")
    print(f"v6.3 positive controls: {len(v63_positive)}")
    print(f"planner rows: {len(planner_rows)}")
    print(f"dialogue response rows: {len(dialogue_rows)}")
    print(f"hard-negative JSON rows: {len(hard_negative_json)}")
    print(f"control rows: {len(control_rows)}")
    print(f"all rows: {len(all_rows)}")
    print(f"train: {len(train)}")
    print(f"val: {len(val)}")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2))

    if (
        summary["assistant_raw_urls"]
        or summary["assistant_numeric_citations"]
        or summary["freeform_composer_refusal_marker_rows"]
        or summary["freeform_composer_refuse_rows"]
    ):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
