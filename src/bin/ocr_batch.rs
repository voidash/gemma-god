//! Run OCR on all Tier C docs from the batch classification and report results.
//!
//! Reads `survey/classification_batch.json`, filters to tier=C, OCRs each
//! corresponding PDF in `survey/cdn_batch/`, writes full text to
//! `survey/ocr_output/<filename>.txt`, emits a JSON summary report.

use gemma_god::legacy_fonts::nepali_word_hits;
use gemma_god::ocr_pdf_default;
use serde::{Deserialize, Serialize};
use std::fs::{self, File};
use std::io::BufReader;
use std::path::PathBuf;

#[derive(Debug, Deserialize)]
struct Classification {
    file: String,
    tier: String,
    pages: u32,
    size_bytes: u64,
    producer: String,
}

#[derive(Debug, Serialize)]
struct OcrReport {
    file: String,
    pages: u32,
    size_bytes: u64,
    producer: String,
    ok: bool,
    error: Option<String>,
    text_len: usize,
    devanagari_chars: usize,
    nepali_word_hits: usize,
    preview: String,
}

fn count_deva(text: &str) -> usize {
    text.chars()
        .filter(|c| ('\u{0900}'..='\u{097F}').contains(c))
        .count()
}

fn preview_200(text: &str) -> String {
    let collapsed = text.split_whitespace().collect::<Vec<_>>().join(" ");
    collapsed.chars().take(200).collect()
}

fn main() -> std::io::Result<()> {
    let json_path = PathBuf::from("survey/classification_batch.json");
    let batch_dir = PathBuf::from("survey/cdn_batch");
    let out_dir = PathBuf::from("survey/ocr_output");

    if !json_path.exists() {
        eprintln!("error: {} not found — run classifier first", json_path.display());
        std::process::exit(2);
    }
    fs::create_dir_all(&out_dir)?;

    let classifications: Vec<Classification> =
        serde_json::from_reader(BufReader::new(File::open(&json_path)?))
            .expect("classification_batch.json must parse");

    let targets: Vec<&Classification> =
        classifications.iter().filter(|c| c.tier == "C").collect();

    eprintln!(
        "OCR on {} Tier C targets (from {} total classifications)",
        targets.len(),
        classifications.len()
    );

    let mut reports: Vec<OcrReport> = Vec::new();
    for c in targets {
        let pdf_path = batch_dir.join(&c.file);
        if !pdf_path.is_file() {
            eprintln!("warning: PDF missing at {}", pdf_path.display());
            continue;
        }
        eprintln!(
            "  OCR'ing {} ({}p, {} bytes) — this may take a while...",
            c.file, c.pages, c.size_bytes
        );

        let result = ocr_pdf_default(&pdf_path);
        let report = match result {
            Ok(text) => {
                // Persist full text.
                let text_out = out_dir.join(format!("{}.txt", c.file));
                if let Err(e) = fs::write(&text_out, &text) {
                    eprintln!("    warning: write {} failed: {}", text_out.display(), e);
                }
                OcrReport {
                    file: c.file.clone(),
                    pages: c.pages,
                    size_bytes: c.size_bytes,
                    producer: c.producer.clone(),
                    ok: true,
                    error: None,
                    text_len: text.len(),
                    devanagari_chars: count_deva(&text),
                    nepali_word_hits: nepali_word_hits(&text),
                    preview: preview_200(&text),
                }
            }
            Err(e) => OcrReport {
                file: c.file.clone(),
                pages: c.pages,
                size_bytes: c.size_bytes,
                producer: c.producer.clone(),
                ok: false,
                error: Some(e.to_string()),
                text_len: 0,
                devanagari_chars: 0,
                nepali_word_hits: 0,
                preview: String::new(),
            },
        };
        reports.push(report);
    }

    println!("{}", serde_json::to_string_pretty(&reports).unwrap());

    // stderr summary
    let ok_count = reports.iter().filter(|r| r.ok).count();
    let fail_count = reports.len() - ok_count;
    let total_deva: usize = reports.iter().map(|r| r.devanagari_chars).sum();
    let total_words: usize = reports.iter().map(|r| r.nepali_word_hits).sum();

    eprintln!("\n=== OCR SUMMARY ===");
    eprintln!("files processed: {}", reports.len());
    eprintln!("ok: {}  failed: {}", ok_count, fail_count);
    eprintln!("total Devanagari chars across batch: {}", total_deva);
    eprintln!("total Nepali word hits across batch: {}", total_words);
    eprintln!();
    for r in &reports {
        let tag = if r.ok { "OK" } else { "ERR" };
        eprintln!(
            "  [{}] {:<60} deva={:<6} nepali_hits={}",
            tag, r.file, r.devanagari_chars, r.nepali_word_hits,
        );
        if let Some(e) = &r.error {
            eprintln!("       error: {}", e);
        }
    }
    Ok(())
}
