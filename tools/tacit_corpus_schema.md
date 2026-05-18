# Tacit-knowledge corpus schema

Each record represents **one extracted claim** from one interview. Multiple claims per interview, multiple interviews per office, multiple offices total.

## Why one-claim-per-record (not one-interview-per-record)

The retrieval system queries at the claim level: "where do I park at MOHA?" should return parking-specific claims, not the whole 30-minute transcript. Storing each claim atomically also lets us:
- Triangulate (3 interviewees mention the same room number → high confidence)
- Update individual facts without re-processing the whole interview
- Mark stale facts and re-verify
- Carry per-claim provenance for the UI ("from a 2026-04-30 interview with a security guard")

## Per-record JSON

```json
{
  "id": "tacit_jirimun_nagarikta_navigation_001",

  "office": {
    "name_en": "Jiri Municipality",
    "name_ne": "जिरी नगरपालिका",
    "domain": "jirimun.gov.np",
    "service_unit": "Citizenship and registration desk",
    "address": "Jiri-1, Dolakha",
    "geo": {"lat": 27.6440, "lon": 86.2300},
    "catchment": "Jiri municipality residents only"
  },

  "service": "nagarikta_certificate",
  "service_aliases": ["citizenship", "नागरिकता", "nagarikta"],

  "fact_type": "navigation",
  "claim": "First counter is room 2 (front desk for token), then room 4 for verification, then room 1 for issuance",
  "claim_lang": "english",

  "confidence": "high",
  "triangulation": {
    "supporting_interviews": ["interview_2026-04-30_RP", "interview_2026-04-30_SS"],
    "contradicting_interviews": []
  },

  "source": {
    "interview_id": "interview_2026-04-30_RP",
    "interviewee_role": "officer",
    "office_visit_date": "2026-04-30",
    "method": "field_interview",
    "transcript_offset_sec": 142
  },

  "validity": {
    "as_of": "2026-04-30",
    "expected_stale_after_days": 180,
    "last_verified": "2026-04-30"
  },

  "tags": ["counter_routing", "first_visit"],

  "anonymization": {
    "names_redacted": false,
    "redacted_spans": []
  }
}
```

## Field reference

### Required fields

| Field | Type | Notes |
|---|---|---|
| `id` | string | `tacit_<office>_<service>_<fact_type>_<NNN>` |
| `office.name_en` / `name_ne` | string | Both for cross-language retrieval |
| `office.domain` | string | gov.np subdomain |
| `office.service_unit` | string | Internal department / desk |
| `service` | string slug | snake_case, e.g. `passport_renewal` |
| `fact_type` | enum | see below |
| `claim` | string | The actual fact, 1-3 sentences |
| `claim_lang` | enum | `devanagari` / `roman_nepali` / `english` |
| `confidence` | enum | `high` / `medium` / `low` |
| `source.interview_id` | string | Links to the audio + transcript |
| `source.interviewee_role` | enum | `officer` / `agent` / `security_guard` / `citizen` / `synthetic` |
| `source.office_visit_date` | ISO date | When the interview happened |
| `source.method` | enum | `field_interview` / `synthetic_pilot` / `crowdsourced` |
| `validity.as_of` | ISO date | When the fact was true |

### `fact_type` enum

Mirrors the interview template PARTs:

- `navigation` — counter/room sequence, building layout
- `documents_official` — gov.np-listed documents
- `documents_actual` — what officers actually ask for (delta from official)
- `process_flow` — step-by-step procedure
- `logistics` — hours, parking, transit, nearby facilities
- `tips` — backup options, common mistakes, accessibility
- `cost` — fees and ancillary costs
- `officer_questions` — what officers commonly ask
- `edge_cases` — minors, NRN, foreign docs, lost originals
- `recent_changes` — policy in transition
- `general` — free-form catch-all

### `confidence`

- `high` — multiple sources agree, recent, officer-confirmed
- `medium` — single source, recent, plausible
- `low` — single source, anecdotal, contradicts other interviews

### `triangulation`

Cross-references other interview IDs that confirm or contradict this claim. Filled in during the cross-interview consistency-check pass after each office finishes ingestion.

### `validity`

`as_of` is when the fact was confirmed true. `expected_stale_after_days` is a heuristic for when to re-verify (default: 180 days; shorter for fees/policies, longer for building location). `last_verified` advances each time the fact is re-confirmed.

### `anonymization`

`names_redacted` indicates whether a redaction pass has run. `redacted_spans` lists what was removed (for audit; spans themselves can be kept opaque).

## Storage

- File-per-office: `corpora/tacit/<office_domain>/<service>/<fact_type>_<NNN>.json`
- Or flat JSONL: `corpora/tacit_unified.jsonl`
- Both formats are equivalent; pick one for retrieval-index building.

## Retrieval

The tacit corpus has its **own embedding index** (separate from gov.np). At query time, both indices are queried, results are merged, and each chunk carries its provenance label so the composer can say:

> "From the gov.np procedure (https://moha.gov.np/...): you need documents A, B, C.
> From a citizen-experience interview: officers also typically ask for a recent utility bill, and the photocopy shop next door does it for ₹5/page."

## Migration / staleness flow

Every 6 months (or on the configured `expected_stale_after_days`):
1. Mark records as `stale_pending_verify`
2. Citizen feedback (post-visit) can either confirm or contradict
3. If contradicted, mark `confidence: low`, queue for re-interview
4. If confirmed, advance `last_verified`
5. Annual re-interview pass refreshes the high-impact offices
