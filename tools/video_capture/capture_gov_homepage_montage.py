#!/usr/bin/env python3
"""Capture a continuous browser montage of Nepali government homepages."""

from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from playwright.sync_api import Error, TimeoutError, sync_playwright


SITES = [
    ("ird.gov.np", "https://ird.gov.np", "Inland Revenue Department"),
    ("ocr.gov.np", "https://ocr.gov.np", "Office of the Company Registrar"),
    ("nepalpassport.gov.np", "https://nepalpassport.gov.np", "Department of Passports"),
    ("moha.gov.np", "https://moha.gov.np", "Ministry of Home Affairs"),
    ("donidcr.gov.np", "https://donidcr.gov.np", "National ID and Civil Registration"),
    ("dotm.gov.np", "https://dotm.gov.np", "Department of Transport Management"),
    ("dofe.gov.np", "http://dofe.gov.np/Home.aspx", "Department of Foreign Employment"),
    ("feb.gov.np", "https://feb.gov.np", "Foreign Employment Board"),
    ("mofa.gov.np", "https://mofa.gov.np", "Ministry of Foreign Affairs"),
    ("lawcommission.gov.np", "https://lawcommission.gov.np", "Nepal Law Commission"),
    ("opmcm.gov.np", "https://opmcm.gov.np/en", "Office of the Prime Minister"),
    ("election.gov.np", "https://election.gov.np", "Election Commission"),
    ("nepalpolice.gov.np", "https://nepalpolice.gov.np", "Nepal Police"),
    ("nrb.org.np", "https://nrb.org.np", "Nepal Rastra Bank"),
    ("sebon.gov.np", "https://www.sebon.gov.np", "Securities Board of Nepal"),
    ("customs.gov.np", "https://www.customs.gov.np", "Department of Customs"),
    ("jirimun.gov.np", "https://jirimun.gov.np", "Jiri Municipality"),
    ("daokathmandu.moha.gov.np", "https://daokathmandu.moha.gov.np", "DAO Kathmandu"),
    ("daolalitpur.moha.gov.np", "https://daolalitpur.moha.gov.np", "DAO Lalitpur"),
    ("daodolakha.moha.gov.np", "https://daodolakha.moha.gov.np", "DAO Dolakha"),
]


POPUP_SELECTORS = [
    "button:has-text('Close')",
    "button:has-text('close')",
    "button:has-text('CLOSE')",
    "button:has-text('Skip')",
    "button:has-text('skip')",
    "a:has-text('Close')",
    "a:has-text('Skip')",
    "[aria-label='Close']",
    "[aria-label='close']",
    ".modal button.close",
    ".modal .close",
    ".popup .close",
    ".mfp-close",
    ".fancybox-close",
    ".btn-close",
    "button.close",
    "text=×",
    "text=✕",
    "text=बन्द",
    "text=हटाउनुहोस्",
]


@dataclass
class CaptureResult:
    index: int
    domain: str
    url: str
    name: str
    final_url: str
    title: str
    status: str
    popup_clicks: int
    screenshot: str
    error: str = ""


def close_popups(page) -> int:
    clicks = 0
    for _ in range(4):
        clicked_this_round = False
        for selector in POPUP_SELECTORS:
            try:
                loc = page.locator(selector).first
                if loc.count() and loc.is_visible(timeout=300):
                    loc.click(timeout=800)
                    clicks += 1
                    clicked_this_round = True
                    page.wait_for_timeout(350)
                    break
            except (Error, TimeoutError):
                continue
        if not clicked_this_round:
            break
    try:
        page.keyboard.press("Escape")
    except Error:
        pass
    return clicks


def safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", value).strip("_")


def write_manifest(path: Path, rows: Iterable[CaptureResult]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "index",
                "domain",
                "url",
                "name",
                "final_url",
                "title",
                "status",
                "popup_clicks",
                "screenshot",
                "error",
            ],
            delimiter="\t",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(row.__dict__)


def convert_video(webm: Path, mp4: Path) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(webm),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(mp4),
    ]
    subprocess.run(cmd, check=True)


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("gov_homepage_montage_capture")
    out_dir.mkdir(parents=True, exist_ok=True)
    screenshots = out_dir / "screenshots"
    videos = out_dir / "recorded_webm"
    screenshots.mkdir(exist_ok=True)
    videos.mkdir(exist_ok=True)

    (out_dir / "sites.json").write_text(
        json.dumps(
            [
                {"domain": domain, "url": url, "name": name}
                for domain, url, name in SITES
            ],
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    results: list[CaptureResult] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(videos),
            record_video_size={"width": 1920, "height": 1080},
            ignore_https_errors=True,
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        video_path = None

        for index, (domain, url, name) in enumerate(SITES, 1):
            status = "ok"
            error = ""
            popup_clicks = 0
            screenshot_name = f"{index:02d}_{safe_name(domain)}.png"
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=25_000)
                page.wait_for_timeout(1_500)
                popup_clicks = close_popups(page)
                page.wait_for_timeout(900)
                page.screenshot(path=str(screenshots / screenshot_name), full_page=False)
                page.mouse.wheel(0, 650)
                page.wait_for_timeout(1_100)
                page.mouse.wheel(0, -650)
                page.wait_for_timeout(700)
            except Exception as exc:  # keep the montage moving through broken gov sites
                status = "error"
                error = str(exc).replace("\n", " ")[:500]
                try:
                    page.screenshot(path=str(screenshots / screenshot_name), full_page=False)
                except Exception:
                    screenshot_name = ""
            results.append(
                CaptureResult(
                    index=index,
                    domain=domain,
                    url=url,
                    name=name,
                    final_url=page.url,
                    title=page.title() if status == "ok" else "",
                    status=status,
                    popup_clicks=popup_clicks,
                    screenshot=screenshot_name,
                    error=error,
                )
            )

        video_path = page.video.path() if page.video else None
        context.close()
        browser.close()

    write_manifest(out_dir / "capture_manifest.tsv", results)
    if video_path:
        raw_webm = out_dir / "gov_homepage_montage_20sites.webm"
        Path(video_path).rename(raw_webm)
        convert_video(raw_webm, out_dir / "gov_homepage_montage_20sites.mp4")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
