#!/usr/bin/env python3
"""Capture official office pages for the four-office route animation."""

from __future__ import annotations

import csv
import re
import shutil
from pathlib import Path

from playwright.sync_api import Error, sync_playwright


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "assets" / "sources" / "four_office_route"
SCREENSHOTS = OUT / "screenshots"

SOURCES = [
    {
        "slug": "office_company_registrar",
        "label": "Office of Company Registrar",
        "route_label": "OCR / company registration",
        "url": "https://camis.ocr.gov.np/",
    },
    {
        "slug": "ird_tripureshwor",
        "label": "Inland Revenue Office Tripureshwor",
        "route_label": "IRD Tripureshwor",
        "url": "https://ird.gov.np/office/inlandrevenueofficetripureswor/",
    },
    {
        "slug": "ird_kalimati",
        "label": "Inland Revenue Office Kalimati",
        "route_label": "IRD Kalimati",
        "url": "https://ird.gov.np/office/inlandrevenueofficekalimati/",
    },
    {
        "slug": "ird_kalanki",
        "label": "Inland Revenue Office Kalanki",
        "route_label": "IRD Kalanki",
        "url": "https://ird.gov.np/office/inlandrevenueofficekalanki/",
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
            viewport={"width": 1440, "height": 1200},
            device_scale_factor=2,
            ignore_https_errors=True,
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
        )
        for idx, src in enumerate(SOURCES, 1):
            page = context.new_page()
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
                if tmp_screenshot.exists():
                    tmp_screenshot.unlink()
            rows.append(
                {
                    "index": str(idx),
                    "slug": src["slug"],
                    "label": src["label"],
                    "route_label": src["route_label"],
                    "url": src["url"],
                    "final_url": final_url,
                    "page_title": title,
                    "status": status,
                    "popup_clicks": str(popup_clicks),
                    "screenshot": str(screenshot.relative_to(ROOT)),
                    "error": error,
                }
            )
            page.close()
        browser.close()
    with (OUT / "capture_manifest.tsv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
