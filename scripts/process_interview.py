#!/usr/bin/env python3
"""Process a gov-office interview into atomic tacit-knowledge claims.

Two input modes:

  --audio path/to/recording.wav       → transcribe via Gemini API, then process
  --transcript path/to/synthetic.json → skip ASR, use existing transcript text

Either way, the output is a JSONL of atomic claims following the schema in
`tools/tacit_corpus_schema.md`. Each claim is one fact extracted from the
transcript, with a `fact_type` tag and provenance back to the source
interview.

Authentication:
  Uses the Gemini API key from $GEMINI_KEY or ~/.fmw (GEMINI_KEY=...).
  This is the standalone Gemini API (not GCP Vertex / Chirp 2).

Why Gemini for ASR:
  - Excellent Nepali quality including code-switched Roman-NE
  - Single API key (no GCP service-account / billing setup)
  - One-shot transcription of a 30-minute interview is fine
    (we're not doing live streaming here)

Why DeepSeek for fact extraction:
  - Established in our codebase (refusals + MC + brief Q&A used it)
  - Cheaper than Gemini for the structured-extraction step
  - Handles JSON-output-only prompts reliably

Usage:
  # Audio path (real fieldwork)
  python scripts/process_interview.py \
      --audio recordings/2026-04-30_jirimun_officer_RP.wav \
      --office jirimun --service nagarikta_certificate \
      --interviewee-role officer

  # Transcript path (synthetic for testing)
  python scripts/process_interview.py \
      --transcript corpora/tacit/raw/jirimun/nagarikta_certificate/agent_001.json
"""
from __future__ import annotations

import argparse
import base64
import json
import logging
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path


# ---- API setup ------------------------------------------------------------


GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_MODEL_AUDIO = os.environ.get("GEMINI_AUDIO_MODEL", "gemini-2.0-flash-exp")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/anthropic")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
MAX_RETRIES = 3
TIMEOUT_S = 180


def _read_fmw(key: str) -> str:
    if v := os.environ.get(key):
        return v
    fmw = Path.home() / ".fmw"
    if fmw.exists():
        for line in fmw.read_text().splitlines():
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError(f"{key} not found in env or ~/.fmw")


# ---- Gemini audio transcription ------------------------------------------


GEMINI_TRANSCRIBE_PROMPT = """\
You are transcribing an interview about a Nepal government office. The interviewee \
may speak in Devanagari Nepali, Roman-Nepali (Nepali in Latin script), English, or \
freely code-switch between them.

Transcribe the audio faithfully. Preserve:
- Code-switching exactly as spoken (do NOT translate)
- Specific room/counter numbers, building names, shop names, fees
- Officer-asked questions in their original language (often Nepali)

Use this format, with one Q/A pair per question:

  Q: <interviewer question, in whatever language they used>
  A: <interviewee answer, in their language(s)>

  Q: <next>
  A: ...

Reply ONLY with the transcript text. No preamble, no JSON wrapper, no commentary."""


def gemini_transcribe(audio_path: Path, api_key: str) -> str:
    """Send audio to Gemini and get back a Q/A transcript.

    Gemini accepts inline audio data up to ~20 MB; for larger files use the
    File API (we add that path if it ever matters)."""
    mime, _ = mimetypes.guess_type(str(audio_path))
    if not mime or not mime.startswith("audio/"):
        # default to wav if guess_type couldn't tell
        mime = "audio/wav"
    audio_b64 = base64.b64encode(audio_path.read_bytes()).decode("ascii")

    payload = json.dumps({
        "contents": [{
            "parts": [
                {"text": GEMINI_TRANSCRIBE_PROMPT},
                {"inline_data": {"mime_type": mime, "data": audio_b64}},
            ],
        }],
        "generationConfig": {
            "temperature": 0.0,
            "maxOutputTokens": 8192,
        },
    }).encode("utf-8")

    last_err: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(
                f"{GEMINI_BASE}/models/{GEMINI_MODEL_AUDIO}:generateContent?key={api_key}",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                data = json.loads(resp.read())
            candidates = data.get("candidates", [])
            if not candidates:
                raise RuntimeError(f"no candidates in response: {data}")
            parts = candidates[0].get("content", {}).get("parts", [])
            return "".join(p.get("text", "") for p in parts).strip()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            last_err = RuntimeError(f"HTTP {e.code}: {body[:300]}")
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            raise last_err
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
            last_err = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"gemini transcribe failed: {last_err}")


# ---- DeepSeek fact extraction --------------------------------------------


def deepseek_chat(system: str, user: str, max_tokens: int = 6000, api_key: str | None = None) -> str:
    payload = json.dumps({
        "model": DEEPSEEK_MODEL,
        "max_tokens": max_tokens,
        "temperature": 0.2,  # low for structured extraction
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "thinking": {"type": "disabled"},
    }).encode("utf-8")
    if api_key is None:
        api_key = _read_fmw("DEEPSEEK")
    last_err: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            req = urllib.request.Request(
                f"{DEEPSEEK_BASE_URL}/v1/messages",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                data = json.loads(resp.read())
            parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
            return "".join(parts).strip()
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            last_err = RuntimeError(f"HTTP {e.code}: {body[:300]}")
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            raise last_err
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
            last_err = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"deepseek failed: {last_err}")


_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.M)


def _try_parse_json(text: str) -> dict | None:
    if not text:
        return None
    text = _FENCE_RE.sub("", text.strip()).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, flags=re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


SYSTEM_FACT_EXTRACTOR = """\
You extract atomic, verifiable claims from a gov-office interview transcript. \
Each claim is a single self-contained fact about how the office actually works \
that a citizen would benefit from knowing.

Rules:
1. One fact per record. Don't combine multiple facts into one claim.
2. Use the SAME language the interviewee used for that fact (Devanagari / Roman-NE / English).
3. Tag each fact with one of these fact_types:
   navigation, documents_official, documents_actual, process_flow, logistics,
   tips, cost, officer_questions, edge_cases, recent_changes, general
4. Confidence: 'high' if specific and concrete (room number, fee, shop name, etc),
   'medium' if generally true but could vary, 'low' if vague or anecdotal.
5. SKIP facts that are pure opinion, rumor, or naming individual people negatively.
6. SKIP "expedite/chai-pani" specifics — too sensitive for public corpus.
7. Reply with JSON ONLY, no preamble."""


FACT_USER_TEMPLATE = """\
Transcript from an interview at the following office:

OFFICE: {office_name_en} ({office_name_ne}) — {office_address}
SERVICE: {service_name_en}
INTERVIEWEE ROLE: {interviewee_role}

TRANSCRIPT:
'''
{transcript}
'''

Extract every atomic, useful fact. Aim for 20-50 facts from a 30-minute transcript.

Reply with JSON ONLY in this schema:
{{
  "claims": [
    {{
      "fact_type": "navigation | documents_official | documents_actual | process_flow | logistics | tips | cost | officer_questions | edge_cases | recent_changes | general",
      "claim": "<one fact, 1-3 sentences, in the same language the interviewee used>",
      "claim_lang": "devanagari | roman_nepali | english",
      "confidence": "high | medium | low",
      "tags": ["optional", "free-form", "tags"]
    }},
    ...
  ]
}}"""


# ---- Schema-compliant record build ----------------------------------------


_OFFICE_REGISTRY: dict[str, dict] = {
    # Mirror of the synthesizer's OFFICES; in production this comes from
    # corpora/sources_tiered.jsonl
    "jirimun": {
        "name_en": "Jiri Municipality Office",
        "name_ne": "जिरी नगरपालिका कार्यालय",
        "domain": "jirimun.gov.np",
        "service_unit": "Municipality main office",
        "address": "Jiri-1, Dolakha",
        "geo": {"lat": 27.6440, "lon": 86.2300},
        "catchment": "Jiri municipality residents only",
    },
    "moha_passport": {
        "name_en": "Department of Passports (MOHA)",
        "name_ne": "राहदानी विभाग, गृह मन्त्रालय",
        "domain": "nepalpassport.gov.np",
        "service_unit": "Department of Passports — main office",
        "address": "Tripureshwor, Kathmandu",
        "geo": {"lat": 27.6915, "lon": 85.3075},
        "catchment": "nationwide",
    },
    "ird_pan": {
        "name_en": "Inland Revenue Office, Lazimpat",
        "name_ne": "आन्तरिक राजस्व कार्यालय, लाजिम्पाट",
        "domain": "ird.gov.np",
        "service_unit": "PAN/VAT desk",
        "address": "Lazimpat, Kathmandu",
        "geo": {"lat": 27.7237, "lon": 85.3245},
        "catchment": "Kathmandu valley walk-ins",
    },
}


def build_records(
    office_slug: str,
    service: str,
    interview_id: str,
    interviewee_role: str,
    interview_date: str,
    method: str,
    claims: list[dict],
) -> list[dict]:
    """Turn DeepSeek-extracted claims into schema-compliant tacit-corpus records."""
    office = _OFFICE_REGISTRY.get(office_slug, {
        "name_en": office_slug, "name_ne": "", "domain": f"{office_slug}.gov.np",
        "service_unit": "", "address": "", "geo": {}, "catchment": "",
    })
    out: list[dict] = []
    for i, c in enumerate(claims, 1):
        fact_type = c.get("fact_type", "general")
        record_id = f"tacit_{office_slug}_{service}_{fact_type}_{interview_id[-10:]}_{i:03d}"
        out.append({
            "id": record_id,
            "office": office,
            "service": service,
            "service_aliases": [],
            "fact_type": fact_type,
            "claim": c.get("claim", "").strip(),
            "claim_lang": c.get("claim_lang", "english"),
            "confidence": c.get("confidence", "medium"),
            "triangulation": {"supporting_interviews": [], "contradicting_interviews": []},
            "source": {
                "interview_id": interview_id,
                "interviewee_role": interviewee_role,
                "office_visit_date": interview_date,
                "method": method,
            },
            "validity": {
                "as_of": interview_date,
                "expected_stale_after_days": 180,
                "last_verified": interview_date,
            },
            "tags": c.get("tags", []),
            "anonymization": {"names_redacted": False, "redacted_spans": []},
        })
    return out


# ---- Main ------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser()
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--audio", type=Path, help="audio file (wav, mp3, ogg, m4a)")
    src.add_argument("--transcript", type=Path,
                     help="existing transcript JSON (synthesize_interview.py output)")

    # If --audio, we need to know what the interview is about
    ap.add_argument("--office", help="office slug (jirimun, moha_passport, etc)")
    ap.add_argument("--service", help="service slug (nagarikta_certificate, etc)")
    ap.add_argument("--interviewee-role", choices=["officer", "agent", "security_guard", "citizen"],
                    default=None)
    ap.add_argument("--interview-date", default=None,
                    help="ISO date when the interview happened (default: today)")

    ap.add_argument("--output-dir", default="corpora/tacit/processed")
    ap.add_argument("--save-transcript", action="store_true",
                    help="for --audio mode, also save the raw transcript before extraction")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    # Resolve inputs
    if args.transcript:
        # Synthetic / pre-existing transcript path
        data = json.loads(args.transcript.read_text(encoding="utf-8"))
        meta = data.get("meta", {})
        transcript = data.get("transcript", "")
        office_slug = args.office or meta.get("office")
        service = args.service or meta.get("service")
        interviewee_role = args.interviewee_role or meta.get("role")
        interview_date = args.interview_date or meta.get("synthesized_at", "")[:10] or str(date.today())
        method = meta.get("method", "synthetic_pilot")
        interview_id = args.transcript.stem
        if not all([office_slug, service, interviewee_role]):
            raise SystemExit("transcript JSON missing meta; supply --office --service --interviewee-role")
    else:
        # Audio → transcribe
        if not all([args.office, args.service, args.interviewee_role]):
            raise SystemExit("--audio requires --office --service --interviewee-role")
        office_slug = args.office
        service = args.service
        interviewee_role = args.interviewee_role
        interview_date = args.interview_date or str(date.today())
        method = "field_interview"
        interview_id = args.audio.stem

        gemini_key = _read_fmw("GEMINI_KEY")
        logging.info("transcribing %s via Gemini …", args.audio.name)
        t0 = time.time()
        transcript = gemini_transcribe(args.audio, gemini_key)
        logging.info("transcribed in %.1fs (%d chars)", time.time() - t0, len(transcript))

        if args.save_transcript:
            ts_dir = Path(args.output_dir).parent / "transcripts" / office_slug / service
            ts_dir.mkdir(parents=True, exist_ok=True)
            ts_path = ts_dir / f"{interview_id}.json"
            ts_path.write_text(json.dumps({
                "meta": {
                    "office": office_slug, "service": service,
                    "role": interviewee_role, "method": method,
                    "interview_date": interview_date,
                    "audio_file": str(args.audio.resolve()),
                    "transcribed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "model": GEMINI_MODEL_AUDIO,
                },
                "transcript": transcript,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            logging.info("transcript saved → %s", ts_path)

    # Fact extraction (DeepSeek)
    office_data = _OFFICE_REGISTRY.get(office_slug, {})
    user_prompt = FACT_USER_TEMPLATE.format(
        office_name_en=office_data.get("name_en", office_slug),
        office_name_ne=office_data.get("name_ne", ""),
        office_address=office_data.get("address", ""),
        service_name_en=service,
        interviewee_role=interviewee_role,
        transcript=transcript[:30000],  # generous cap; 30k chars ~= 7-8k tokens
    )
    logging.info("extracting facts via DeepSeek …")
    t0 = time.time()
    resp = deepseek_chat(SYSTEM_FACT_EXTRACTOR, user_prompt, max_tokens=8000)
    parsed = _try_parse_json(resp)
    if not parsed or "claims" not in parsed:
        logging.error("fact extraction failed; raw response head: %s", resp[:400])
        return 1
    raw_claims = parsed["claims"]
    logging.info("extracted %d claims in %.1fs", len(raw_claims), time.time() - t0)

    records = build_records(
        office_slug, service, interview_id, interviewee_role,
        interview_date, method, raw_claims,
    )

    # Write JSONL
    out_dir = Path(args.output_dir) / office_slug / service
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{interview_id}.jsonl"
    with out_path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n=== process_interview done ===", file=sys.stderr)
    print(f"  interview_id : {interview_id}", file=sys.stderr)
    print(f"  office       : {office_slug}", file=sys.stderr)
    print(f"  service      : {service}", file=sys.stderr)
    print(f"  role         : {interviewee_role}", file=sys.stderr)
    print(f"  method       : {method}", file=sys.stderr)
    print(f"  claims       : {len(records)}", file=sys.stderr)
    print(f"  output       : {out_path}", file=sys.stderr)

    # Per-fact-type breakdown
    from collections import Counter
    by_type = Counter(r["fact_type"] for r in records)
    print(f"\n  by fact_type:", file=sys.stderr)
    for t, n in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"    {t:>22s}: {n}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
