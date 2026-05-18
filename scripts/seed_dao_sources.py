#!/usr/bin/env python3
"""Seed District Administration Office (DAO/CDO) sources.

The digobikas directory does not cover district DAO subdomains consistently,
but citizenship, passport, national ID, emergency documents, and local routing
questions often need district-level authority pages. This script turns the
reviewed district list into `tier_overrides.jsonl` add records and can probe
which candidate DAO domains are reachable before adding them.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_DISTRICTS = Path("corpora/nepal_districts.jsonl")
DEFAULT_SOURCES = Path("corpora/sources_tiered.jsonl")
DEFAULT_OVERRIDES = Path("corpora/tier_overrides.jsonl")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 gemma-god/dao-source-seed"
)


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


def source_id_from_domain(domain: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", domain.lower()).strip("_")


def existing_source_ids(*paths: Path) -> set[str]:
    out: set[str] = set()
    for path in paths:
        for row in load_jsonl(path):
            source_id = row.get("source_id")
            if isinstance(source_id, str) and source_id:
                out.add(source_id)
    return out


def probe_url(url: str, timeout: float) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"},
        method="GET",
    )
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return {
                "url": url,
                "ok": 200 <= int(resp.status) < 400,
                "status": int(resp.status),
                "final_url": resp.geturl(),
                "error": "",
            }
    except urllib.error.HTTPError as e:
        return {
            "url": url,
            "ok": 200 <= int(e.code) < 400,
            "status": int(e.code),
            "final_url": url,
            "error": "",
        }
    except Exception as e:
        return {
            "url": url,
            "ok": False,
            "status": None,
            "final_url": url,
            "error": type(e).__name__,
        }


def probe_domain(domain: str, timeout: float) -> dict[str, Any]:
    urls = [
        f"https://{domain}",
        f"https://{domain}/en",
        f"https://{domain}/ne",
        f"http://{domain}",
    ]
    attempts = [probe_url(url, timeout) for url in urls]
    best = next((a for a in attempts if a["ok"]), attempts[0])
    return {
        "domain": domain,
        "ok": bool(best["ok"]),
        "best_url": best["final_url"] if best["ok"] else f"https://{domain}",
        "status": best["status"],
        "attempts": attempts,
    }


def choose_domain(
    district: dict[str, Any],
    probes: dict[str, dict[str, Any]],
    include_unverified: bool,
) -> tuple[str | None, dict[str, Any] | None]:
    for domain in district.get("dao_domains") or []:
        probe = probes.get(domain) or {"domain": domain, "ok": False, "best_url": f"https://{domain}"}
        if probe.get("ok"):
            return domain, probe
    if include_unverified:
        domains = district.get("dao_domains") or []
        if domains:
            domain = domains[0]
            return domain, probes.get(domain)
    return None, None


def override_for(district: dict[str, Any], domain: str, probe: dict[str, Any] | None) -> dict[str, Any]:
    display = district.get("display_name") or district.get("district") or domain
    homepage = (probe or {}).get("best_url") or f"https://{domain}"
    return {
        "op": "add",
        "source_id": source_id_from_domain(domain),
        "domain": domain,
        "homepage_url": homepage,
        "name_en": f"District Administration Office, {display}",
        "name_np": "",
        "office_type": "District Administration Office",
        "province": district.get("province"),
        "tier_guess": 3,
        "poll_interval_hours": 24,
        "reason": (
            "District DAO/CDO site for citizenship, passport routing, national ID, "
            "local administration contact, and district-level service navigation."
        ),
    }


def append_overrides(path: Path, overrides: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for row in overrides:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--districts", default=str(DEFAULT_DISTRICTS))
    ap.add_argument("--sources", default=str(DEFAULT_SOURCES))
    ap.add_argument("--overrides", default=str(DEFAULT_OVERRIDES))
    ap.add_argument("--out", default="")
    ap.add_argument("--append-overrides", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--include-unverified", action="store_true")
    ap.add_argument("--timeout", type=float, default=5.0)
    ap.add_argument("--workers", type=int, default=16)
    args = ap.parse_args()

    districts = load_jsonl(Path(args.districts))
    if not districts:
        print(f"no districts loaded from {args.districts}", file=sys.stderr)
        return 1

    candidate_domains = sorted({
        domain
        for row in districts
        for domain in (row.get("dao_domains") or [])
    })
    probes: dict[str, dict[str, Any]] = {}
    if args.verify:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            future_map = {pool.submit(probe_domain, d, args.timeout): d for d in candidate_domains}
            for future in concurrent.futures.as_completed(future_map):
                domain = future_map[future]
                try:
                    probes[domain] = future.result()
                except Exception as e:
                    probes[domain] = {"domain": domain, "ok": False, "best_url": f"https://{domain}", "error": str(e)}
    else:
        probes = {
            domain: {"domain": domain, "ok": True, "best_url": f"https://{domain}", "status": None}
            for domain in candidate_domains
        }

    existing = existing_source_ids(Path(args.sources), Path(args.overrides))
    overrides: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    for district in districts:
        domain, probe = choose_domain(district, probes, args.include_unverified or not args.verify)
        chosen = None
        skipped_reason = ""
        if domain:
            candidate = override_for(district, domain, probe)
            chosen = candidate
            if candidate["source_id"] in existing:
                skipped_reason = "already_present"
            else:
                overrides.append(candidate)
                existing.add(candidate["source_id"])
        else:
            skipped_reason = "no_reachable_domain"
        audit_rows.append({
            "district": district.get("district"),
            "display_name": district.get("display_name"),
            "province": district.get("province"),
            "chosen_domain": domain,
            "chosen_ok": bool((probe or {}).get("ok")),
            "chosen_status": (probe or {}).get("status"),
            "source_id": (chosen or {}).get("source_id"),
            "skipped_reason": skipped_reason,
            "candidate_domains": district.get("dao_domains") or [],
        })

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            for row in audit_rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    if args.append_overrides and overrides:
        append_overrides(Path(args.overrides), overrides)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    reachable = sum(1 for r in audit_rows if r["chosen_ok"])
    skipped = sum(1 for r in audit_rows if r["skipped_reason"])
    print(json.dumps({
        "finished_at": now,
        "districts": len(districts),
        "candidate_domains": len(candidate_domains),
        "reachable_chosen": reachable,
        "new_overrides": len(overrides),
        "skipped": skipped,
        "appended": bool(args.append_overrides and overrides),
        "out": args.out,
    }, ensure_ascii=False))

    if not args.append_overrides:
        for row in overrides:
            print(json.dumps(row, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
