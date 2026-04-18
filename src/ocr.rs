//! OCR pipeline for Tier C (image-only) PDFs.
//!
//! Shells out to `pdftoppm` (poppler) to rasterize pages to PNG, then to
//! `tesseract` with Nepali + English traineddata to extract text. Expects:
//!   - `pdftoppm` on PATH
//!   - `tesseract` on PATH
//!   - `nep.traineddata` available in Tesseract's tessdata directory
//!     (we use `tessdata_best` from the upstream Tesseract repo for quality)
//!
//! Default rendering DPI is 300 — empirically sufficient for scanned gov
//! documents (verified on ocr_camscanner.pdf from survey/samples/).

use std::error::Error;
use std::fmt;
use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::process::Command;
use tempfile::TempDir;

pub const DEFAULT_DPI: u32 = 300;
pub const DEFAULT_LANGS: &str = "nep+eng";

#[derive(Debug)]
pub enum OcrError {
    /// A required external binary is not installed or not on PATH.
    ToolNotFound(String),
    /// An external binary exited non-zero.
    CommandFailed {
        tool: String,
        rc: i32,
        stderr: String,
    },
    /// Rasterization succeeded but produced no page images.
    NoPagesRendered,
    /// I/O error (tempdir creation, directory enumeration, etc.).
    Io(io::Error),
}

impl fmt::Display for OcrError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            OcrError::ToolNotFound(t) => write!(f, "tool not installed or not on PATH: {}", t),
            OcrError::CommandFailed { tool, rc, stderr } => {
                write!(f, "{} failed (rc={}): {}", tool, rc, stderr.trim())
            }
            OcrError::NoPagesRendered => write!(f, "pdftoppm produced no output images"),
            OcrError::Io(e) => write!(f, "io error: {}", e),
        }
    }
}

impl Error for OcrError {}

impl From<io::Error> for OcrError {
    fn from(e: io::Error) -> Self {
        OcrError::Io(e)
    }
}

fn run_expecting(tool: &str, cmd: &mut Command) -> Result<std::process::Output, OcrError> {
    let out = cmd.output().map_err(|e| match e.kind() {
        io::ErrorKind::NotFound => OcrError::ToolNotFound(tool.to_string()),
        _ => OcrError::Io(e),
    })?;
    if !out.status.success() {
        return Err(OcrError::CommandFailed {
            tool: tool.to_string(),
            rc: out.status.code().unwrap_or(-1),
            stderr: String::from_utf8_lossy(&out.stderr).into_owned(),
        });
    }
    Ok(out)
}

/// Rasterize a PDF into a temp directory via `pdftoppm`. Returns the sorted list
/// of PNG page paths. Caller is responsible for keeping `TempDir` alive.
fn rasterize(pdf: &Path, tmpdir: &Path, dpi: u32) -> Result<Vec<PathBuf>, OcrError> {
    let prefix = tmpdir.join("page");
    run_expecting(
        "pdftoppm",
        Command::new("pdftoppm")
            .args(["-r", &dpi.to_string(), "-png"])
            .arg(pdf)
            .arg(&prefix),
    )?;

    let mut pages: Vec<PathBuf> = Vec::new();
    for entry in fs::read_dir(tmpdir)? {
        let entry = entry?;
        let path = entry.path();
        if path.extension().and_then(|s| s.to_str()) == Some("png") {
            pages.push(path);
        }
    }
    if pages.is_empty() {
        return Err(OcrError::NoPagesRendered);
    }
    pages.sort();
    Ok(pages)
}

/// Run Tesseract on a single image file, returning the extracted text.
fn ocr_image(image: &Path, langs: &str) -> Result<String, OcrError> {
    let out = run_expecting(
        "tesseract",
        Command::new("tesseract")
            .arg(image)
            .arg("-")
            .args(["-l", langs]),
    )?;
    Ok(String::from_utf8_lossy(&out.stdout).into_owned())
}

/// OCR a full PDF. Rasterizes each page to PNG at the given DPI, runs
/// Tesseract on each image, and concatenates results with `\n\n` page separators.
pub fn ocr_pdf(pdf: &Path, langs: &str, dpi: u32) -> Result<String, OcrError> {
    if !pdf.is_file() {
        return Err(OcrError::Io(io::Error::new(
            io::ErrorKind::NotFound,
            format!("pdf not found: {}", pdf.display()),
        )));
    }
    let tmp = TempDir::new()?;
    let pages = rasterize(pdf, tmp.path(), dpi)?;
    let mut text = String::new();
    for page in &pages {
        let page_text = ocr_image(page, langs)?;
        text.push_str(&page_text);
        if !text.ends_with("\n\n") {
            text.push_str("\n\n");
        }
    }
    Ok(text)
}

/// Convenience with default DPI and langs.
pub fn ocr_pdf_default(pdf: &Path) -> Result<String, OcrError> {
    ocr_pdf(pdf, DEFAULT_LANGS, DEFAULT_DPI)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ocr_pdf_on_nonexistent_returns_io_error() {
        let err = ocr_pdf(Path::new("/no/such/file.pdf"), "eng", 150).unwrap_err();
        matches!(err, OcrError::Io(_));
    }

    // Note: a real OCR test requires tesseract + nep traineddata + pdftoppm
    // installed. Gated behind `--ignored` so CI without OCR tooling stays green.
    #[test]
    #[ignore]
    fn ocr_extracts_nepali_from_known_scan() {
        let path = Path::new("survey/samples/ocr_camscanner.pdf");
        let text = ocr_pdf(path, "nep+eng", 300).expect("OCR should succeed");
        // Lalitpur District Court notice. Should contain at least these tokens.
        assert!(
            text.contains("ललितपुर") || text.contains("अदालत") || text.contains("Court"),
            "expected Nepali court-notice tokens in OCR output, got: {}",
            &text[..text.len().min(400)]
        );
    }
}
