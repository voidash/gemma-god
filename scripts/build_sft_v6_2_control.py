#!/usr/bin/env python3
"""Build v6.2 SFT rows focused on citation/source-control behavior.

v6.1 improved the refusal habit but still emitted `[1]`, raw URLs, missing
citations, and refusal tails. This builder creates targeted rows from the
reviewed-gold grounded contracts:

- normal final-answer rows with normalized `[S#]` citations;
- rewrite rows that repair `[1]` / raw URL / refusal-tail drafts;
- a combined train/val split that keeps v6.1 rows and adds the control rows.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import urllib.parse
from pathlib import Path
from typing import Any


SYSTEM_FINAL_V62 = """\
You are SpeakGov, a Nepal government-service navigator.
Use only the provided Sources and planner/composer contract. Answer in plain chat.
Every factual claim that comes from a source must cite source IDs like [S1] or [S2].
Never cite raw URLs. Never use numeric citations like [1]. Never append a fallback refusal after a source-backed answer.
If the sources do not support the answer, say the specific gap and ask a compact follow-up if needed.
Match the user's language/script and never answer in Hindi."""

SYSTEM_REWRITE_V62 = """\
You are a strict final-answer editor for SpeakGov.
Rewrite the draft answer so it follows these rules:
- keep only facts supported by the provided Sources;
- cite source-backed facts with source IDs like [S1], never raw URLs and never [1];
- remove fallback refusal tails when the answer is already source-backed;
- preserve the user's language/script;
- output only the corrected final answer."""

RAW_URL_RE = re.compile(r"https?://[^\s\]\)>'\"`]+")
BRACKET_NUMBER_RE = re.compile(r"\[(\d{1,2})\]")
SOURCE_ID_RE = re.compile(r"\[S(\d{1,2})\]")
REFUSAL_TAIL_PATTERNS = [
    re.compile(r"(?:।|\.)?\s*मलाई[^\n।.]{0,80}स्रोत[^\n।.]{0,50}भेटि[^\n।.]*[।.]?\s*$", re.U),
    re.compile(r"(?:।|\.)?\s*मलाई[^\n।.]{0,80}आधिकारिक[^\n।.]{0,80}(?:छैन|भेटि|पाइ)[^\n।.]*[।.]?\s*$", re.U),
    re.compile(r"(?:\.|\।)?\s*I (?:cannot|can't|could not)[^\n.]{0,100}(?:source|information|answer)[^\n.]*\.?\s*$", re.I),
    re.compile(r"(?:\.|\।)?\s*(?:adhikarik\s+)?(?:srot|source)[^\n.]{0,80}(?:chaina|bhetina|bhetena)[^\n.]*\.?\s*$", re.I),
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
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


def normalize_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(url.strip().rstrip(".,;:!?)>\"'"))
        path = urllib.parse.unquote(parsed.path).rstrip("/")
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return f"{host}{path}"
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


def sid_for_url(url: str, sources: list[dict[str, Any]]) -> str | None:
    wanted = normalize_url(url)
    if not wanted:
        return None
    for idx, src in enumerate(sources, 1):
        src_url = str(src.get("url") or "")
        if not src_url:
            continue
        if normalize_url(src_url) == wanted:
            return source_ref(src, idx)
    for idx, src in enumerate(sources, 1):
        src_url = str(src.get("url") or "")
        if src_url and (wanted in normalize_url(src_url) or normalize_url(src_url) in wanted):
            return source_ref(src, idx)
    return None


def strip_refusal_tail(text: str) -> str:
    out = text.strip()
    for pat in REFUSAL_TAIL_PATTERNS:
        out = pat.sub("", out).strip()
    return out


def normalize_citations(text: str, sources: list[dict[str, Any]]) -> str:
    out = strip_refusal_tail(text)

    def replace_url(match: re.Match[str]) -> str:
        url = match.group(0).rstrip(".,;:!?)>\"'")
        sid = sid_for_url(url, sources)
        return f"[{sid}]" if sid else ""

    out = RAW_URL_RE.sub(replace_url, out)

    def replace_num(match: re.Match[str]) -> str:
        n = int(match.group(1))
        if 1 <= n <= max(1, len(sources)):
            return f"[S{n}]"
        return match.group(0)

    out = BRACKET_NUMBER_RE.sub(replace_num, out)
    out = re.sub(r"\[\s*(S\d{1,2})\s*\]", r"[\1]", out)
    out = re.sub(r"\s+([।.,;:!?])", r"\1", out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out


def has_valid_source_citation(text: str) -> bool:
    return bool(SOURCE_ID_RE.search(text))


def has_bad_citation(text: str) -> bool:
    return bool(RAW_URL_RE.search(text) or BRACKET_NUMBER_RE.search(text))


def canonical_contract(contract: dict[str, Any], final_answer: str) -> dict[str, Any]:
    keep = dict(contract)
    keep["final_answer"] = final_answer
    return keep


def build_final_prompt(rec: dict[str, Any], final_answer: str) -> str:
    return "\n".join([
        "Conversation history:\n(none)",
        "",
        f"Latest user question: {rec.get('question')}",
        "",
        source_pack_text(rec.get("sources") or []),
        "",
        "Planner/composer contract:",
        json.dumps(canonical_contract(rec.get("contract") or {}, final_answer), ensure_ascii=False, separators=(",", ":")),
        "",
        "Write the next assistant message.",
    ])


def corrupt_numeric(answer: str) -> str:
    return SOURCE_ID_RE.sub(lambda m: f"[{m.group(1)}]", answer)


def corrupt_raw_url(answer: str, sources: list[dict[str, Any]]) -> str:
    def repl(match: re.Match[str]) -> str:
        n = int(match.group(1))
        if 1 <= n <= len(sources):
            return str(sources[n - 1].get("url") or match.group(0))
        return match.group(0)
    return SOURCE_ID_RE.sub(repl, answer)


def corrupt_tail(answer: str, lang: str) -> str:
    if lang == "roman_nepali":
        return answer.rstrip() + " Adhikarik srot bhetina."
    if lang == "english":
        return answer.rstrip() + " I cannot find an authoritative source for this question."
    return answer.rstrip() + " मलाई यो प्रश्नको आधिकारिक स्रोत भेटिनँ।"


def repair_prompt(rec: dict[str, Any], draft: str) -> str:
    return "\n".join([
        f"Latest user question: {rec.get('question')}",
        "",
        source_pack_text(rec.get("sources") or []),
        "",
        "Draft answer:",
        draft,
        "",
        "Rewrite the draft into the corrected final answer.",
    ])


def metadata(rec: dict[str, Any], source: str) -> dict[str, Any]:
    contract = rec.get("contract") or {}
    return {
        "source": source,
        "lang": rec.get("question_lang") or "mixed",
        "category": rec.get("topic") or rec.get("service") or "other",
        "answerability": contract.get("answerability") or "answer",
        "recommended_next_action": contract.get("recommended_next_action") or "answer",
        "seed_id": rec.get("id"),
    }


def build_control_rows(contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for rec in contracts:
        if rec.get("validation_issues"):
            continue
        contract = rec.get("contract") or {}
        if contract.get("answerability") != "answer":
            continue
        sources = rec.get("sources") or []
        original = str(contract.get("final_answer") or rec.get("answer") or "").strip()
        answer = normalize_citations(original, sources)
        if not answer or has_bad_citation(answer) or not has_valid_source_citation(answer):
            continue

        rows.append({
            "messages": [
                {"role": "system", "content": SYSTEM_FINAL_V62},
                {"role": "user", "content": build_final_prompt(rec, answer)},
                {"role": "assistant", "content": answer},
            ],
            **metadata(rec, "v6_2_source_id_final_answer"),
        })

        drafts = [
            ("v6_2_rewrite_numeric_citations", corrupt_numeric(answer)),
            ("v6_2_rewrite_raw_url_citations", corrupt_raw_url(answer, sources)),
            ("v6_2_rewrite_refusal_tail", corrupt_tail(answer, rec.get("question_lang") or "")),
        ]
        for source, draft in drafts:
            if draft == answer:
                continue
            rows.append({
                "messages": [
                    {"role": "system", "content": SYSTEM_REWRITE_V62},
                    {"role": "user", "content": repair_prompt(rec, draft)},
                    {"role": "assistant", "content": answer},
                ],
                **metadata(rec, source),
            })
    return rows


def dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
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
    for source, bucket in sorted(by_source.items()):
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
    ap.add_argument("--base-train", default="corpora/sft_v6_1_train.jsonl")
    ap.add_argument("--base-val", default="corpora/sft_v6_1_val.jsonl")
    ap.add_argument("--control-out", default="corpora/sft_v6_2_control_rows.jsonl")
    ap.add_argument("--train-out", default="corpora/sft_v6_2_train.jsonl")
    ap.add_argument("--val-out", default="corpora/sft_v6_2_val.jsonl")
    ap.add_argument("--val-frac", type=float, default=0.08)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    contracts = load_jsonl(Path(args.contracts))
    control = build_control_rows(contracts)
    write_jsonl(Path(args.control_out), control)

    base_train = load_jsonl(Path(args.base_train))
    base_val = load_jsonl(Path(args.base_val))
    c_train, c_val = split_rows(control, args.val_frac, args.seed)
    train = dedupe_rows(base_train + c_train)
    val = dedupe_rows(base_val + c_val)
    write_jsonl(Path(args.train_out), train)
    write_jsonl(Path(args.val_out), val)

    print("=== v6.2 control build ===")
    print(f"contracts: {len(contracts)}")
    print(f"control rows: {len(control)}")
    print(f"train: {len(train)} ({len(base_train)} base + {len(c_train)} control before dedupe)")
    print(f"val: {len(val)} ({len(base_val)} base + {len(c_val)} control before dedupe)")
    by_source: dict[str, int] = {}
    for row in control:
        by_source[row["source"]] = by_source.get(row["source"], 0) + 1
    print(json.dumps(by_source, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
