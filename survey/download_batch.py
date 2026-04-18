#!/usr/bin/env python3
"""Parallel downloader for the gov PDF scale-validation batch.

One-off ops script (not part of the Rust crate). Reads survey/urls.txt,
downloads each URL via curl -k to survey/cdn_batch/, prints a status report.

Usage:
    python3 survey/download_batch.py
"""

import concurrent.futures
import os
import re
import subprocess
import sys
import urllib.parse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
URLS_PATH = os.path.join(SCRIPT_DIR, "urls.txt")
OUT_DIR = os.path.join(SCRIPT_DIR, "cdn_batch")
MAX_WORKERS = 8
CURL_TIMEOUT = 120  # seconds
WRAPPER_TIMEOUT = 160


def safe_filename(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.replace(".", "_")[:40]
    decoded_path = urllib.parse.unquote(parsed.path)
    base = os.path.basename(decoded_path.rstrip("/")) or "index"
    if not base.lower().endswith(".pdf"):
        base += ".pdf"
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base)[:100]
    return f"{host}__{base}"


def download(url: str) -> tuple[str, str, str]:
    out = os.path.join(OUT_DIR, safe_filename(url))
    if os.path.exists(out) and os.path.getsize(out) > 100:
        return url, out, "skip (exists)"
    try:
        result = subprocess.run(
            [
                "curl", "-kLsS",
                "-w", "%{http_code}",
                "--max-time", str(CURL_TIMEOUT),
                "-o", out, url,
            ],
            capture_output=True, text=True, timeout=WRAPPER_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        if os.path.exists(out):
            os.unlink(out)
        return url, out, "timeout"
    except Exception as e:
        return url, out, f"exc: {e}"

    code = result.stdout.strip() or "?"
    if code == "200" and os.path.exists(out) and os.path.getsize(out) > 100:
        return url, out, f"ok ({os.path.getsize(out)} bytes)"

    if os.path.exists(out) and os.path.getsize(out) == 0:
        os.unlink(out)
    return url, out, f"fail (http={code} rc={result.returncode})"


def main() -> int:
    if not os.path.isfile(URLS_PATH):
        print(f"error: urls file missing at {URLS_PATH}", file=sys.stderr)
        return 2

    os.makedirs(OUT_DIR, exist_ok=True)
    urls: list[str] = []
    with open(URLS_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                urls.append(line)

    print(f"queuing {len(urls)} downloads -> {OUT_DIR}", file=sys.stderr)
    results: list[tuple[str, str, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for r in ex.map(download, urls):
            results.append(r)

    ok = sum(1 for _, _, s in results if s.startswith("ok") or s.startswith("skip"))
    fails = [(u, s) for u, _, s in results if not (s.startswith("ok") or s.startswith("skip"))]

    for url, out, status in results:
        tag = "OK " if (status.startswith("ok") or status.startswith("skip")) else "ERR"
        print(f"[{tag}] {os.path.basename(out):<75} | {status}", file=sys.stderr)

    print(
        f"\ntotal {len(results)} | ok {ok} | fail {len(fails)}",
        file=sys.stderr,
    )
    if fails:
        print("\nfailed URLs:", file=sys.stderr)
        for url, status in fails:
            print(f"  {status:<30} {url}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
