#!/usr/bin/env python3
"""Record product proof clips from helpdesk.ampixa.com.

The admin/WhatsApp password is read from HELP_DESK_CAPTURE_PASSWORD and is not
written to any output file.
"""

from __future__ import annotations

import base64
import csv
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import TimeoutError, sync_playwright


BASE_URL = "https://helpdesk.ampixa.com"
TEXT_REDACTOR = r"""
() => {
  const redact = () => {
    if (!document.body) return;
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const node of nodes) {
      let value = node.nodeValue || "";
      value = value.replace(/ip\s+\d{1,3}(?:\.\d{1,3}){3}/g, "ip redacted");
      value = value.replace(/Connected as\s+[^)\s]+/g, "Connected as WhatsApp Web");
      value = value.replace(/\b977\d{6,14}@s\.whatsapp\.net\b/g, "WhatsApp Web");
      node.nodeValue = value;
    }
  };
  window.setInterval(redact, 120);
}
"""


@dataclass
class Clip:
    slug: str
    title: str
    mp4: str
    webm: str
    notes: str


def convert_video(webm: Path, mp4: Path) -> None:
    subprocess.run(
        [
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
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def finalize_video(page, context, raw_dir: Path, slug: str, out_dir: Path) -> tuple[str, str]:
    video = page.video
    raw_path = Path(video.path()) if video else None
    context.close()
    if raw_path is None:
        raise RuntimeError(f"No Playwright video produced for {slug}")
    webm = raw_dir / f"{slug}.webm"
    mp4 = out_dir / f"{slug}.mp4"
    raw_path.rename(webm)
    convert_video(webm, mp4)
    return str(mp4.name), str(webm.name)


def capture_chat(pw, out_dir: Path, raw_dir: Path) -> Clip:
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={"width": 1440, "height": 1080},
        record_video_dir=str(raw_dir),
        record_video_size={"width": 1440, "height": 1080},
        ignore_https_errors=True,
    )
    context.add_init_script(TEXT_REDACTOR)
    page = context.new_page()
    page.goto(f"{BASE_URL}/chat", wait_until="domcontentloaded", timeout=30_000)
    page.wait_for_timeout(1_000)

    input_box = page.locator("textarea, input[placeholder*='Ask']").last
    input_box.fill(
        "I need help with a government office task. I don't know which office, "
        "room, document, or fee applies to me. Can you first ask me the right questions?"
    )
    input_box.press("Enter")
    page.wait_for_selector("text=Which government service do you need?", timeout=20_000)
    page.wait_for_timeout(1_500)

    input_box = page.locator("textarea, input[placeholder*='Ask']").last
    input_box.fill("Jiri Municipality office timing and which room should citizens first go to?")
    input_box.press("Enter")
    page.wait_for_selector("text=Sources used", timeout=30_000)
    page.wait_for_selector("text=Citizen interview", timeout=30_000)
    page.wait_for_timeout(3_000)

    mp4, webm = finalize_video(page, context, raw_dir, "helpdesk_chat_ask_first_sources", out_dir)
    browser.close()
    return Clip(
        "helpdesk_chat_ask_first_sources",
        "Chat intake first, then source-backed answer",
        mp4,
        webm,
        "Shows vague service prompt -> compact follow-up, then Jiri practical answer with Citizen interview source.",
    )


def capture_admin(pw, out_dir: Path, raw_dir: Path, password: str) -> Clip:
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={"width": 1440, "height": 1080},
        record_video_dir=str(raw_dir),
        record_video_size={"width": 1440, "height": 1080},
        ignore_https_errors=True,
    )
    context.add_init_script(TEXT_REDACTOR)
    page = context.new_page()
    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30_000)
    token = base64.b64encode(f"admin:{password}".encode()).decode()
    page.evaluate("(value) => localStorage.setItem('helpdesk.admin.b64', value)", token)
    page.goto(f"{BASE_URL}/admin", wait_until="domcontentloaded", timeout=30_000)
    page.wait_for_selector("text=Review interview submissions", timeout=20_000)
    page.wait_for_timeout(1_000)

    page.locator("button:has-text('Srat')").click()
    page.wait_for_selector("text=office_identity", timeout=20_000)
    page.wait_for_timeout(1_000)
    for y in (420, 420, 420):
        page.mouse.wheel(0, y)
        page.wait_for_timeout(1_000)
    page.mouse.wheel(0, -1300)
    page.wait_for_timeout(800)
    page.locator("button:has-text('man bahadur')").click()
    page.wait_for_selector("text=Approve & transcribe", timeout=20_000)
    page.wait_for_timeout(1_000)
    page.mouse.wheel(0, 900)
    page.wait_for_timeout(1_000)

    mp4, webm = finalize_video(page, context, raw_dir, "helpdesk_admin_interview_review", out_dir)
    browser.close()
    return Clip(
        "helpdesk_admin_interview_review",
        "Admin interview review and approval queue",
        mp4,
        webm,
        "Shows approved practical-source transcripts and pending interview ready for approve/transcribe.",
    )


def capture_whatsapp(pw, out_dir: Path, raw_dir: Path, password: str) -> Clip:
    browser = pw.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={"width": 1080, "height": 1440},
        record_video_dir=str(raw_dir),
        record_video_size={"width": 1080, "height": 1440},
        ignore_https_errors=True,
        http_credentials={"username": "admin", "password": password},
    )
    context.add_init_script(TEXT_REDACTOR)
    page = context.new_page()
    page.goto(f"{BASE_URL}/whatsapp", wait_until="domcontentloaded", timeout=30_000)
    page.wait_for_selector("text=PreVillage WhatsApp Demo", timeout=20_000)
    page.wait_for_timeout(1_200)

    box = page.locator("textarea[placeholder*='WhatsApp-style']").last
    box.fill("What is the official process for a Mars residence certificate in Jiri?")
    page.locator("footer button[aria-label='Send']").click()
    try:
        page.wait_for_selector("text=Officer outreach", timeout=45_000)
    except TimeoutError:
        page.wait_for_timeout(5_000)
    page.wait_for_timeout(2_500)
    page.mouse.wheel(0, 700)
    page.wait_for_timeout(1_500)

    mp4, webm = finalize_video(page, context, raw_dir, "helpdesk_whatsapp_officer_outreach", out_dir)
    browser.close()
    return Clip(
        "helpdesk_whatsapp_officer_outreach",
        "WhatsApp-style gap -> officer outreach draft",
        mp4,
        webm,
        "Shows the WhatsApp demo generating a contact-officer outreach draft when reliable sources are missing.",
    )


def write_manifest(path: Path, clips: list[Clip]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["slug", "title", "mp4", "webm", "notes"], delimiter="\t")
        writer.writeheader()
        for clip in clips:
            writer.writerow(clip.__dict__)


def main() -> int:
    password = os.environ.get("HELP_DESK_CAPTURE_PASSWORD", "")
    if not password:
        raise SystemExit("HELP_DESK_CAPTURE_PASSWORD is required")
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("helpdesk_product_captures")
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = out_dir / "recorded_webm"
    raw_dir.mkdir(exist_ok=True)

    clips: list[Clip] = []
    with sync_playwright() as pw:
        clips.append(capture_chat(pw, out_dir, raw_dir))
        clips.append(capture_admin(pw, out_dir, raw_dir, password))
        clips.append(capture_whatsapp(pw, out_dir, raw_dir, password))
    write_manifest(out_dir / "capture_manifest.tsv", clips)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
