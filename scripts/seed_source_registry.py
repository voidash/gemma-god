#!/usr/bin/env python3
"""Seed the source registry from digobikas.gov.np's Joomla AJAX directory.

The government-websites directory at
  http://digobikas.gov.np/en/websites-en
is rendered client-side from three AJAX endpoints:

  POST /index.php?option=com_newsgov&task=newsgov.govlist
    data: filter_name={federal|province}, page=N
    -> federal ministries (1 page) or all province-level offices (2 pages)

  POST /index.php?option=com_newsgov&task=newsgov.govlocallist
    data: optionType={Province|Local level}, optionValue=<province name>, page=N
    -> per-province listings (provincial offices OR local bodies)

All three return JSON:
  {"query_data": [{"id","name_en","name_np","website","office_type",
                   "province_name_en","province_name_np"}, ...],
   "total_pages": N}

The site has an expired TLS cert; we send HTTP + --insecure. Expected total
is ~850 sources: ~25 federal + ~75 province-level + ~750 local palikas.

Output: corpora/sources.jsonl — one record per source, ready to be loaded
into the SQLite sources table. Re-running is idempotent on source_id and
preserves `first_seen` if the file already exists.

Usage:
    python scripts/seed_source_registry.py
    python scripts/seed_source_registry.py --out /custom/path.jsonl
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "http://digobikas.gov.np/index.php"
ENDPOINT_FLAT = BASE + "?option=com_newsgov&task=newsgov.govlist"
ENDPOINT_LOCAL = BASE + "?option=com_newsgov&task=newsgov.govlocallist"

PROVINCES = [
    "Province 1",
    "Province 2",
    "Province 3",
    "Gandaki Province",
    "Province 5",
    "Karnali Province",
    "Sudurpaschim Province",
]

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 gemma-god/source-registry"
)

TIMEOUT = 30.0
SLEEP_BETWEEN = 0.4  # polite spacing between requests


def _post_json(url: str, data: dict) -> dict:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "User-Agent": USER_AGENT,
            "X-Requested-With": "XMLHttpRequest",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json, text/javascript, */*",
        },
        method="POST",
    )
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def _fetch_all_pages(url: str, base_data: dict) -> list[dict]:
    """Walk pagination until total_pages. Returns all `query_data` concatenated."""
    page1 = _post_json(url, {**base_data, "page": 1})
    total = int(page1.get("total_pages") or 1)
    out: list[dict] = list(page1.get("query_data") or [])
    for p in range(2, max(total, 1) + 1):
        time.sleep(SLEEP_BETWEEN)
        pg = _post_json(url, {**base_data, "page": p})
        out.extend(pg.get("query_data") or [])
    return out


def _slug(domain: str) -> str:
    """Stable source_id from domain. 'moha.gov.np/en' -> 'moha_gov_np'."""
    d = domain.strip().lower()
    # strip scheme if someone put one in
    d = re.sub(r"^https?://", "", d)
    # keep only the authority, drop any path
    d = d.split("/", 1)[0]
    # replace anything non-alnum with underscore
    return re.sub(r"[^a-z0-9]+", "_", d).strip("_")


def _normalize_domain(website: str) -> str:
    """Strip scheme+path, keep the registrable domain authority."""
    s = website.strip()
    s = re.sub(r"^https?://", "", s)
    return s.split("/", 1)[0].lower()


def _homepage_url(website: str) -> str:
    s = website.strip()
    if not s.startswith(("http://", "https://")):
        s = "http://" + s
    return s


def _guess_tier(rec: dict) -> tuple[int, int]:
    """Return (tier, poll_interval_hours) from a raw digobikas record.

    Heuristic only. Tier 1 (gazette/constitutional) is not populated from
    digobikas — those get promoted manually in a follow-up pass (#26).
    """
    office_type = (rec.get("office_type") or "").strip().lower()
    name_en = (rec.get("name_en") or "").strip().lower()

    # Tier 5: local palikas — 48h
    if office_type == "local level":
        return 5, 48
    # Tier 4: province-level offices — 3.5 days = 84h
    if office_type == "province":
        return 4, 84
    # Federal office. Ministry vs Department distinction.
    if "ministry" in name_en:
        return 2, 12
    # Departments, autonomous offices, commissions: Tier 3, 24h
    return 3, 24


def _load_existing(path: Path) -> dict[str, dict]:
    """Read an existing sources.jsonl so we can preserve first_seen on re-run."""
    if not path.is_file():
        return {}
    out: dict[str, dict] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            sid = r.get("source_id")
            if sid:
                out[sid] = r
    return out


def _record_from_raw(rec: dict, now_iso: str, existing: dict[str, dict]) -> dict | None:
    website = (rec.get("website") or "").strip()
    if not website:
        return None
    domain = _normalize_domain(website)
    if not domain:
        return None
    source_id = _slug(domain)
    if not source_id:
        return None

    tier, poll_hours = _guess_tier(rec)
    prev = existing.get(source_id)
    first_seen = (prev or {}).get("first_seen") or now_iso

    return {
        "source_id": source_id,
        "domain": domain,
        "homepage_url": _homepage_url(website),
        "name_en": (rec.get("name_en") or "").strip(),
        "name_np": (rec.get("name_np") or "").strip(),
        "office_type": rec.get("office_type") or "",
        "province": rec.get("province_name_en"),
        "province_np": rec.get("province_name_np"),
        "tier_guess": tier,
        "poll_interval_hours": poll_hours,
        "status": "active",
        "first_seen": first_seen,
        "digobikas_id": rec.get("id"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--out",
        default="corpora/sources.jsonl",
        help="output JSONL path (default: corpora/sources.jsonl)",
    )
    args = ap.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    existing = _load_existing(out_path)
    if existing:
        print(f"[seed] found {len(existing)} existing records; preserving first_seen",
              file=sys.stderr)

    now_iso = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")

    aggregated: dict[str, dict] = {}  # source_id -> record (dedup across endpoints)
    summary: list[tuple[str, int]] = []

    # 1) federal
    print("[seed] fetching federal ...", file=sys.stderr, flush=True)
    federal = _fetch_all_pages(ENDPOINT_FLAT, {"filter_name": "federal"})
    print(f"       {len(federal)} records", file=sys.stderr)
    summary.append(("federal", len(federal)))
    for raw in federal:
        rec = _record_from_raw(raw, now_iso, existing)
        if rec:
            aggregated.setdefault(rec["source_id"], rec)

    # 2) province-level (pooled)
    time.sleep(SLEEP_BETWEEN)
    print("[seed] fetching province (pooled) ...", file=sys.stderr, flush=True)
    prov_flat = _fetch_all_pages(ENDPOINT_FLAT, {"filter_name": "province"})
    print(f"       {len(prov_flat)} records", file=sys.stderr)
    summary.append(("province_flat", len(prov_flat)))
    for raw in prov_flat:
        rec = _record_from_raw(raw, now_iso, existing)
        if rec:
            aggregated.setdefault(rec["source_id"], rec)

    # 3) per-province local bodies (palikas)
    for prov in PROVINCES:
        time.sleep(SLEEP_BETWEEN)
        print(f"[seed] fetching local-level for '{prov}' ...", file=sys.stderr,
              flush=True)
        local = _fetch_all_pages(
            ENDPOINT_LOCAL,
            {"optionType": "Local level", "optionValue": prov},
        )
        print(f"       {len(local)} records", file=sys.stderr)
        summary.append((f"local:{prov}", len(local)))
        for raw in local:
            rec = _record_from_raw(raw, now_iso, existing)
            if rec:
                # stamp province from the request context if missing
                if not rec.get("province"):
                    rec["province"] = prov
                aggregated.setdefault(rec["source_id"], rec)

    # 4) write
    with out_path.open("w", encoding="utf-8") as f:
        for rec in sorted(aggregated.values(), key=lambda r: (r["tier_guess"], r["source_id"])):
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # 5) report
    print("", file=sys.stderr)
    print(f"=== seeded {len(aggregated):,} unique sources -> {out_path} ===",
          file=sys.stderr)
    tier_counts: dict[int, int] = {}
    for r in aggregated.values():
        tier_counts[r["tier_guess"]] = tier_counts.get(r["tier_guess"], 0) + 1
    for tier in sorted(tier_counts):
        print(f"  tier {tier}: {tier_counts[tier]:>4} sources",
              file=sys.stderr)
    print("", file=sys.stderr)
    print("endpoint counts (raw, before dedup):", file=sys.stderr)
    for name, n in summary:
        print(f"  {name:<30} {n:>5}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
