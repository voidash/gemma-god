#!/usr/bin/env python3
"""Synthesize a realistic gov-office tacit-knowledge interview transcript.

Produces text that LOOKS like a real ASR transcript of an interview that
followed `tools/office_interview_template.md`. Used to bootstrap the
processing pipeline and the retrieval/eval system before any actual
fieldwork — once a real recording arrives, swap it in unchanged.

Realism notes:
- Uses three personas (officer, experienced agent, security guard) with
  distinguishable voices.
- Mixes Devanagari, Roman-Nepali, and English code-switching as a real
  Nepal-gov interview would.
- Includes false starts, partial answers, occasional "I don't know."
- Mentions specific room/counter numbers, specific procedural quirks,
  and identifiable practical tips.

Each invocation produces ONE interview (one office × one interviewee role).
Run multiple times to build a multi-perspective corpus per office.

Output: `corpora/tacit/raw/<office_slug>/<role>_<seed>.json`
        with structure: {meta: {...}, transcript: "..."}

Usage:
    # one synthetic interview, officer perspective on Jiri citizenship
    python scripts/synthesize_interview.py \
        --office jirimun \
        --service nagarikta_certificate \
        --role officer \
        --seed 1

    # build all three perspectives for one office
    for role in officer agent security_guard; do
        python scripts/synthesize_interview.py \
            --office jirimun --service nagarikta_certificate \
            --role $role --seed 1
    done

To run a small batch covering Jiri's main services:
    bash scripts/synthesize_jirimun_pilot.sh
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/anthropic")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
MAX_RETRIES = 3
TIMEOUT_S = 120


def _deepseek_key() -> str:
    if k := os.environ.get("DEEPSEEK_API_KEY"):
        return k
    fmw = Path.home() / ".fmw"
    if fmw.exists():
        for line in fmw.read_text().splitlines():
            if line.startswith("DEEPSEEK="):
                return line.split("=", 1)[1].strip()
    raise RuntimeError("DeepSeek API key not found in env or ~/.fmw")


def deepseek_chat(system: str, user: str, max_tokens: int = 6000, temperature: float = 0.85) -> str:
    payload = json.dumps({
        "model": DEEPSEEK_MODEL,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": user}],
        "thinking": {"type": "disabled"},
    }).encode("utf-8")
    api_key = _deepseek_key()
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
            last_err = RuntimeError(f"HTTP {e.code}: {body[:200]}")
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            raise last_err
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
            last_err = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"deepseek failed: {last_err}")


# ---- Office + service registry --------------------------------------------
#
# Hand-curated minimal facts about each office that the synthesizer uses as
# scaffolding. The synthesizer fills in the realistic details — quirks, room
# numbers, parking, etc. — so we end up with a transcript that's coherent
# but not fully made up.

OFFICES: dict[str, dict] = {
    "jirimun": {
        "name_en": "Jiri Municipality Office",
        "name_ne": "जिरी नगरपालिका कार्यालय",
        "domain": "jirimun.gov.np",
        "address": "Jiri-1, Dolakha",
        "context": (
            "Local-level (palika) government office serving Jiri municipality residents. "
            "Issues citizenship recommendations, birth/death/marriage registration, "
            "land tax (malpot) collection, voter ID local steps, and general ward services. "
            "It's a small office (single building, ~5-6 counters) in a hill town in Dolakha district."
        ),
    },
    "moha_passport": {
        "name_en": "Department of Passports (MOHA)",
        "name_ne": "राहदानी विभाग, गृह मन्त्रालय",
        "domain": "nepalpassport.gov.np",
        "address": "Tripureshwor, Kathmandu",
        "context": (
            "Federal-level office in Kathmandu issuing Nepali passports. Also has provincial "
            "branches. High traffic, multiple counters, biometric capture station, common queues."
        ),
    },
    "ird_pan": {
        "name_en": "Inland Revenue Office, Lazimpat (PAN registration)",
        "name_ne": "आन्तरिक राजस्व कार्यालय, लाजिम्पाट",
        "domain": "ird.gov.np",
        "address": "Lazimpat, Kathmandu",
        "context": (
            "Issues PAN and VAT numbers, handles personal and business tax registration, accepts "
            "tax filings. Has both walk-in counters and the online TaxpayerPortal."
        ),
    },
}


SERVICES: dict[str, dict] = {
    "nagarikta_certificate": {
        "name_en": "Citizenship certificate (recommendation step at municipality)",
        "name_ne": "नागरिकता प्रमाणपत्र",
        "what_it_does": (
            "At the municipality the citizen gets the local-level recommendation form filled, "
            "submitted, and signed by the ward chair. The actual citizenship certificate is "
            "issued by the District Administration Office (DAO) in Charikot, but Jiri municipality "
            "issues the prerequisite recommendation."
        ),
    },
    "passport_renewal": {
        "name_en": "Passport renewal (in-person)",
        "name_ne": "राहदानी नवीकरण",
        "what_it_does": "Standard 10-year passport renewal at MOHA Kathmandu.",
    },
    "pan_individual": {
        "name_en": "Individual PAN registration",
        "name_ne": "व्यक्तिगत प्यान दर्ता",
        "what_it_does": "Issues a Personal Identification Number for tax purposes, individual.",
    },
    "birth_registration": {
        "name_en": "Birth registration",
        "name_ne": "जन्म दर्ता",
        "what_it_does": "Local-level civil registration of births, issued at municipality / ward.",
    },
}


# ---- Persona prompts ------------------------------------------------------


PERSONAS = {
    "officer": (
        "You are an experienced gov-office officer at this desk for 4-7 years. "
        "You speak in a mix of Nepali and English/Roman-Nepali, mostly Nepali but "
        "switching to English for technical/legal terms. You are slightly formal and "
        "give official answers, but if pressed you do mention practical workarounds "
        "(without naming colleagues). You sometimes deflect to 'check the gov.np "
        "website' but the interviewer pushes you for the practical reality."
    ),
    "agent": (
        "You are a local 'document agent' or consultant — citizens pay you Rs 500-2000 "
        "to handle paperwork for them. You've been at this office almost daily for 5+ years "
        "and you know every quirk: which counter is fastest, what officers actually ask "
        "for, the photocopy shops, the unofficial reality. You speak frankly in mostly "
        "Roman-Nepali with frequent English technical terms. You're a goldmine of tacit knowledge."
    ),
    "security_guard": (
        "You are a security guard who has worked at this building for 10+ years. You don't "
        "know the procedures in detail but you know the building inside out — every room, "
        "every back door, parking, when crowds arrive, where the photocopy and tea shops are, "
        "which days are busiest. You speak simple Nepali, plain and friendly."
    ),
    "citizen": (
        "You are an ordinary citizen who recently navigated this office and got the service. "
        "You speak in a mix of Roman-Nepali and English. You're describing your experience "
        "in retrospect — what surprised you, what you wish you'd known, what tricked you up."
    ),
}


SYSTEM_INTERVIEWEE = """\
You are role-playing an interviewee at a Nepal government office, being asked questions about \
how the office actually works. Your goal is to produce a REALISTIC interview transcript \
including hesitations, code-switching between Nepali / Roman-Nepali / English, occasional \
'I don't know', specific practical detail (room numbers, fees, names of nearby shops), and \
occasional digressions. Reply ONLY with the transcript text, no preamble. Use the format:

  Q: <interviewer question>
  A: <your answer as the interviewee>

  Q: <next>
  A: ...

Make it feel real — not a polished press release. Include uneven detail (some answers are \
2 sentences, some are a paragraph, some are 'matlab… mero ta yo thaha chaina hai')."""


def build_user_prompt(office_data: dict, service_data: dict, role: str, persona: str) -> str:
    return f"""\
INTERVIEWEE PROFILE:
{persona}

OFFICE:
- Name: {office_data['name_en']} / {office_data['name_ne']}
- Address: {office_data['address']}
- Domain: {office_data['domain']}
- Context: {office_data['context']}

SERVICE BEING DISCUSSED:
- {service_data['name_en']} / {service_data['name_ne']}
- {service_data['what_it_does']}

The interview should follow this template (PART 1-10). Produce a transcript that covers
ALL ten parts, but with the interviewee's natural voice and detail level. Some parts will
be covered in 1-2 exchanges, others in several. Total transcript length: approximately
2000-3000 words. The interviewer's questions can be slightly varied/conversational —
you don't have to read the template verbatim.

Template parts to cover (each gets at least one question):
1. Office identification (location, what it serves)
2. Services this office offers
3. Process flow (which counter first, then where)
4. Logistics (hours, parking, transit, inside facilities, nearby shops)
5. Practical tips (rejection reasons, backups, accommodations)
6. Cost reality (official fee + ancillary)
7. The "did you bring X?" gotchas — questions officers commonly ask
8. Special cases (foreign citizen, NRN, minor, lost original)
9. Recent changes (last year vs now)
10. Free-form (single-most-common mistake, anything else)

Make sure the transcript includes specific concrete details:
- At least 2-3 specific room/counter numbers
- At least 1 nearby photocopy/photo shop with name + price
- At least 1 specific officer-asked gotcha question
- Specific times of day for queues
- Specific landmark for the office location
- Specific parking arrangement detail

These details can be plausible/realistic — they don't have to be 100% factual since this is
synthetic. Just make them concrete and consistent.

Begin transcript now."""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--office", required=True, choices=list(OFFICES.keys()))
    ap.add_argument("--service", required=True, choices=list(SERVICES.keys()))
    ap.add_argument(
        "--role", required=True, choices=list(PERSONAS.keys()),
        help="interviewee role (officer / agent / security_guard / citizen)",
    )
    ap.add_argument("--seed", type=int, default=1, help="just for filename uniqueness")
    ap.add_argument("--output-dir", default="corpora/tacit/raw")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    office_data = OFFICES[args.office]
    service_data = SERVICES[args.service]
    persona = PERSONAS[args.role]

    user_prompt = build_user_prompt(office_data, service_data, args.role, persona)
    logging.info(
        "synthesizing interview: office=%s service=%s role=%s seed=%d",
        args.office, args.service, args.role, args.seed,
    )
    t0 = time.time()
    transcript = deepseek_chat(
        SYSTEM_INTERVIEWEE,
        user_prompt,
        max_tokens=6000,
        temperature=0.85,
    )
    elapsed = time.time() - t0

    out_dir = Path(args.output_dir) / args.office / args.service
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.role}_{args.seed:03d}.json"
    interview = {
        "meta": {
            "office": args.office,
            "office_data": office_data,
            "service": args.service,
            "service_data": service_data,
            "role": args.role,
            "seed": args.seed,
            "method": "synthetic_pilot",
            "synthesized_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "elapsed_sec": round(elapsed, 1),
            "model": DEEPSEEK_MODEL,
        },
        "transcript": transcript,
    }
    out_path.write_text(json.dumps(interview, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n=== synthesis done ===", file=sys.stderr)
    print(f"  output: {out_path}", file=sys.stderr)
    print(f"  transcript chars: {len(transcript)}", file=sys.stderr)
    print(f"  elapsed: {elapsed:.1f}s", file=sys.stderr)

    # Show the first 500 chars as sanity
    print(f"\n--- first 500 chars ---", file=sys.stderr)
    print(transcript[:500], file=sys.stderr)
    print("...", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
