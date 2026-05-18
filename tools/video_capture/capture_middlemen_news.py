#!/usr/bin/env python3
"""Capture source screenshots for the PreVillage middlemen/news montage."""

from __future__ import annotations

import csv
import re
import shutil
from pathlib import Path

from playwright.sync_api import Error, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "assets" / "sources" / "middlemen_news"
SCREENSHOTS = OUT / "screenshots"

SOURCES = [
    {
        "slug": "myrepublica_good_governance_on_hold",
        "title": "Good governance on hold as middlemen run the show",
        "url": "https://myrepublica.nagariknetwork.com/amp/news/middlemen-running-the-show-good-governance-on-hold-52-90.html",
    },
    {
        "slug": "rising_nepal_ending_sway_middlemen",
        "title": "Ending The Sway Of Middlemen",
        "url": "https://risingnepaldaily.com/news/79858",
    },
    {
        "slug": "ekantipur_middlemen_prohibited_land_revenue",
        "title": "Middlemen prohibited in land revenue and surveying",
        "url": "https://ekantipur.com/news/2026/04/01/en/now-middlemen-are-prohibited-in-land-revenue-and-surveying-making-it-easier-for-service-recipients-25-18.html",
    },
    {
        "slug": "ratopati_land_revenue_middlemen_crackdown",
        "title": "Nepal cracks down on middlemen in land offices",
        "url": "https://english.ratopati.com/story/58142/middleman-free-land-revenue-work-begins-in-10-minutes",
    },
    {
        "slug": "nepalnews_brokers_hijack_services",
        "title": "From transport to land offices, brokers hijack services nationwide",
        "url": "https://english.nepalnews.com/s/feature/from-transport-to-land-offices-brokers-hijack-services-nationwide/",
    },
    {
        "slug": "arthasarokar_sarlahi_middlemen",
        "title": "Middlemen in Sarlahi government offices",
        "url": "https://english.arthasarokar.com/2026/04/middlemen-in-sarlahi-government-offices-extorted-up-to-rs-2500-on-the-pretext-of-getting-work-done-2.html",
    },
]


def safe_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def dismiss_popups(page) -> int:
    labels = [
        "Accept",
        "I agree",
        "Got it",
        "OK",
        "Close",
        "No thanks",
        "Skip",
        "Continue",
    ]
    clicks = 0
    for label in labels:
        try:
            locator = page.get_by_text(label, exact=False)
            if locator.count() and locator.first.is_visible(timeout=500):
                locator.first.click(timeout=1000)
                clicks += 1
                page.wait_for_timeout(300)
        except Exception:
            pass
    return clicks


def main() -> None:
    SCREENSHOTS.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 1600},
            device_scale_factor=2,
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        for idx, src in enumerate(SOURCES, 1):
            screenshot = SCREENSHOTS / f"{idx:02d}_{src['slug']}.png"
            tmp_screenshot = SCREENSHOTS / f".{idx:02d}_{src['slug']}.tmp.png"
            status = "ok"
            error = ""
            final_url = ""
            title = ""
            popup_clicks = 0
            try:
                page.goto(src["url"], wait_until="domcontentloaded", timeout=45_000)
                page.wait_for_timeout(2500)
                popup_clicks += dismiss_popups(page)
                final_url = page.url
                title = safe_text(page.title())
                page.screenshot(path=str(tmp_screenshot), full_page=False)
                shutil.move(str(tmp_screenshot), str(screenshot))
            except Error as exc:
                status = "error"
                error = str(exc).replace("\n", " ")[:500]
                try:
                    if tmp_screenshot.exists():
                        tmp_screenshot.unlink()
                except Exception:
                    pass
            rows.append(
                {
                    "index": str(idx),
                    "slug": src["slug"],
                    "title_hint": src["title"],
                    "url": src["url"],
                    "final_url": final_url,
                    "page_title": title,
                    "status": status,
                    "popup_clicks": str(popup_clicks),
                    "screenshot": str(screenshot.relative_to(ROOT)),
                    "error": error,
                }
            )
        browser.close()
    with (OUT / "capture_manifest.tsv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
