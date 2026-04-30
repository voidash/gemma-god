//! Probe PDF extraction quality across PDFs for one source. For each PDF
//! in the documents table for `--source <id>`, runs the full crawler_v2
//! `extract_text` pipeline (pdf_extract → pdftotext fallback → legacy-font
//! conversion) and reports per-doc text length + Devanagari char count.
//!
//! Buckets the result into:
//!   - rich  : >= 200 extracted chars (usable for retrieval)
//!   - thin  : 1..200 chars (mostly chrome / tiny content)
//!   - empty : 0 chars (truly image-only — needs OCR phase)
//!
//! With `pdftotext` available, this should recover the panic class that
//! `pdf_extract` alone fails on.
//!
//! Usage:
//!     cargo run --release --example probe_pdf_text -- \
//!         --db /Volumes/T9/gemma-god/corpus_v2/index.db \
//!         --corpus-root /Volumes/T9/gemma-god/corpus_v2 \
//!         --source jirimun_gov_np

use std::path::PathBuf;
use std::time::Instant;

use gemma_god::crawler_v2::{extract_text, ExtractStatus};
use gemma_god::crawler_v2::types::{DocType, Document};
use chrono::{DateTime, Utc};
use rusqlite::{params, Connection};

fn devanagari_chars(s: &str) -> usize {
    s.chars()
        .filter(|c| ('\u{0900}'..='\u{097F}').contains(c))
        .count()
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut db = PathBuf::from("/Volumes/T9/gemma-god/corpus_v2/index.db");
    let mut corpus_root = PathBuf::from("/Volumes/T9/gemma-god/corpus_v2");
    let mut source_id = String::new();

    let mut args = std::env::args().skip(1);
    while let Some(a) = args.next() {
        match a.as_str() {
            "--db" => db = args.next().expect("--db needs value").into(),
            "--corpus-root" => corpus_root = args.next().expect("--corpus-root needs value").into(),
            "--source" => source_id = args.next().expect("--source needs value"),
            _ => panic!("unknown arg: {a}"),
        }
    }
    if source_id.is_empty() {
        eprintln!("usage: --source <source_id>");
        std::process::exit(2);
    }

    let conn = Connection::open(&db)?;
    let mut stmt = conn.prepare(
        "SELECT doc_id, source_id, url, content_hash, fetched_at, doc_type,
                status_code, raw_blob_path, size_bytes, depth
         FROM documents
         WHERE source_id = ?1 AND doc_type = 'pdf'
           AND superseded_by IS NULL AND removed_at IS NULL
         ORDER BY size_bytes DESC",
    )?;
    let rows: Vec<Document> = stmt
        .query_map(params![&source_id], |r| {
            let fetched_at_str: String = r.get(4)?;
            let dt = DateTime::parse_from_rfc3339(&fetched_at_str)
                .map(|d| d.with_timezone(&Utc))
                .unwrap_or_else(|_| Utc::now());
            Ok(Document {
                doc_id: r.get(0)?,
                source_id: r.get(1)?,
                url: r.get(2)?,
                content_hash: r.get(3)?,
                fetched_at: dt,
                superseded_by: None,
                removed_at: None,
                doc_type: DocType::from_str(&r.get::<_, String>(5)?).unwrap_or(DocType::Pdf),
                status_code: r.get::<_, i64>(6)? as i32,
                title: None,
                language: None,
                date_published: None,
                raw_blob_path: r.get(7)?,
                extracted_text_path: None,
                text_chars: 0,
                size_bytes: r.get::<_, i64>(8)? as u64,
                depth: r.get::<_, i64>(9)? as u32,
                priority_at_fetch: None,
            })
        })?
        .collect::<Result<Vec<_>, _>>()?;
    eprintln!("[probe] {} PDFs for source={}", rows.len(), source_id);

    let mut rich = 0usize;
    let mut thin = 0usize;
    let mut empty = 0usize;
    let mut errored = 0usize;
    let mut total_extracted_chars = 0usize;
    let mut total_devanagari = 0usize;
    let started = Instant::now();

    for doc in &rows {
        let pretty = pretty_name(&doc.url);
        let extracted = match extract_text(doc, &corpus_root) {
            Ok(e) => e,
            Err(e) => {
                errored += 1;
                println!(
                    "  err          {:>4} kB  {pretty}  ({e})",
                    doc.size_bytes / 1024
                );
                continue;
            }
        };
        let chars = extracted.text.chars().count();
        let dev = devanagari_chars(&extracted.text);
        total_extracted_chars += chars;
        total_devanagari += dev;
        let bucket = match (chars, &extracted.status) {
            (0, _) => {
                empty += 1;
                "empty"
            }
            (n, _) if n >= 200 => {
                rich += 1;
                "rich "
            }
            _ => {
                thin += 1;
                "thin "
            }
        };
        let status = match extracted.status {
            ExtractStatus::Ok => "ok ",
            ExtractStatus::PdfNoText => "ntx",
            ExtractStatus::EmptyExtraction => "emp",
            ExtractStatus::SkippedUnsupported => "uns",
        };
        println!(
            "  {bucket}  {:>4} kB  {status}  chars={:>6}  deva={:>6}  {pretty}",
            doc.size_bytes / 1024,
            chars,
            dev
        );
    }

    eprintln!();
    eprintln!("=== probe summary ===");
    eprintln!("  total PDFs:               {}", rows.len());
    eprintln!("  rich  (>=200 chars):      {rich}");
    eprintln!("  thin  (1..199 chars):     {thin}");
    eprintln!("  empty (0 chars):          {empty}");
    eprintln!("  hard errors:              {errored}");
    eprintln!("  total extracted chars:    {total_extracted_chars}");
    eprintln!("  total devanagari chars:   {total_devanagari}");
    eprintln!("  elapsed: {:.1}s", started.elapsed().as_secs_f64());
    Ok(())
}

fn pretty_name(url: &str) -> String {
    let stem = url.rsplit('/').next().unwrap_or(url);
    percent_decode(stem).chars().take(80).collect()
}

fn percent_decode(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    let bytes = s.as_bytes();
    let mut i = 0;
    let mut buf = Vec::<u8>::new();
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            if let Ok(b) = u8::from_str_radix(
                std::str::from_utf8(&bytes[i + 1..i + 3]).unwrap_or("00"),
                16,
            ) {
                buf.push(b);
                i += 3;
                continue;
            }
        }
        // flush any pending UTF-8 bytes before non-percent char
        if !buf.is_empty() {
            out.push_str(std::str::from_utf8(&buf).unwrap_or(""));
            buf.clear();
        }
        out.push(bytes[i] as char);
        i += 1;
    }
    if !buf.is_empty() {
        out.push_str(std::str::from_utf8(&buf).unwrap_or(""));
    }
    out
}
