pub mod crawler;
pub mod detector;
pub mod legacy_fonts;
pub mod ocr;

pub use crawler::{extract_pdf_links, fetch, head, resolve_url, status_ok, CrawlError};
pub use detector::{classify_pdf, Confidence, PdfClassification, Tier};
pub use legacy_fonts::{
    best_effort_convert, convert, convert_mixed, preeti_to_unicode, supported_fonts,
};
pub use ocr::{ocr_pdf, ocr_pdf_default, OcrError};
