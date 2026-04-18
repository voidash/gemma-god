use clap::Parser;
use gemma_god::classify_pdf;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

#[derive(Parser)]
#[command(about = "Classify Nepal government PDFs by extraction tier")]
struct Cli {
    /// PDF files or directories containing PDFs (directories are walked recursively)
    paths: Vec<PathBuf>,

    /// Emit a single JSON array instead of the human-readable report
    #[arg(short, long)]
    json: bool,
}

fn collect_pdfs(root: &Path, out: &mut Vec<PathBuf>) -> std::io::Result<()> {
    if root.is_file() {
        out.push(root.to_path_buf());
        return Ok(());
    }
    if !root.exists() {
        eprintln!("warning: path not found: {}", root.display());
        return Ok(());
    }
    if !root.is_dir() {
        eprintln!("warning: not a file or directory: {}", root.display());
        return Ok(());
    }
    for entry in std::fs::read_dir(root)? {
        let entry = entry?;
        let path = entry.path();
        if path.is_dir() {
            collect_pdfs(&path, out)?;
        } else if path.extension().and_then(|e| e.to_str()) == Some("pdf") {
            out.push(path);
        }
    }
    Ok(())
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    if cli.paths.is_empty() {
        eprintln!("error: provide at least one PDF file or directory");
        return ExitCode::from(2);
    }

    let mut pdfs: Vec<PathBuf> = Vec::new();
    for p in &cli.paths {
        if let Err(e) = collect_pdfs(p, &mut pdfs) {
            eprintln!("error walking {}: {}", p.display(), e);
            return ExitCode::FAILURE;
        }
    }

    if pdfs.is_empty() {
        eprintln!("no PDF files found under the given paths");
        return ExitCode::from(2);
    }

    pdfs.sort();
    let results: Vec<_> = pdfs.iter().map(|p| classify_pdf(p)).collect();

    if cli.json {
        match serde_json::to_string_pretty(&results) {
            Ok(s) => println!("{}", s),
            Err(e) => {
                eprintln!("error serializing JSON: {}", e);
                return ExitCode::FAILURE;
            }
        }
        return ExitCode::SUCCESS;
    }

    for r in &results {
        println!("-- {} ({} bytes)", r.file, r.size_bytes);
        println!("  tier: {:?}  confidence: {:?}", r.tier, r.confidence);
        println!(
            "  pages: {}  text_len: {}  deva: {}  latin: {}  deva_ratio: {:.3}  preeti_sig_ratio: {:.3}  preeti_word_hits: {}",
            r.pages,
            r.text_len,
            r.devanagari_chars,
            r.latin_alpha_chars,
            r.devanagari_ratio,
            r.preeti_sig_ratio,
            r.preeti_word_hits,
        );
        println!(
            "  creator: {}  producer: {}",
            if r.creator.is_empty() { "-" } else { &r.creator },
            if r.producer.is_empty() { "-" } else { &r.producer },
        );
        if let Some(h) = &r.producer_hint {
            println!("  producer_hint: {}", h);
        }
        if let Some(f) = &r.legacy_family_hint {
            println!("  legacy_family_hint: {}", f);
        }
        for w in &r.warnings {
            println!("  ! warning: {}", w);
        }
        if let Some(e) = &r.error {
            println!("  !! error: {}", e);
        }
        if !r.preview.is_empty() {
            println!("  preview: {}", r.preview);
        }
        println!();
    }

    ExitCode::SUCCESS
}
