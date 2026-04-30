#!/usr/bin/env python3
"""First-pass crawler for Nepal gov sources.

Reads `corpora/sources_tiered.jsonl`, walks each source's homepage BFS-style
to a bounded depth (same-host only), captures every HTML page and PDF, and
extracts text from HTML via trafilatura. Writes a per-source manifest.

Resumable — a doc URL whose content_hash matches its manifest entry is
skipped on re-run. This same pattern is what the scheduled poller (task #28)
will use for diff-based re-ingest.

Output layout (under --out-root, default /Volumes/T9/gemma-god/corpus_v2):

    raw/<source_id>/<doc_hash>.<ext>          # raw bytes (html/pdf)
    extracted/<source_id>/<doc_hash>.txt      # readable text, HTML only
    manifests/<source_id>.jsonl               # one line per fetched doc
    fetch.log                                 # stderr of current run

Usage:
    python scripts/crawl_sources.py --tiers 1 2
    python scripts/crawl_sources.py --tiers 1 --max-pages 20   # sanity
    python scripts/crawl_sources.py --sources ird_gov_np,ocr_gov_np
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import random
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from pathlib import Path

# Deps: pip install beautifulsoup4 lxml trafilatura
try:
    from bs4 import BeautifulSoup
    import trafilatura
except ImportError as e:
    print(f"error: missing dep ({e}). run: uv pip install beautifulsoup4 lxml trafilatura",
          file=sys.stderr)
    raise SystemExit(2)


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "gemma-god-crawler/0.1 (+corpus for public gov info RAG)"
)
FETCH_TIMEOUT = 30.0
RATE_LIMIT_SEC = 1.0  # per-domain
JITTER_SEC = 0.3
MAX_BYTES = 50 * 1024 * 1024  # 50 MB cap per doc

# Extensions we never try to fetch (binary assets that aren't docs).
SKIP_EXTS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico",
    ".mp3", ".mp4", ".avi", ".mov", ".mkv", ".webm", ".wav", ".ogg",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".zip", ".rar", ".tar", ".gz", ".7z",
    ".css", ".js", ".map",
}
# Extensions we treat as docs worth saving.
DOC_EXTS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".csv"}


def _make_ssl_ctx() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _safe_url(url: str) -> str:
    """Re-encode unsafe characters in the path + query so urllib accepts it.

    Nepal gov sites frequently link PDFs with raw spaces or Devanagari in the
    path ('/resources/Manual/New Registration.pdf'); Python urllib raises
    InvalidURL on those. quote() with safe chars that are already URL-legal
    preserves existing %-encoded bytes.
    """
    u = urllib.parse.urlsplit(url)
    safe_path = urllib.parse.quote(u.path, safe="/%:@!$&'()*+,;=~-._")
    safe_query = urllib.parse.quote(u.query, safe="=&%:@!$'()*+,;/?~-._")
    return urllib.parse.urlunsplit((u.scheme, u.netloc, safe_path, safe_query, ""))


def _fetch(url: str) -> tuple[int, str, bytes]:
    """Return (http_status, content_type, body_bytes). Raises on network error.

    TLS-tolerant (expired certs on .gov.np) and size-capped.
    """
    req = urllib.request.Request(_safe_url(url), headers={"User-Agent": USER_AGENT,
                                                           "Accept": "*/*"})
    with urllib.request.urlopen(
        req, timeout=FETCH_TIMEOUT, context=_make_ssl_ctx()
    ) as resp:
        status = resp.status
        ct = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        body = resp.read(MAX_BYTES + 1)
        if len(body) > MAX_BYTES:
            body = body[:MAX_BYTES]
    return status, ct, body


def _host(url: str) -> str:
    return (urllib.parse.urlparse(url).hostname or "").lower()


def _ext(url: str) -> str:
    p = urllib.parse.urlparse(url).path.lower()
    m = re.search(r"\.[a-z0-9]{1,6}$", p)
    return m.group(0) if m else ""


def _is_fetchable(url: str) -> bool:
    if not url.startswith(("http://", "https://")):
        return False
    e = _ext(url)
    if e in SKIP_EXTS:
        return False
    return True


MAX_PATH_LEN = 500
MAX_PATH_SEGMENTS = 15
MAX_REPEATED_SEGMENTS = 2  # any segment may appear at most this many times


def _path_is_pathological(path: str) -> bool:
    """Detect relative-path compounding traps (e.g. supremecourt.gov.np's
    /assets/downloads/judgements/assets/downloads/judgements/...).

    Two guards: absolute path length, and repeated-segment count. Either
    triggering rejects the URL.
    """
    if len(path) > MAX_PATH_LEN:
        return True
    segs = [s for s in path.split("/") if s]
    if len(segs) > MAX_PATH_SEGMENTS:
        return True
    counts: dict[str, int] = {}
    for s in segs:
        counts[s] = counts.get(s, 0) + 1
        if counts[s] > MAX_REPEATED_SEGMENTS:
            return True
    return False


def _canonicalize(base: str, href: str) -> str | None:
    try:
        joined = urllib.parse.urljoin(base, href)
    except Exception:
        return None
    u = urllib.parse.urlparse(joined)
    if u.scheme not in ("http", "https"):
        return None
    if _path_is_pathological(u.path):
        return None
    # drop fragment; preserve query
    cleaned = u._replace(fragment="")
    return urllib.parse.urlunparse(cleaned)


def _same_site(host_a: str, host_b: str) -> bool:
    """Same-site = same registrable domain (modulo single-level subdomains).

    moha.gov.np / www.moha.gov.np / aaosatbise.moha.gov.np -> same site.
    """
    if not host_a or not host_b:
        return False
    ha = host_a.split(".")
    hb = host_b.split(".")
    # Match on the last 3 labels (xxx.gov.np) — conservative, avoids
    # wandering to a different ministry via a shared parent.
    return ha[-3:] == hb[-3:]


def _extract_links_from_html(base_url: str, html_bytes: bytes) -> list[str]:
    try:
        soup = BeautifulSoup(html_bytes, "lxml")
    except Exception:
        return []
    out: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        c = _canonicalize(base_url, href)
        if c and _is_fetchable(c):
            out.add(c)
    return sorted(out)


def _extract_text_from_html(html_bytes: bytes, url: str) -> str:
    # Prefer trafilatura for main-content extraction; fall back to bs4 if empty.
    try:
        html_text = html_bytes.decode("utf-8", errors="replace")
    except Exception:
        html_text = ""
    if html_text:
        try:
            t = trafilatura.extract(
                html_text,
                url=url,
                include_comments=False,
                include_tables=True,
                favor_recall=True,
            )
            if t and t.strip():
                return t.strip()
        except Exception:
            pass
    # Fallback: raw text via bs4
    try:
        soup = BeautifulSoup(html_bytes, "lxml")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        txt = soup.get_text(separator="\n", strip=True)
        return "\n".join(line for line in txt.splitlines() if line.strip())
    except Exception:
        return ""


def _doc_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()[:16]


def _url_hash(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _load_manifest(path: Path) -> dict[str, dict]:
    """Return {url: record} for an existing manifest (resumability)."""
    out: dict[str, dict] = {}
    if not path.is_file():
        return out
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                u = r.get("url")
                if u:
                    out[u] = r
            except Exception:
                continue
    return out


def _append_manifest(path: Path, rec: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _classify_content_type(ct: str, ext: str) -> str:
    ct_l = (ct or "").lower()
    if "html" in ct_l:
        return "html"
    if "pdf" in ct_l or ext == ".pdf":
        return "pdf"
    if ext in DOC_EXTS:
        return ext.lstrip(".")
    return "other"


def crawl_source(src: dict, out_root: Path, *, max_depth: int, max_pages: int,
                 max_pdf_depth: int, max_source_fetches: int,
                 max_source_elapsed_sec: int, now_iso: str) -> dict:
    sid = src["source_id"]
    homepage = src["homepage_url"]
    home_host = _host(homepage)
    if not home_host:
        return {"source_id": sid, "status": "bad_homepage", "pages": 0}

    raw_dir = out_root / "raw" / sid
    ext_dir = out_root / "extracted" / sid
    man_dir = out_root / "manifests"
    raw_dir.mkdir(parents=True, exist_ok=True)
    ext_dir.mkdir(parents=True, exist_ok=True)
    man_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = man_dir / f"{sid}.jsonl"

    already = _load_manifest(manifest_path)
    visited: set[str] = set(already.keys())
    # Two queues so PDFs always drain first (and outside the HTML page budget).
    # HTML pages are the expensive exploration budget; PDFs are the target.
    html_queue: deque[tuple[str, int]] = deque([(homepage, 0)])
    pdf_queue: deque[tuple[str, int]] = deque()
    html_fetched = 0
    pages_skipped_resume = 0
    errors = 0
    pdfs_found = 0
    html_pages = 0

    print(f"\n=== {sid:<28} tier={src.get('tier_guess','?')} home={homepage}",
          file=sys.stderr, flush=True)
    print(f"    resume: {len(already)} docs already in manifest",
          file=sys.stderr)

    src_t0 = time.time()

    def _budget_ok() -> bool:
        if html_pages + pdfs_found + errors >= max_source_fetches:
            return False
        if time.time() - src_t0 > max_source_elapsed_sec:
            return False
        return True

    def _pop_next():
        # Always drain PDFs first; HTML queue is bounded by max_pages.
        if pdf_queue:
            return pdf_queue.popleft(), "pdf"
        if html_queue and html_fetched < max_pages:
            return html_queue.popleft(), "html"
        return None, None

    stop_reason = "queue_drained"
    while True:
        if not _budget_ok():
            stop_reason = ("source_elapsed_cap"
                           if time.time() - src_t0 > max_source_elapsed_sec
                           else "source_fetch_cap")
            break
        item, kind = _pop_next()
        if item is None:
            break
        url, depth = item
        if url in visited:
            pages_skipped_resume += 1
            continue
        visited.add(url)

        # Rate limit per-domain with jitter
        time.sleep(RATE_LIMIT_SEC + random.uniform(0, JITTER_SEC))

        try:
            status, ct, body = _fetch(url)
        except urllib.error.HTTPError as e:
            errors += 1
            _append_manifest(manifest_path, {
                "url": url, "depth": depth, "fetched_at": now_iso,
                "status": e.code, "error": f"HTTPError {e.code}",
            })
            continue
        except Exception as e:
            errors += 1
            _append_manifest(manifest_path, {
                "url": url, "depth": depth, "fetched_at": now_iso,
                "status": 0, "error": f"{type(e).__name__}: {e}",
            })
            continue

        if status >= 400:
            _append_manifest(manifest_path, {
                "url": url, "depth": depth, "fetched_at": now_iso,
                "status": status,
            })
            continue

        dhash = _doc_hash(body)
        ext = _ext(url)
        doc_type = _classify_content_type(ct, ext)

        # Persist raw body
        raw_ext = (".html" if doc_type == "html"
                   else (".pdf" if doc_type == "pdf"
                         else (ext if ext else ".bin")))
        raw_path = raw_dir / f"{dhash}{raw_ext}"
        if not raw_path.exists():
            raw_path.write_bytes(body)

        rec = {
            "url": url,
            "depth": depth,
            "fetched_at": now_iso,
            "status": status,
            "content_type": ct,
            "doc_type": doc_type,
            "content_hash": dhash,
            "size_bytes": len(body),
            "raw_path": str(raw_path.relative_to(out_root)),
        }

        if doc_type == "html":
            html_pages += 1
            html_fetched += 1
            text = _extract_text_from_html(body, url)
            if text:
                text_path = ext_dir / f"{dhash}.txt"
                if not text_path.exists():
                    text_path.write_text(text, encoding="utf-8")
                rec["extracted_path"] = str(text_path.relative_to(out_root))
                rec["text_chars"] = len(text)
            else:
                rec["text_chars"] = 0
            # BFS expansion: split discovered links into HTML vs PDF queues.
            # Within max_depth → HTML goes to html_queue; PDFs go to pdf_queue
            # regardless of depth (PDFs are the target, always capture).
            for link in _extract_links_from_html(url, body):
                if link in visited:
                    continue
                if not _same_site(_host(link), home_host):
                    continue
                link_ext = _ext(link)
                new_depth = depth + 1
                if link_ext == ".pdf" or link_ext in DOC_EXTS:
                    # PDFs are the target — but still bound by max_pdf_depth
                    # so we don't chase compounding relative paths forever.
                    if new_depth <= max_pdf_depth:
                        pdf_queue.append((link, new_depth))
                elif new_depth <= max_depth:
                    html_queue.append((link, new_depth))
        elif doc_type == "pdf":
            pdfs_found += 1
            rec["text_chars"] = 0  # defer PDF text extraction to ingest step

        _append_manifest(manifest_path, rec)
        total_fetched = html_pages + pdfs_found + errors
        if total_fetched % 20 == 0:
            print(f"    [{html_pages}/{max_pages}h  +{pdfs_found}pdf] "
                  f"depth={depth} err={errors} "
                  f"html_q={len(html_queue)} pdf_q={len(pdf_queue)}",
                  file=sys.stderr, flush=True)

    summary = {
        "source_id": sid,
        "status": "ok",
        "stop_reason": stop_reason,
        "elapsed_sec": round(time.time() - src_t0, 1),
        "pages_resume_skip": pages_skipped_resume,
        "html_pages": html_pages,
        "pdfs_found": pdfs_found,
        "errors": errors,
        "html_queue_remaining": len(html_queue),
        "pdf_queue_remaining": len(pdf_queue),
    }
    print(f"    done: html={html_pages} pdf={pdfs_found} err={errors} "
          f"stop={stop_reason} elapsed={summary['elapsed_sec']:.0f}s",
          file=sys.stderr, flush=True)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sources-file", default="corpora/sources_tiered.jsonl")
    ap.add_argument("--out-root", default="/Volumes/T9/gemma-god/corpus_v2")
    ap.add_argument("--tiers", type=int, nargs="+", default=[1, 2],
                    help="Which tiers to crawl. Default: 1 2")
    ap.add_argument("--sources", default=None,
                    help="Comma-separated source_ids to crawl (overrides --tiers)")
    ap.add_argument("--max-depth", type=int, default=2,
                    help="HTML-page BFS depth limit")
    ap.add_argument("--max-pdf-depth", type=int, default=3,
                    help="Depth limit for PDF enqueue (PDFs often live one "
                         "hop below content pages; allow a bit more)")
    ap.add_argument("--max-pages", type=int, default=250,
                    help="Per-source cap on HTML fetches")
    ap.add_argument("--max-source-fetches", type=int, default=1500,
                    help="Per-source hard cap on total fetches (html+pdf+err)")
    ap.add_argument("--max-source-elapsed-sec", type=int, default=1200,
                    help="Per-source wallclock cap; breaks runaways")
    ap.add_argument("--max-sources", type=int, default=None,
                    help="Stop after this many sources (for sanity runs)")
    args = ap.parse_args()

    out_root = Path(args.out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    # Load sources
    sources: list[dict] = []
    with Path(args.sources_file).open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            sources.append(json.loads(line))

    if args.sources:
        wanted = {s.strip() for s in args.sources.split(",") if s.strip()}
        filtered = [s for s in sources if s["source_id"] in wanted]
        missing = wanted - {s["source_id"] for s in filtered}
        if missing:
            print(f"warn: unknown source_ids: {sorted(missing)}", file=sys.stderr)
    else:
        filtered = [s for s in sources if s.get("tier_guess") in set(args.tiers)]

    if args.max_sources:
        filtered = filtered[: args.max_sources]

    filtered.sort(key=lambda s: (s.get("tier_guess", 99), s["source_id"]))

    print(f"[crawl] {len(filtered)} sources (tiers {args.tiers}); "
          f"depth<={args.max_depth}, max_pages={args.max_pages}",
          file=sys.stderr)
    now_iso = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    t0 = time.time()
    summaries = []
    for i, src in enumerate(filtered):
        print(f"\n[{i+1}/{len(filtered)}] {src['source_id']} ...",
              file=sys.stderr)
        try:
            s = crawl_source(src, out_root,
                             max_depth=args.max_depth,
                             max_pdf_depth=args.max_pdf_depth,
                             max_pages=args.max_pages,
                             max_source_fetches=args.max_source_fetches,
                             max_source_elapsed_sec=args.max_source_elapsed_sec,
                             now_iso=now_iso)
        except KeyboardInterrupt:
            print("\n[crawl] interrupted by user", file=sys.stderr)
            break
        except Exception as e:
            print(f"    ABORTED: {type(e).__name__}: {e}", file=sys.stderr)
            s = {"source_id": src["source_id"], "status": "aborted",
                 "error": f"{type(e).__name__}: {e}"}
        summaries.append(s)

    # Write run summary
    summary_path = out_root / f"crawl_summary_{now_iso.replace(':','-')}.json"
    with summary_path.open("w", encoding="utf-8") as f:
        json.dump({
            "started_at": now_iso,
            "elapsed_sec": round(time.time() - t0, 1),
            "tiers": args.tiers,
            "n_sources": len(filtered),
            "summaries": summaries,
        }, f, indent=2)

    total_html = sum(s.get("html_pages", 0) for s in summaries)
    total_pdf = sum(s.get("pdfs_found", 0) for s in summaries)
    total_err = sum(s.get("errors", 0) for s in summaries)
    print(f"\n=== run summary ===", file=sys.stderr)
    print(f"  sources crawled: {len(summaries)}", file=sys.stderr)
    print(f"  html pages:      {total_html}", file=sys.stderr)
    print(f"  pdfs found:      {total_pdf}", file=sys.stderr)
    print(f"  fetch errors:    {total_err}", file=sys.stderr)
    print(f"  elapsed:         {time.time()-t0:.0f}s", file=sys.stderr)
    print(f"  summary:         {summary_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
