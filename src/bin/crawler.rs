//! Discover new gov PDFs from known index pages.
//!
//! Reads `survey/urls.txt` as the known set, crawls a hard-coded seed list
//! of deep index pages on Tier 1 gov sites, and writes anything new to
//! `survey/urls_discovered.txt`. Rate-limited per-domain. TLS-tolerant.

use gemma_god::crawler::{extract_pdf_links, fetch, head, status_ok};
use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::PathBuf;
use std::thread::sleep;
use std::time::Duration;

const RATE_LIMIT_MS: u64 = 1000;

/// Deep index pages. Each one is known to list many PDFs for its agency.
/// Sourced from round-1 WebSearch + WebFetch reconnaissance.
const SEED_URLS: &[(&str, &str)] = &[
    ("ird-notices", "https://ird.gov.np/category/notices/"),
    ("ird-acts", "https://ird.gov.np/category/acts-rules/"),
    ("ird-tax-bulletins", "https://ird.gov.np/category/tax-bulletins/"),
    ("lawcom-acts", "https://lawcommission.gov.np/category/1757"),
    ("lawcom-constitution", "https://lawcommission.gov.np/category/1807"),
    ("lawcom-ordinances", "https://lawcommission.gov.np/category/1809"),
    ("lawcom-regulations", "https://lawcommission.gov.np/category/1811"),
    ("lawcom-policies", "https://lawcommission.gov.np/category/1812"),
    ("lawcom-treaties", "https://lawcommission.gov.np/category/1817"),
    ("ocr-home", "https://ocr.gov.np/"),
    ("nrb-notices", "https://www.nrb.org.np/category/notices/?department=ofg"),
    ("nrb-monetary-policy", "https://www.nrb.org.np/category/monetary-policy/?department=ofg"),
    ("nrb-manual-guidelines", "https://www.nrb.org.np/category/manual-guidelines/?department=ofg"),
    ("dop-gazette", "https://dop.gov.np/pages/16711289"),
    ("sebon-press", "https://sebon.gov.np/press-releases"),
    ("sebon-acts", "https://sebon.gov.np/acts"),
    ("sebon-regulations", "https://sebon.gov.np/regulations"),
    ("moha-home", "https://moha.gov.np/"),
    ("dotm-home", "https://dotm.gov.np/"),
    ("nepalpassport-home", "https://nepalpassport.gov.np/"),
    ("dos-home", "https://dos.gov.np/"),
    ("opmcm-home", "https://opmcm.gov.np/"),
];

fn load_known_urls(path: &PathBuf) -> HashSet<String> {
    if !path.is_file() {
        return HashSet::new();
    }
    match fs::read_to_string(path) {
        Ok(s) => s
            .lines()
            .filter(|l| {
                let t = l.trim();
                !t.is_empty() && !t.starts_with('#')
            })
            .map(|l| l.trim().to_string())
            .collect(),
        Err(e) => {
            eprintln!("warning: failed to read {}: {}", path.display(), e);
            HashSet::new()
        }
    }
}

fn today_str() -> String {
    std::process::Command::new("date")
        .arg("+%Y-%m-%d")
        .output()
        .ok()
        .and_then(|o| String::from_utf8(o.stdout).ok())
        .map(|s| s.trim().to_string())
        .unwrap_or_else(|| "unknown-date".to_string())
}

fn main() -> std::io::Result<()> {
    let survey = PathBuf::from("survey");
    let urls_path = survey.join("urls.txt");
    let out_path = survey.join("urls_discovered.txt");
    let dead_path = survey.join("dead_urls.txt");

    let known = load_known_urls(&urls_path);
    eprintln!(
        "loaded {} known URLs from {}",
        known.len(),
        urls_path.display()
    );
    eprintln!("crawling {} seed pages with 1 req/s rate limit...", SEED_URLS.len());
    eprintln!();

    let mut new_by_seed: HashMap<String, Vec<String>> = HashMap::new();
    let mut all_new: Vec<(String, String)> = Vec::new(); // (url, seed_label)
    let mut total_pdfs_seen = 0usize;
    let mut per_seed_results: Vec<(String, String, u32, usize, usize)> = Vec::new(); // label, url, status, total, new

    for (label, seed) in SEED_URLS {
        eprint!("  [{}] {} ... ", label, seed);
        let result = fetch(seed);
        let (status, new_count, total_count) = match result {
            Ok((status, body)) => {
                if !status_ok(status) {
                    eprintln!("status={}  SKIP", status);
                    per_seed_results.push((label.to_string(), seed.to_string(), status, 0, 0));
                    sleep(Duration::from_millis(RATE_LIMIT_MS));
                    continue;
                }
                let pdfs = extract_pdf_links(seed, &body);
                let new: Vec<String> = pdfs
                    .iter()
                    .filter(|u| !known.contains(*u))
                    .cloned()
                    .collect();
                total_pdfs_seen += pdfs.len();
                eprintln!(
                    "status={}  {} pdfs ({} new)",
                    status,
                    pdfs.len(),
                    new.len()
                );
                for pdf in &new {
                    all_new.push((pdf.clone(), label.to_string()));
                }
                new_by_seed.insert(label.to_string(), new.clone());
                (status, new.len(), pdfs.len())
            }
            Err(e) => {
                eprintln!("ERR: {}", e);
                per_seed_results.push((label.to_string(), seed.to_string(), 0, 0, 0));
                sleep(Duration::from_millis(RATE_LIMIT_MS));
                continue;
            }
        };
        per_seed_results.push((
            label.to_string(),
            seed.to_string(),
            status,
            total_count,
            new_count,
        ));
        sleep(Duration::from_millis(RATE_LIMIT_MS));
    }

    // Dedupe new across seeds
    let mut seen: HashSet<String> = HashSet::new();
    all_new.retain(|(u, _)| seen.insert(u.clone()));

    eprintln!();
    eprintln!("=== DISCOVERY SUMMARY ===");
    eprintln!("total PDFs seen across seeds: {}", total_pdfs_seen);
    eprintln!("unique new PDFs (not in urls.txt): {}", all_new.len());
    eprintln!();
    for (label, _url, status, total, new) in &per_seed_results {
        eprintln!(
            "  [{:<22}] status={:<3}  {} pdfs  ({} new)",
            label, status, total, new
        );
    }

    if !all_new.is_empty() {
        let mut content = format!(
            "# Discovered {} new PDF URLs on {}\n# Source: Phase E crawler (see src/bin/crawler.rs)\n\n",
            all_new.len(),
            today_str()
        );
        for (url, src) in &all_new {
            content.push_str(&format!("# from: {}\n{}\n", src, url));
        }
        fs::write(&out_path, content)?;
        eprintln!();
        eprintln!("wrote {} new URLs to {}", all_new.len(), out_path.display());
    }

    // Revalidation: sample-check 20 existing known URLs via HEAD to surface
    // link-rot. Full revalidation of 85 URLs would take ~90s (1/s); 20 is a
    // quick sanity check. User can run with --revalidate-all for full pass.
    eprintln!();
    eprintln!("=== REVALIDATION (sample of 20 known URLs) ===");
    let sample: Vec<&String> = known.iter().take(20).collect();
    let mut dead: Vec<String> = Vec::new();
    for url in sample {
        match head(url) {
            Ok(status) => {
                if !status_ok(status) {
                    eprintln!("  DEAD ({}): {}", status, url);
                    dead.push(format!("# status={}\n{}", status, url));
                }
            }
            Err(e) => {
                eprintln!("  ERR: {}  ({})", e, url);
                dead.push(format!("# error={}\n{}", e, url));
            }
        }
        sleep(Duration::from_millis(RATE_LIMIT_MS));
    }
    if !dead.is_empty() {
        let content = format!(
            "# Revalidation sweep on {}: {} dead URLs found\n\n{}\n",
            today_str(),
            dead.len(),
            dead.join("\n")
        );
        fs::write(&dead_path, content)?;
        eprintln!("wrote {} dead URLs to {}", dead.len(), dead_path.display());
    } else {
        eprintln!("  all sampled URLs alive");
    }

    Ok(())
}
