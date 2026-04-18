//! Minimal crawler for discovering gov PDFs from HTML index pages.
//!
//! Shells out to `curl -kLsS` so we inherit curl's broken-TLS tolerance
//! (~27% of Nepal gov sites fail cert verification — crawler must not crash
//! on those). Extracts `.pdf` links via regex and resolves relative URLs.
//!
//! This is deliberately a v1. Not a full graph crawler — no deep link
//! following, no robots.txt parsing, no JS rendering. Meant to be called
//! on a seeded list of known index pages (notices, downloads, category pages)
//! and diff results against the existing `survey/urls.txt` to surface new PDFs.

use regex::Regex;
use std::process::Command;
use std::sync::OnceLock;

#[derive(Debug)]
pub enum CrawlError {
    /// `curl` not installed or not on PATH.
    CurlNotFound,
    /// curl exited but we couldn't parse its output.
    ParseFailure(String),
    /// I/O error invoking curl.
    Io(String),
}

impl std::fmt::Display for CrawlError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            CrawlError::CurlNotFound => write!(f, "curl not installed or not on PATH"),
            CrawlError::ParseFailure(s) => write!(f, "parse failure: {}", s),
            CrawlError::Io(s) => write!(f, "io: {}", s),
        }
    }
}

impl std::error::Error for CrawlError {}

/// Fetch a URL via curl (with `-k` for TLS tolerance). Returns (http_status, body).
/// `curl` handles redirects (`-L`), is silent (`-s`), but surfaces errors (`-S`).
pub fn fetch(url: &str) -> Result<(u32, String), CrawlError> {
    const STATUS_SENTINEL: &str = "\n__HTTP_STATUS__";
    let out = Command::new("curl")
        .args([
            "-kLsS",
            "-w",
            &format!("{}%{{http_code}}", STATUS_SENTINEL),
            "--max-time",
            "30",
            "--user-agent",
            "gemma-god-crawler/0.1 (Nepal gov corpus research; ashish.thapa477@gmail.com)",
            url,
        ])
        .output()
        .map_err(|e| match e.kind() {
            std::io::ErrorKind::NotFound => CrawlError::CurlNotFound,
            _ => CrawlError::Io(e.to_string()),
        })?;

    let full = String::from_utf8_lossy(&out.stdout);
    let (body, status) = full.rsplit_once(STATUS_SENTINEL).ok_or_else(|| {
        CrawlError::ParseFailure(format!(
            "no status sentinel in curl output (rc={})",
            out.status.code().unwrap_or(-1)
        ))
    })?;
    let status: u32 = status.trim().parse().map_err(|e| {
        CrawlError::ParseFailure(format!("unparseable status '{}': {}", status.trim(), e))
    })?;
    Ok((status, body.to_string()))
}

/// HEAD request (via `curl -I`) to check if a URL still exists. Returns status code.
pub fn head(url: &str) -> Result<u32, CrawlError> {
    const STATUS_SENTINEL: &str = "__HTTP_STATUS__";
    let out = Command::new("curl")
        .args([
            "-kLsS",
            "-I",
            "-o",
            "/dev/null",
            "-w",
            &format!("{}%{{http_code}}", STATUS_SENTINEL),
            "--max-time",
            "20",
            url,
        ])
        .output()
        .map_err(|e| match e.kind() {
            std::io::ErrorKind::NotFound => CrawlError::CurlNotFound,
            _ => CrawlError::Io(e.to_string()),
        })?;
    let full = String::from_utf8_lossy(&out.stdout);
    let status_str = full
        .split(STATUS_SENTINEL)
        .nth(1)
        .unwrap_or("")
        .trim();
    status_str
        .parse::<u32>()
        .map_err(|e| CrawlError::ParseFailure(format!("unparseable HEAD status '{}': {}", status_str, e)))
}

pub fn status_ok(status: u32) -> bool {
    (200..400).contains(&status)
}

static PDF_HREF_RE: OnceLock<Regex> = OnceLock::new();

fn pdf_href_re() -> &'static Regex {
    PDF_HREF_RE.get_or_init(|| {
        Regex::new(r#"(?i)href\s*=\s*["']([^"']+?\.pdf(?:[?#][^"']*)?)["']"#)
            .expect("static regex")
    })
}

/// Extract absolute `.pdf` URLs from an HTML page. Relative hrefs are resolved
/// against `base_url`. Returns deduplicated list in appearance order.
pub fn extract_pdf_links(base_url: &str, html: &str) -> Vec<String> {
    let re = pdf_href_re();
    let mut seen = std::collections::HashSet::new();
    let mut out = Vec::new();
    for caps in re.captures_iter(html) {
        if let Some(m) = caps.get(1) {
            let resolved = resolve_url(base_url, m.as_str());
            if seen.insert(resolved.clone()) {
                out.push(resolved);
            }
        }
    }
    out
}

/// Resolve a possibly-relative href against a base URL. Handles:
///   - Absolute http(s):// URLs (passthrough)
///   - Protocol-relative //host/path
///   - Absolute path /path/to
///   - Relative path (anchored at base's directory)
pub fn resolve_url(base: &str, href: &str) -> String {
    let href = href.trim();
    if href.starts_with("http://") || href.starts_with("https://") {
        return href.to_string();
    }
    let (scheme, rest) = base.split_once("://").unwrap_or(("https", base));
    if href.starts_with("//") {
        return format!("{}:{}", scheme, href);
    }
    let host_end = rest.find('/').unwrap_or(rest.len());
    let host = &rest[..host_end];
    let path = &rest[host_end..];
    if href.starts_with('/') {
        return format!("{}://{}{}", scheme, host, href);
    }
    let base_dir = match path.rfind('/') {
        Some(i) => &path[..=i],
        None => "/",
    };
    format!("{}://{}{}{}", scheme, host, base_dir, href)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn resolve_absolute_passthrough() {
        assert_eq!(
            resolve_url("https://a.com/", "https://b.com/x.pdf"),
            "https://b.com/x.pdf"
        );
    }

    #[test]
    fn resolve_absolute_path() {
        assert_eq!(
            resolve_url("https://a.com/foo/bar", "/x/y.pdf"),
            "https://a.com/x/y.pdf"
        );
    }

    #[test]
    fn resolve_relative_path() {
        assert_eq!(
            resolve_url("https://a.com/foo/bar", "y.pdf"),
            "https://a.com/foo/y.pdf"
        );
        assert_eq!(
            resolve_url("https://a.com/foo/", "y.pdf"),
            "https://a.com/foo/y.pdf"
        );
    }

    #[test]
    fn resolve_protocol_relative() {
        assert_eq!(
            resolve_url("https://a.com/", "//b.com/x.pdf"),
            "https://b.com/x.pdf"
        );
    }

    #[test]
    fn extract_finds_single_and_double_quoted_pdfs() {
        let html = r#"<a href="doc.pdf">1</a> <a href='/big/file.pdf?v=1'>2</a> <a href="HTTPS://ex.com/CAPS.PDF">3</a>"#;
        let links = extract_pdf_links("https://a.com/", html);
        assert_eq!(links.len(), 3, "expected 3, got {:?}", links);
        assert!(links.iter().any(|u| u.ends_with("doc.pdf")));
        assert!(links.iter().any(|u| u.contains("/big/file.pdf")));
    }

    #[test]
    fn extract_dedupes_identical_hrefs() {
        let html = r#"<a href="x.pdf">1</a><a href="x.pdf">2</a>"#;
        let links = extract_pdf_links("https://a.com/", html);
        assert_eq!(links.len(), 1);
    }

    #[test]
    fn extract_ignores_non_pdf_hrefs() {
        let html = r#"<a href="page.html">1</a> <a href="about">2</a>"#;
        assert_eq!(extract_pdf_links("https://a.com/", html).len(), 0);
    }
}
