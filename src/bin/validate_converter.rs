//! Scale-validate the Preeti / legacy-font converter against the batch.
//!
//! Loads survey/classification_batch.json, re-extracts text from each
//! BPreeti / Mixed / BLegacyUnknown PDF, runs the appropriate converter,
//! and reports before/after Devanagari ratio to quantify conversion yield.

use gemma_god::legacy_fonts::nepali_word_hits;
use gemma_god::{best_effort_convert, convert_mixed, preeti_to_unicode};
use serde::{Deserialize, Serialize};
use std::fs::File;
use std::io::BufReader;
use std::path::{Path, PathBuf};
use std::process::Command;

#[derive(Debug, Deserialize)]
struct Classification {
    file: String,
    tier: String,
    pages: u32,
}

#[derive(Debug, Serialize)]
struct ConvertReport {
    file: String,
    tier: String,
    pages: u32,
    before_deva: usize,
    before_latin: usize,
    before_ratio: f64,
    after_deva: usize,
    after_latin: usize,
    after_ratio: f64,
    best_font: String,
    ratio_improvement: f64,
    /// Count of known high-frequency Nepali words in the conversion output.
    /// This is the trustworthy quality signal — >=3 hits means real Nepali,
    /// 0 hits on BLegacyUnknown means the font guess was wrong.
    nepali_word_hits_after: usize,
    preview_before: String,
    preview_after: String,
}

fn extract_text(path: &Path) -> String {
    let out = Command::new("pdftotext")
        .args(["-layout", &path.to_string_lossy(), "-"])
        .output();
    match out {
        Ok(o) => String::from_utf8_lossy(&o.stdout).into_owned(),
        Err(_) => String::new(),
    }
}

fn count_deva(text: &str) -> usize {
    text.chars()
        .filter(|c| ('\u{0900}'..='\u{097F}').contains(c))
        .count()
}

fn count_latin_alpha(text: &str) -> usize {
    text.chars().filter(|c| c.is_ascii_alphabetic()).count()
}

fn ratio(deva: usize, latin: usize) -> f64 {
    let total = deva + latin;
    if total == 0 {
        0.0
    } else {
        deva as f64 / total as f64
    }
}

fn preview_200(text: &str) -> String {
    let collapsed = text.split_whitespace().collect::<Vec<_>>().join(" ");
    collapsed.chars().take(200).collect()
}

fn main() -> std::io::Result<()> {
    let json_path = PathBuf::from("survey/classification_batch.json");
    let batch_dir = PathBuf::from("survey/cdn_batch");

    if !json_path.exists() {
        eprintln!("error: {} not found — run classifier first", json_path.display());
        std::process::exit(2);
    }
    if !batch_dir.is_dir() {
        eprintln!("error: {} not found", batch_dir.display());
        std::process::exit(2);
    }

    let classifications: Vec<Classification> =
        serde_json::from_reader(BufReader::new(File::open(&json_path)?))
            .expect("classification_batch.json must parse");

    let targets: Vec<&Classification> = classifications
        .iter()
        .filter(|c| matches!(c.tier.as_str(), "BPreeti" | "Mixed" | "BLegacyUnknown"))
        .collect();

    eprintln!(
        "validating converter on {} targets (BPreeti | Mixed | BLegacyUnknown) from {} total",
        targets.len(),
        classifications.len()
    );

    let mut reports: Vec<ConvertReport> = Vec::new();
    for c in targets {
        let pdf_path = batch_dir.join(&c.file);
        if !pdf_path.is_file() {
            eprintln!("warning: PDF missing at {}", pdf_path.display());
            continue;
        }
        let text_before = extract_text(&pdf_path);
        let before_deva = count_deva(&text_before);
        let before_latin = count_latin_alpha(&text_before);
        let before_ratio = ratio(before_deva, before_latin);

        let (best_font, text_after): (String, String) = match c.tier.as_str() {
            "BPreeti" => ("Preeti".to_string(), preeti_to_unicode(&text_before)),
            "Mixed" => {
                // Per-block Preeti conversion: keeps English + already-Unicode
                // Devanagari untouched, converts only Preeti-like tokens. Phase C.
                (
                    "Preeti (per-block mixed)".to_string(),
                    convert_mixed(&text_before, "Preeti"),
                )
            }
            "BLegacyUnknown" => {
                let r = best_effort_convert(&text_before);
                let label = if r.nepali_word_hits >= 3 {
                    format!("best-effort:{}", r.font)
                } else {
                    format!(
                        "best-effort:{} (LOW QUALITY: only {} Nepali words found — font guess unreliable)",
                        r.font, r.nepali_word_hits
                    )
                };
                (label, r.text)
            }
            _ => (String::from("-"), text_before.clone()),
        };

        let after_deva = count_deva(&text_after);
        let after_latin = count_latin_alpha(&text_after);
        let after_ratio = ratio(after_deva, after_latin);
        let after_word_hits = nepali_word_hits(&text_after);

        reports.push(ConvertReport {
            file: c.file.clone(),
            tier: c.tier.clone(),
            pages: c.pages,
            before_deva,
            before_latin,
            before_ratio,
            after_deva,
            after_latin,
            after_ratio,
            best_font,
            ratio_improvement: after_ratio - before_ratio,
            nepali_word_hits_after: after_word_hits,
            preview_before: preview_200(&text_before),
            preview_after: preview_200(&text_after),
        });
    }

    // Sort: tier ascending, then biggest improvement first within tier.
    reports.sort_by(|a, b| {
        a.tier.cmp(&b.tier).then_with(|| {
            b.ratio_improvement
                .partial_cmp(&a.ratio_improvement)
                .unwrap_or(std::cmp::Ordering::Equal)
        })
    });

    println!("{}", serde_json::to_string_pretty(&reports).unwrap());

    // ---- stderr summary ----
    let by_tier = {
        use std::collections::HashMap;
        let mut m: HashMap<String, Vec<&ConvertReport>> = HashMap::new();
        for r in &reports {
            m.entry(r.tier.clone()).or_default().push(r);
        }
        m
    };

    eprintln!("\n=== VALIDATION SUMMARY ===");
    eprintln!("KEY: real_conversions = docs where converted output contains >= 3 known Nepali words");
    eprintln!("     (raw Devanagari ratio is misleading — any char-map produces Devanagari even on garbage)");
    eprintln!();
    for (tier, rs) in &by_tier {
        let n = rs.len() as f64;
        let mean_before: f64 = rs.iter().map(|r| r.before_ratio).sum::<f64>() / n;
        let mean_after: f64 = rs.iter().map(|r| r.after_ratio).sum::<f64>() / n;
        let real_conversions = rs.iter().filter(|r| r.nepali_word_hits_after >= 3).count();
        let zero_quality = rs.iter().filter(|r| r.nepali_word_hits_after == 0).count();
        eprintln!(
            "  {:<16} n={:<3} mean_deva_ratio before={:.3} -> after={:.3}  real_conversions={}/{}  zero_quality={}",
            tier, rs.len(), mean_before, mean_after, real_conversions, rs.len(), zero_quality
        );
    }
    eprintln!();
    eprintln!("Files where conversion produced ZERO Nepali words (font guess is wrong):");
    for r in &reports {
        if r.nepali_word_hits_after == 0 {
            eprintln!(
                "  [{}] {:<60}  font_guess={}",
                r.tier, r.file, r.best_font
            );
        }
    }
    eprintln!();
    eprintln!("Top 5 best real conversions (highest Nepali word hit count):");
    let mut by_hits: Vec<&ConvertReport> = reports.iter().collect();
    by_hits.sort_by(|a, b| b.nepali_word_hits_after.cmp(&a.nepali_word_hits_after));
    for r in by_hits.iter().take(5) {
        eprintln!(
            "  [{}] {:<55} nepali_hits={}  deva_ratio={:.3}",
            r.tier, r.file, r.nepali_word_hits_after, r.after_ratio
        );
    }

    Ok(())
}
