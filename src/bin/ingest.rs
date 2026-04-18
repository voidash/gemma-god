//! Ingest the classified batch + OCR output into chunked JSONL ready for
//! retrieval indexing. Per-tier text extraction:
//!   - A / E          : pdftotext direct
//!   - BPreeti        : pdftotext -> preeti_to_unicode
//!   - Mixed          : pdftotext -> convert_mixed (per-block)
//!   - C              : read pre-OCR'd survey/ocr_output/<file>.txt
//!   - BLegacyUnknown : skip (font unidentified; conversion would be garbage)
//!   - XInvalid/Unknown: skip
//!
//! Chunks: target ~600 chars, soft boundary at sentence-end (`.`, `।`, `!`,
//! `?`, newline), ~80 chars overlap between successive chunks to preserve
//! cross-boundary context for retrieval.

use gemma_god::{convert_mixed, preeti_to_unicode};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs::{self, File};
use std::io::{BufReader, BufWriter, Write};
use std::path::{Path, PathBuf};
use std::process::Command;

const TARGET_CHARS: usize = 600;
const OVERLAP_CHARS: usize = 80;
const MIN_CHUNK_CHARS: usize = 100;

#[derive(Debug, Deserialize)]
struct Classification {
    file: String,
    tier: String,
    pages: u32,
    size_bytes: u64,
}

#[derive(Debug, Serialize)]
struct ChunkRecord<'a> {
    doc_id: &'a str,
    chunk_id: usize,
    text: String,
    source_url: Option<&'a str>,
    tier: &'a str,
    total_pages: u32,
    char_start: usize,
    char_end: usize,
}

fn extract_text_via_pdftotext(pdf: &Path) -> Option<String> {
    let out = Command::new("pdftotext")
        .args(["-layout", &pdf.to_string_lossy(), "-"])
        .output()
        .ok()?;
    if out.status.success() {
        Some(String::from_utf8_lossy(&out.stdout).into_owned())
    } else {
        None
    }
}

fn extract_text(c: &Classification, batch_dir: &Path, ocr_dir: &Path) -> Option<String> {
    match c.tier.as_str() {
        "A" | "E" => extract_text_via_pdftotext(&batch_dir.join(&c.file)),
        "BPreeti" => extract_text_via_pdftotext(&batch_dir.join(&c.file))
            .map(|t| preeti_to_unicode(&t)),
        "Mixed" => extract_text_via_pdftotext(&batch_dir.join(&c.file))
            .map(|t| convert_mixed(&t, "Preeti")),
        "C" => fs::read_to_string(ocr_dir.join(format!("{}.txt", c.file))).ok(),
        _ => None,
    }
}

fn chunk_text(text: &str, target: usize, overlap: usize) -> Vec<(usize, usize, String)> {
    let chars: Vec<char> = text.chars().collect();
    let mut chunks: Vec<(usize, usize, String)> = Vec::new();
    if chars.is_empty() {
        return chunks;
    }
    let mut start = 0usize;
    while start < chars.len() {
        let hard_end = (start + target).min(chars.len());
        // Try to align hard_end to a sentence boundary in the last quarter of the window.
        let lookback_start = hard_end.saturating_sub(target / 4).max(start + MIN_CHUNK_CHARS);
        let mut end = hard_end;
        if hard_end < chars.len() {
            for i in (lookback_start..hard_end).rev() {
                if matches!(chars[i], '.' | '।' | '!' | '?' | '\n') {
                    end = i + 1;
                    break;
                }
            }
        }
        let slice: String = chars[start..end].iter().collect();
        let trimmed = slice.trim();
        if trimmed.len() >= MIN_CHUNK_CHARS {
            chunks.push((start, end, trimmed.to_string()));
        }
        if end >= chars.len() {
            break;
        }
        start = end.saturating_sub(overlap).max(start + 1);
    }
    chunks
}

/// Rebuild the filename -> source-url map that the downloader created.
/// Mirrors the Python `safe_filename` in survey/download_batch.py so the two
/// stay consistent. Porting logic here lets us attach original URLs to chunks.
fn safe_filename_from_url(url: &str) -> String {
    let (scheme, rest) = url.split_once("://").unwrap_or(("https", url));
    let _ = scheme;
    let host_end = rest.find('/').unwrap_or(rest.len());
    let host = &rest[..host_end];
    let path = &rest[host_end..];
    let query_stripped = path.split('?').next().unwrap_or(path);
    let fragment_stripped = query_stripped.split('#').next().unwrap_or(query_stripped);
    let basename_raw = fragment_stripped
        .rsplit('/')
        .find(|s| !s.is_empty())
        .unwrap_or("index");
    let decoded = percent_decode(basename_raw);
    let with_ext = if decoded.to_ascii_lowercase().ends_with(".pdf") {
        decoded.clone()
    } else {
        format!("{}.pdf", decoded)
    };
    let capped: String = with_ext.chars().take(100).collect();
    let sanitized: String = capped
        .chars()
        .map(|c| {
            if c.is_ascii_alphanumeric() || c == '.' || c == '_' || c == '-' {
                c
            } else {
                '_'
            }
        })
        .collect();
    let host_prefix: String = host.replace('.', "_").chars().take(40).collect();
    format!("{}__{}", host_prefix, sanitized)
}

fn percent_decode(s: &str) -> String {
    let bytes = s.as_bytes();
    let mut out: Vec<u8> = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            if let (Some(h), Some(l)) = (hex_digit(bytes[i + 1]), hex_digit(bytes[i + 2])) {
                out.push(h * 16 + l);
                i += 3;
                continue;
            }
        }
        out.push(bytes[i]);
        i += 1;
    }
    String::from_utf8_lossy(&out).into_owned()
}

fn hex_digit(b: u8) -> Option<u8> {
    match b {
        b'0'..=b'9' => Some(b - b'0'),
        b'a'..=b'f' => Some(b - b'a' + 10),
        b'A'..=b'F' => Some(b - b'A' + 10),
        _ => None,
    }
}

fn load_filename_url_map(urls_path: &Path) -> HashMap<String, String> {
    let mut map = HashMap::new();
    let Ok(content) = fs::read_to_string(urls_path) else {
        return map;
    };
    for line in content.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        if !trimmed.starts_with("http") {
            continue;
        }
        let fname = safe_filename_from_url(trimmed);
        map.insert(fname, trimmed.to_string());
    }
    map
}

fn main() -> std::io::Result<()> {
    let survey = PathBuf::from("survey");
    let class_path = survey.join("classification_batch.json");
    let urls_path = survey.join("urls.txt");
    let batch_dir = survey.join("cdn_batch");
    let ocr_dir = survey.join("ocr_output");
    let out_path = survey.join("corpus_chunks.jsonl");

    if !class_path.is_file() {
        eprintln!("error: {} not found", class_path.display());
        std::process::exit(2);
    }

    let classifications: Vec<Classification> =
        serde_json::from_reader(BufReader::new(File::open(&class_path)?))
            .expect("classification JSON must parse");

    let fname_to_url = load_filename_url_map(&urls_path);
    eprintln!(
        "loaded {} classifications; {} filename->URL mappings",
        classifications.len(),
        fname_to_url.len()
    );

    let writer = File::create(&out_path)?;
    let mut writer = BufWriter::new(writer);

    let mut docs_ingested = 0usize;
    let mut docs_skipped = 0usize;
    let mut total_chunks = 0usize;
    let mut total_chars = 0usize;
    let mut by_tier: HashMap<String, (usize, usize)> = HashMap::new(); // tier -> (docs, chunks)

    for c in &classifications {
        let source_url = fname_to_url.get(&c.file).map(|s| s.as_str());

        let text = match extract_text(c, &batch_dir, &ocr_dir) {
            Some(t) if !t.trim().is_empty() => t,
            _ => {
                docs_skipped += 1;
                continue;
            }
        };

        let chunks = chunk_text(&text, TARGET_CHARS, OVERLAP_CHARS);
        if chunks.is_empty() {
            docs_skipped += 1;
            continue;
        }
        docs_ingested += 1;
        for (idx, (start, end, chunk)) in chunks.iter().enumerate() {
            let rec = ChunkRecord {
                doc_id: &c.file,
                chunk_id: idx,
                text: chunk.clone(),
                source_url,
                tier: &c.tier,
                total_pages: c.pages,
                char_start: *start,
                char_end: *end,
            };
            let line = serde_json::to_string(&rec).expect("serialize chunk");
            writeln!(writer, "{}", line)?;
            total_chunks += 1;
            total_chars += chunk.chars().count();
        }
        let entry = by_tier.entry(c.tier.clone()).or_insert((0, 0));
        entry.0 += 1;
        entry.1 += chunks.len();
    }

    writer.flush()?;

    eprintln!();
    eprintln!("=== INGEST SUMMARY ===");
    eprintln!("docs ingested: {}", docs_ingested);
    eprintln!("docs skipped:  {}", docs_skipped);
    eprintln!("total chunks:  {}", total_chunks);
    eprintln!(
        "total chars:   {} ({:.1} KB of indexable text)",
        total_chars,
        total_chars as f64 / 1024.0
    );
    eprintln!();
    eprintln!("by tier (docs, chunks):");
    let mut tiers: Vec<(&String, &(usize, usize))> = by_tier.iter().collect();
    tiers.sort_by(|a, b| b.1 .1.cmp(&a.1 .1));
    for (tier, (d, c)) in tiers {
        eprintln!("  {:<16} docs={:<3} chunks={}", tier, d, c);
    }
    eprintln!();
    eprintln!("wrote {}", out_path.display());

    Ok(())
}
