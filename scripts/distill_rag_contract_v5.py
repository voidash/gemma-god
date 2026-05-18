#!/usr/bin/env python3
"""Distill v5 RAG-contract supervision with Claude or DeepSeek.

This is deliberately different from v4's final-answer-only distillation. For
each question, it calls the live `/retrieve` endpoint, then asks a teacher model
to produce a structured contract:

  - answerability: answer | partial | refuse | off_domain
  - relevant_source_ids: ["S1", "S3"]
  - facts: [{claim, source_ids}]
  - missing: unsupported details the user may need
  - answer: final user-facing answer citing [S#]

The student can later be trained either on the JSON contract, the final answer,
or both. The important part is that source selection and answerability become
visible labels instead of hidden behavior inside one decode.

Usage:
    python3 scripts/distill_rag_contract_v5.py \
        --base-url http://<k2-tailnet-ip>:8000 \
        --questions eval/rag_query_smoke.jsonl \
        --provider meridian \
        --model claude-sonnet-4-6 \
        --out corpora/sft_v5_rag_contract_smoke.jsonl

For DeepSeek:
    DEEPSEEK_API_KEY=... python3 scripts/distill_rag_contract_v5.py \
        --provider deepseek --model deepseek-v4-flash
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


MERIDIAN_URL = os.environ.get("MERIDIAN_URL", "http://127.0.0.1:3456")
DEEPSEEK_BASE = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/anthropic")
SOURCE_ID_RE = re.compile(r"^S\d{1,2}$")
# Match source refs inside citations. This intentionally accepts compact
# citations such as "[S1, S3]" as well as separate citations "[S1] [S3]".
ANSWER_SOURCE_REF_RE = re.compile(r"\bS\d{1,2}\b")
HINDI_ROMAN_ARTIFACT_RE = re.compile(
    r"\b("
    r"ham|hum|hamare|humare|hamara\w*|humara\w*|hamari|"
    r"aap|aapko|aapka|"
    r"kijiye|kariye|karein|"
    r"nahi|nahin|"
    r"sakta|sakti|"
    r"isliye|vartamaan|abhi|"
    r"hai|hain"
    r")\b|hamare\s+paas|humare\s+paas",
    re.I,
)
HINDI_DEVANAGARI_ARTIFACT_RE = re.compile(
    r"(?<![\u0900-\u097F])"
    r"(मैं|मेरा|मेरी|आप|आपको|नहीं|करें|कीजिए|सकता|सकती|है|हैं)"
    r"(?![\u0900-\u097F])"
)


SYSTEM = """\
You are creating supervised training data for SpeakGov, a Nepal government-service RAG helpdesk.

You must inspect the user's question and the retrieved Sources. Produce ONLY valid JSON with this schema:
{
  "answerability": "answer" | "partial" | "refuse" | "off_domain",
  "relevant_source_ids": ["S1"],
  "facts": [
    {"claim": "one atomic supported claim", "source_ids": ["S1"]}
  ],
  "missing": ["specific missing unsupported detail, if any"],
  "answer": "final concise answer in the user's language, with every factual claim cited using [S#]"
}

Rules:
- Use only the provided Sources.
- Cite by source ID like [S1], never by URL.
- Do not include raw URLs anywhere in the final answer. The UI maps [S#] citations to URLs.
- If you need to refer to a website, write "the official source [S#]" or the office name [S#].
  Never write "https://...", "http://...", or "www..." in the answer.
- Do not invent source IDs.
- If sources answer only part of the question, set answerability="partial" and answer the supported part.
- If any user-requested detail is unsupported or unavailable, set answerability="partial", not "answer".
- Refuse only when no source meaningfully addresses the question.
- If the question is harmless but outside Nepal government services, set answerability="off_domain",
  answer briefly without citations, and say you are primarily built for Nepal government services.
- If the question is outside scope and high-stakes or unsafe, set answerability="refuse" and redirect safely.
- Be location-strict: never use a local/municipality/DAO source for a different place than the user asked about.
- The final answer must match the user's language/script.
- If Question language is english, the final answer must be English.
- If Question language is devanagari, the final answer must be Devanagari Nepali.
- If Question language is roman_nepali, the final answer must be Roman Nepali in Latin script.
  Do not write Devanagari sentences for roman_nepali questions.
- Never answer in Hindi. For Roman Nepali, avoid Hindi artifacts such as "hamare paas",
  "hamarasanga", "abhi", "aap", "nahi", "sakta hai", or "kijiye"; use plain
  Roman Nepali or simple English official terms instead.
- When citing multiple sources, write separate source IDs such as [S1] [S2].
  Do not write combined citations like [S1, S2].
- Keep facts atomic. One claim per fact.
- Do not include markdown fences or commentary outside JSON.
"""


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


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
        f.flush()


def post_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {detail[:500]}") from e


def read_deepseek_key() -> str:
    def _read_key_like_kv(text: str) -> str:
        for line in text.splitlines():
            part = line.strip()
            if not part or part.startswith("#"):
                continue
            if "=" in part:
                k, v = part.split("=", 1)
                if k.strip() in {"DEEPSEEK_API_KEY", "DEEPSEEK"}:
                    return v.strip().strip("'\"")
            if "=" not in part and part.startswith("sk-"):
                # Single-line bare key file.
                return part
        return ""

    key = os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return key.strip()

    if key_file := os.environ.get("DEEPSEEK_KEY_FILE"):
        p = Path(key_file)
        if p.is_file():
            text = p.read_text(errors="ignore").strip()
            key = _read_key_like_kv(text)
            if key:
                return key

    fmw = Path.home() / ".fmw"
    if fmw.is_file():
        text = fmw.read_text(errors="ignore").strip()
        key = _read_key_like_kv(text)
        if key:
            return key
    else:
        fmw_deepseek = fmw / "deepseek"
        if fmw_deepseek.is_file():
            text = fmw_deepseek.read_text(errors="ignore").strip()
            key = _read_key_like_kv(text)
            if key:
                return key

    for candidate in [
        Path.home() / ".config" / "deepseek" / "api_key",
        Path.home() / ".deepseek" / "api_key",
        Path.home() / ".deepseek",
    ]:
        if candidate.is_file():
            text = candidate.read_text(errors="ignore").strip()
            key = _read_key_like_kv(text)
            if key:
                return key

    raise RuntimeError(
        "DeepSeek key not found; set DEEPSEEK_API_KEY, DEEPSEEK_KEY_FILE, ~/.fmw or ~/.fmw/deepseek "
        "(DEEPSEEK or DEEPSEEK_API_KEY=...), ~/.config/deepseek/api_key, ~/.deepseek, or ~/.deepseek/api_key"
    )


def call_meridian(system: str, user: str, model: str, timeout: int) -> str:
    payload = {
        "model": model,
        "max_tokens": 1800,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    data = post_json(f"{MERIDIAN_URL.rstrip('/')}/v1/messages", payload, timeout=timeout)
    parts = [
        block.get("text", "")
        for block in data.get("content", [])
        if block.get("type") == "text"
    ]
    return "".join(parts).strip()


def call_deepseek(system: str, user: str, model: str, timeout: int) -> str:
    payload = json.dumps({
        "model": model,
        "max_tokens": 1800,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "thinking": {"type": "disabled"},
    }, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{DEEPSEEK_BASE.rstrip('/')}/v1/messages",
        data=payload,
        headers={
            "content-type": "application/json",
            "x-api-key": read_deepseek_key(),
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    parts = [
        block.get("text", "")
        for block in data.get("content", [])
        if block.get("type") == "text"
    ]
    return "".join(parts).strip()


def extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    stripped = stripped.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        compacted = re.sub(r",\s*([}\]])", r"\1", stripped)
        try:
            return json.loads(compacted)
        except json.JSONDecodeError:
            pass
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end > start:
            candidate = stripped[start : end + 1]
            candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
            return json.loads(candidate)
        raise


def detect_lang(text: str) -> str:
    deva = sum(1 for c in text if "ऀ" <= c <= "ॿ")
    latin = sum(1 for c in text if c.isascii() and c.isalpha())
    if deva + latin == 0:
        return "english"
    if deva / (deva + latin) > 0.5:
        return "devanagari"
    if re.search(
        r"\b(kasari|kun|kaha|ke|chha|cha|garna|garne|parcha|huncha|chaina|"
        r"ho|ma|ko|lai|nagarikta|janu|banaune|line|kati)\b",
        text,
        re.I,
    ):
        return "roman_nepali"
    return "english"


def answer_matches_lang(answer: str, expected_lang: str) -> bool:
    deva = sum(1 for c in answer if "ऀ" <= c <= "ॿ")
    latin = sum(1 for c in answer if c.isascii() and c.isalpha())
    if expected_lang == "devanagari":
        return deva > 0 and deva >= latin * 0.4
    if expected_lang == "english":
        # English answers may include Nepali names or official role labels in
        # parentheses. Flag only when Devanagari dominates the actual answer.
        return latin > 0 and (deva <= 20 or latin >= deva * 1.5)
    # Roman Nepali is Latin-script; allow English service names/URLs but avoid
    # Devanagari-heavy answers.
    return latin > 0 and deva <= max(20, latin * 0.15)


def has_hindi_artifact(answer: str, expected_lang: str) -> bool:
    if expected_lang == "roman_nepali":
        return bool(HINDI_ROMAN_ARTIFACT_RE.search(answer))
    if expected_lang == "devanagari":
        return bool(HINDI_DEVANAGARI_ARTIFACT_RE.search(answer))
    return False


def source_prompt(retrieve_resp: dict[str, Any], max_snippet_chars: int) -> tuple[str, set[str]]:
    lines = ["Sources:"]
    valid_ids: set[str] = set()
    for src in retrieve_resp.get("sources") or []:
        source_ref = src.get("source_ref") or f"S{src.get('rank')}"
        if not SOURCE_ID_RE.fullmatch(source_ref):
            continue
        valid_ids.add(source_ref)
        label = src.get("label") or ("CITIZEN INTERVIEW" if src.get("is_tacit") else "GOV.NP")
        url = src.get("url") or ""
        host = src.get("host") or urllib.parse.urlparse(url).netloc
        title = src.get("title") or ""
        snippet = re.sub(r"\s+", " ", src.get("snippet") or "").strip()
        if len(snippet) > max_snippet_chars:
            snippet = snippet[:max_snippet_chars].rstrip() + "..."
        lines.append(f"\n[{source_ref}] {label}")
        if host:
            lines.append(f"Host: {host}")
        if url:
            lines.append(f"URL: {url}")
        if title:
            lines.append(f"Title: {title}")
        lines.append(f"Excerpt: {snippet}")
    return "\n".join(lines), valid_ids


def _host_matches(host: str, domains: list[str]) -> bool:
    host = (host or "").lower()
    return any(host == d.lower() or host.endswith("." + d.lower()) for d in domains)


def validate_contract(
    contract: dict[str, Any],
    valid_ids: set[str],
    expected_lang: str,
    sources: list[dict[str, Any]] | None = None,
    expected_domains: list[str] | None = None,
) -> list[str]:
    issues: list[str] = []
    expected_domains = expected_domains or []
    sid_hosts: dict[str, str] = {}
    for idx, src in enumerate(sources or [], 1):
        sid = src.get("source_ref") or f"S{src.get('rank') or idx}"
        if SOURCE_ID_RE.fullmatch(str(sid)):
            url = src.get("url") or ""
            sid_hosts[str(sid)] = urllib.parse.urlparse(url).netloc.lower()

    used_sids: set[str] = set()
    answerability = contract.get("answerability")
    if answerability not in {"answer", "partial", "refuse", "off_domain"}:
        issues.append("bad_answerability")

    relevant = contract.get("relevant_source_ids")
    if not isinstance(relevant, list):
        issues.append("bad_relevant_source_ids")
        relevant = []
    for sid in relevant:
        if sid not in valid_ids:
            issues.append(f"unknown_relevant_source:{sid}")
        else:
            used_sids.add(str(sid))

    facts = contract.get("facts")
    if not isinstance(facts, list):
        issues.append("bad_facts")
        facts = []
    for i, fact in enumerate(facts):
        if not isinstance(fact, dict):
            issues.append(f"bad_fact:{i}")
            continue
        if not fact.get("claim"):
            issues.append(f"empty_fact_claim:{i}")
        sids = fact.get("source_ids")
        if not isinstance(sids, list) or not sids:
            issues.append(f"bad_fact_source_ids:{i}")
            continue
        for sid in sids:
            if sid not in valid_ids:
                issues.append(f"unknown_fact_source:{sid}")
            else:
                used_sids.add(str(sid))

    answer = contract.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        issues.append("empty_answer")
        answer = ""
    for sid in ANSWER_SOURCE_REF_RE.findall(answer):
        if sid not in valid_ids:
            issues.append(f"unknown_answer_source:{sid}")
        else:
            used_sids.add(str(sid))
    if answerability in {"answer", "partial"} and not ANSWER_SOURCE_REF_RE.search(answer):
        issues.append("answer_missing_source_ref")
    if answerability == "off_domain" and used_sids:
        issues.append("off_domain_used_sources")
    if expected_domains and answerability in {"answer", "partial"}:
        if not any(_host_matches(sid_hosts.get(sid, ""), expected_domains) for sid in used_sids):
            issues.append("expected_domain_missing")
        for sid in sorted(used_sids):
            host = sid_hosts.get(sid, "")
            if host and not _host_matches(host, expected_domains):
                issues.append(f"unexpected_domain_source:{sid}:{host}")
    if re.search(r"https?://|www\.", answer):
        issues.append("raw_url_in_answer")
    missing = contract.get("missing")
    if answerability == "answer" and isinstance(missing, list) and missing:
        issues.append("answer_has_missing")
    if answer and not answer_matches_lang(answer, expected_lang):
        issues.append("answer_language_mismatch")
    if answer and has_hindi_artifact(answer, expected_lang):
        issues.append("answer_hindi_artifact")
    return issues


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
    retrieve_payload = {
        "question": rec["question"],
        "top_k_tacit": int(rec.get("top_k_tacit", top_k_tacit)),
        "top_k_gov": int(rec.get("top_k_gov", top_k_gov)),
        "history": rec.get("history") or [],
    }
    retrieve_resp = post_json(
        f"{base_url.rstrip('/')}/retrieve",
        retrieve_payload,
        timeout=timeout,
    )
    sources_text, valid_ids = source_prompt(retrieve_resp, max_snippet_chars)
    question_lang = rec.get("question_lang") or detect_lang(rec["question"])
    lang_instruction = {
        "english": "Answer language instruction: write the final answer in English. Nepali proper names may appear if copied from sources.\n\n",
        "devanagari": "Answer language instruction: write the final answer in Devanagari Nepali.\n\n",
        "roman_nepali": (
            "Answer language instruction: write the final answer in Roman Nepali using Latin script only. "
            "Do not use Devanagari sentences. Do not use Hindi words/phrases. Forbidden examples: "
            "hamare, hamarasanga, hum, aap, nahi, abhi, sakta hai, kijiye, karein, hai. "
            "Use Nepali phrasing like 'ma sanga source chaina', 'tapai', 'chaina', 'sakinna', "
            "'garnuhos', 'hernu hos'.\n\n"
        ),
    }.get(question_lang, "")
    history = rec.get("history") or []
    history_text = ""
    if history:
        turns: list[str] = []
        for turn in history[-8:]:
            role = str(turn.get("role") or "user")
            content = re.sub(r"\s+", " ", str(turn.get("content") or "")).strip()
            if content:
                turns.append(f"{role}: {content}")
        if turns:
            history_text = "Conversation history:\n" + "\n".join(turns) + "\n\n"

    expected_domains = rec.get("expected_domains") or []
    expected_domains_text = ""
    if expected_domains:
        expected_domains_text = (
            "Expected authoritative domains for this seed: "
            f"{', '.join(expected_domains)}\n"
            "If retrieved local sources are from a different place, treat them as distractors.\n\n"
        )

    user = (
        f"{history_text}"
        f"Latest question: {rec['question'].strip()}\n\n"
        f"Question language: {question_lang}\n\n"
        f"{lang_instruction}"
        f"{expected_domains_text}"
        f"Retrieval quality: {json.dumps(retrieve_resp.get('quality') or {}, ensure_ascii=False)}\n\n"
        f"{sources_text}\n\n"
        "Return the JSON contract. Reminder: the final answer must not contain raw URLs; use [S#] citations only."
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
        valid_ids,
        question_lang,
        sources=retrieve_resp.get("sources") or [],
        expected_domains=expected_domains,
    )

    return {
        "id": rec.get("id"),
        "source": "v5_rag_contract_teacher",
        "teacher_provider": provider,
        "teacher_model": model,
        "question": rec["question"],
        "history": history,
        "question_lang": question_lang,
        "topic": rec.get("topic") or rec.get("service") or retrieve_resp.get("quality", {}).get("topic"),
        "retrieve_quality": retrieve_resp.get("quality"),
        "sources": retrieve_resp.get("sources") or [],
        "contract": contract,
        "answer": contract.get("answer"),
        "validation_issues": issues,
        "teacher_ms": teacher_ms,
        "raw_teacher": raw if issues else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--questions", default="eval/rag_query_smoke.jsonl")
    ap.add_argument("--out", default="corpora/sft_v5_rag_contract.jsonl")
    ap.add_argument("--provider", choices=["meridian", "deepseek"], default="meridian")
    ap.add_argument("--model", default="")
    ap.add_argument("--top-k-tacit", type=int, default=3)
    ap.add_argument("--top-k-gov", type=int, default=5)
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-snippet-chars", type=int, default=900)
    ap.add_argument("--resume", action="store_true")
    args = ap.parse_args()

    model = args.model
    if not model:
        model = "claude-sonnet-4-6" if args.provider == "meridian" else "deepseek-v4-flash"

    rows = load_jsonl(Path(args.questions))
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
                "source": "v5_rag_contract_teacher",
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
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
