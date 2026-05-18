#!/usr/bin/env python3
"""Seed MoHA subordinate office sources from the official office directory.

The district DAO pattern alone misses many live offices and gets spellings
wrong. MoHA's own directory pages contain the authoritative DAO / Area
Administration Office / Border Administration Office links. This script parses
those pages, normalizes common malformed links, optionally verifies reachability,
and appends idempotent `add` records to `corpora/tier_overrides.jsonl`.
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
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup


DEFAULT_SOURCES = Path("corpora/sources_tiered.jsonl")
DEFAULT_OVERRIDES = Path("corpora/tier_overrides.jsonl")
DEFAULT_URLS = (
    "https://moha.gov.np/en/offices",
    "https://moha.gov.np/en/contact",
)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 gemma-god/moha-office-seed"
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


def fetch_text(url: str, timeout: float) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"},
        method="GET",
    )
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
        return resp.read().decode("utf-8", errors="replace")


def normalize_url(raw_href: str, base_url: str) -> str | None:
    if not raw_href:
        return None
    href = urllib.parse.urljoin(base_url, raw_href.strip())
    href = urllib.parse.unquote(href)

    # MoHA has several malformed links like
    # https://moha.gov.np/en/daobara.moha.gov.np. Recover the embedded domain.
    embedded = re.search(r"([a-z0-9-]+\.moha\.gov\.np)(?:[/#?]|$)", href, re.I)
    if embedded:
        domain = embedded.group(1).lower()
        if domain not in {"moha.gov.np", "www.moha.gov.np", "tfs.moha.gov.np"}:
            return f"https://{domain}"

    parsed = urllib.parse.urlparse(href)
    domain = parsed.netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    if domain.endswith(".moha.gov.np") and domain not in {"tfs.moha.gov.np"}:
        return f"{parsed.scheme or 'https'}://{domain}{parsed.path or ''}"
    return None


def clean_name(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"\s*\([^)]*\)\s*$", "", text).strip()
    return text


def office_type_for(name: str, domain: str) -> str:
    n = name.lower()
    if n.startswith("district administration office") or domain.startswith("dao"):
        return "District Administration Office"
    if n.startswith("area administration office") or domain.startswith("aao") or domain.startswith("isc"):
        return "Area Administration Office"
    if n.startswith("border administration office") or domain.startswith("bao"):
        return "Border Administration Office"
    if "hajj" in n or "commission" in n:
        return "Federal"
    return "MoHA Subordinate Office"


def tier_for(office_type: str) -> int:
    if office_type == "District Administration Office":
        return 3
    if office_type in {"Area Administration Office", "Border Administration Office"}:
        return 4
    return 3


def poll_hours_for(office_type: str) -> int:
    if office_type == "District Administration Office":
        return 24
    if office_type in {"Area Administration Office", "Border Administration Office"}:
        return 48
    return 24


def extract_offices(url: str, html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "lxml")
    found: dict[str, dict[str, str]] = {}

    def add_candidate(name: str, href: str) -> None:
        normalized = normalize_url(href, url)
        if not normalized:
            return
        domain = urllib.parse.urlparse(normalized).netloc.lower()
        name = clean_name(name)
        if not name:
            name = domain
        current = found.get(domain)
        if not current or len(name) > len(current["name_en"]):
            found[domain] = {
                "name_en": name,
                "domain": domain,
                "homepage_url": f"https://{domain}",
                "discovered_url": normalized,
                "source_page": url,
            }

    for a in soup.find_all("a", href=True):
        add_candidate(a.get_text(" ", strip=True), a["href"])

    # Leaflet popup strings contain many office links that are not normal DOM
    # anchors after rendering. Parse the raw JavaScript popup HTML too.
    for match in re.finditer(
        r"bindPopup\('(?P<body>.*?)<a\s+href=\"(?P<href>[^\"]+)\"",
        html,
        flags=re.S,
    ):
        body = re.sub(r"<br\s*/?>", "\n", match.group("body"), flags=re.I)
        name = clean_name(body.split("\n", 1)[0])
        add_candidate(name, match.group("href"))

    out: list[dict[str, str]] = []
    for rec in found.values():
        office_type = office_type_for(rec["name_en"], rec["domain"])
        rec["office_type"] = office_type
        out.append(rec)
    out.sort(key=lambda r: (r["office_type"], r["domain"]))
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
        # All MoHA office subdomains share infrastructure. When probing many of
        # them at once the host often returns 429; that still proves the domain
        # is real enough to seed and crawl later at a gentler rate.
        return {
            "url": url,
            "ok": 200 <= int(e.code) < 400 or int(e.code) == 429,
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


def override_for(rec: dict[str, str], probe: dict[str, Any] | None) -> dict[str, Any]:
    office_type = rec["office_type"]
    domain = rec["domain"]
    return {
        "op": "add",
        "source_id": source_id_from_domain(domain),
        "domain": domain,
        "homepage_url": (probe or {}).get("best_url") or rec["homepage_url"],
        "name_en": rec["name_en"],
        "name_np": "",
        "office_type": office_type,
        "province": None,
        "tier_guess": tier_for(office_type),
        "poll_interval_hours": poll_hours_for(office_type),
        "reason": (
            "MoHA official office directory source. Used for DAO/area/border "
            "administration routing, citizenship, national ID, passport routing, "
            "local administration contact, and service navigation."
        ),
    }


def append_overrides(path: Path, overrides: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        for row in overrides:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--urls", nargs="*", default=list(DEFAULT_URLS))
    ap.add_argument("--sources", default=str(DEFAULT_SOURCES))
    ap.add_argument("--overrides", default=str(DEFAULT_OVERRIDES))
    ap.add_argument("--out", default="eval/reports/moha_office_source_probe_20260511.jsonl")
    ap.add_argument("--append-overrides", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--include-unverified", action="store_true")
    ap.add_argument("--timeout", type=float, default=8.0)
    ap.add_argument("--workers", type=int, default=24)
    args = ap.parse_args()

    discovered: dict[str, dict[str, str]] = {}
    fetch_errors: list[dict[str, str]] = []
    for url in args.urls:
        try:
            html = fetch_text(url, args.timeout)
        except Exception as e:
            fetch_errors.append({"url": url, "error": f"{type(e).__name__}: {e}"})
            continue
        for rec in extract_offices(url, html):
            existing = discovered.get(rec["domain"])
            if not existing or existing["source_page"].endswith("/offices"):
                discovered[rec["domain"]] = rec

    probes: dict[str, dict[str, Any]] = {}
    if args.verify and discovered:
        with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            future_map = {pool.submit(probe_domain, d, args.timeout): d for d in discovered}
            for future in concurrent.futures.as_completed(future_map):
                domain = future_map[future]
                try:
                    probes[domain] = future.result()
                except Exception as e:
                    probes[domain] = {"domain": domain, "ok": False, "best_url": f"https://{domain}", "error": str(e)}
    else:
        probes = {
            domain: {"domain": domain, "ok": True, "best_url": f"https://{domain}", "status": None}
            for domain in discovered
        }

    existing = existing_source_ids(Path(args.sources), Path(args.overrides))
    overrides: list[dict[str, Any]] = []
    audit_rows: list[dict[str, Any]] = []
    for domain, rec in sorted(discovered.items()):
        probe = probes.get(domain) or {"domain": domain, "ok": False, "best_url": f"https://{domain}"}
        sid = source_id_from_domain(domain)
        skipped_reason = ""
        override = None
        if sid in existing:
            skipped_reason = "already_present"
        elif args.verify and not probe.get("ok") and not args.include_unverified:
            skipped_reason = "not_reachable"
        else:
            override = override_for(rec, probe)
            overrides.append(override)
            existing.add(sid)
        audit_rows.append({
            "source_id": sid,
            "domain": domain,
            "name_en": rec.get("name_en"),
            "office_type": rec.get("office_type"),
            "source_page": rec.get("source_page"),
            "discovered_url": rec.get("discovered_url"),
            "probe_ok": bool(probe.get("ok")),
            "probe_status": probe.get("status"),
            "homepage_url": (override or {}).get("homepage_url") or (probe or {}).get("best_url") or rec.get("homepage_url"),
            "skipped_reason": skipped_reason,
        })

    out_path = Path(args.out)
    if args.out:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8") as f:
            for row in audit_rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    if args.append_overrides and overrides:
        append_overrides(Path(args.overrides), overrides)

    summary = {
        "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "urls": args.urls,
        "fetch_errors": fetch_errors,
        "discovered": len(discovered),
        "probe_ok": sum(1 for r in audit_rows if r["probe_ok"]),
        "new_overrides": len(overrides),
        "already_present": sum(1 for r in audit_rows if r["skipped_reason"] == "already_present"),
        "not_reachable": sum(1 for r in audit_rows if r["skipped_reason"] == "not_reachable"),
        "appended": bool(args.append_overrides and overrides),
        "out": args.out,
    }
    print(json.dumps(summary, ensure_ascii=False))
    if not args.append_overrides:
        for row in overrides:
            print(json.dumps(row, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
