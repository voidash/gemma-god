use serde::Serialize;
use std::fs::{metadata, File};
use std::io::Read;
use std::path::Path;
use std::process::Command;

const DEVA_LO: char = '\u{0900}';
const DEVA_HI: char = '\u{097F}';

// Classic Preeti-encoded Nepali word signatures (Latin bytes that render as Devanagari
// under the Preeti font). Presence of >= 2 is strong evidence of Preeti.
const PREETI_WORD_MARKERS: &[&str] = &[
    "g]kfn", ";/sf/", "sf7df8f", "gful/s", "sDkgL", "xf]", "df}nL", "dlxgf", "cfly{s",
    "ljefu", "kof{j/0f", "lg0f{o", "sfof{no", "jif{", "gLlt", "a}+s",
];

// Symbols Preeti uses heavily because they map to Devanagari halants/diacritics.
// Restricted to the strong discriminators: these are rare in normal English prose
// and in non-Preeti legacy-font scanner output (which tends to use `.` `,` `:` `/`
// and capital-letter clusters instead). Tightened after empirical test on
// Canon SC1011 samples.
const PREETI_SIGNATURE_CHARS: &[char] = &['{', '}', '[', ']', '|'];

// Producer/Creator substring hints (matched case-insensitively). These pre-triage
// before any extraction. Hint values are advisory, not authoritative.
const PRODUCER_HINTS: &[(&str, &str)] = &[
    ("camscanner", "C"),
    ("ios version", "C"),
    ("quartz", "C"),
    ("naps2", "C-or-B"),
    ("canon sc", "B-legacy"),
    ("adobe psl", "B-legacy"),
    ("microsoft word", "A-likely"),
    ("microsoft: print to pdf", "A-likely"),
    ("ilovepdf", "reprocessed"),
    ("pdfium", "neutral"),
    ("adobe pdf library", "neutral"),
    ("adobe indesign", "neutral"),
];

// Two classes of signal:
// (a) Space-bounded function words — definitive prose markers.
// (b) Common gov-document / form-field substrings — catch non-prose English content
//     like "WRITTEN TEST REPORT", "Driving License Delivery Report". These are rare
//     as coincidental substrings in Canon/legacy-font garbled output (empirically
//     verified on the 93-doc batch).
const ENGLISH_MARKER_WORDS: &[&str] = &[
    " the ", " of ", " and ", " in ", " to ", " is ", " for ", " on ", " with ", " by ",
    " that ", " this ", " are ", " be ", " an ",
    "report", "date", "name", "type", "number", "license", "address",
    "nepal", "government", "department", "office", "ministry",
];

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub enum Tier {
    A,
    BPreeti,
    BLegacyUnknown,
    C,
    E,
    Mixed,
    XInvalid,
    Unknown,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub enum Confidence {
    High,
    Medium,
    Low,
}

#[derive(Debug, Clone, Serialize)]
pub struct PdfClassification {
    pub file: String,
    pub size_bytes: u64,
    pub pages: u32,
    pub is_valid_pdf: bool,
    pub is_encrypted: bool,
    pub creator: String,
    pub producer: String,
    pub producer_hint: Option<String>,
    pub text_len: usize,
    pub devanagari_chars: usize,
    pub latin_alpha_chars: usize,
    pub digit_chars: usize,
    pub devanagari_ratio: f64,
    pub preeti_sig_ratio: f64,
    pub preeti_word_hits: usize,
    pub tier: Tier,
    pub confidence: Confidence,
    pub legacy_family_hint: Option<String>,
    pub warnings: Vec<String>,
    pub error: Option<String>,
    pub preview: String,
}

#[derive(Default)]
struct PdfInfo {
    pages: u32,
    creator: String,
    producer: String,
    encrypted: bool,
    parse_warnings: Vec<String>,
}

#[derive(Default)]
struct CharCounts {
    deva: usize,
    latin: usize,
    digits: usize,
    preeti_sig: usize,
    non_space: usize,
}

struct Decision {
    tier: Tier,
    confidence: Confidence,
    legacy_family_hint: Option<String>,
    warnings: Vec<String>,
}

fn run_cmd(cmd: &str, args: &[&str]) -> (String, String, i32) {
    match Command::new(cmd).args(args).output() {
        Ok(out) => {
            let stdout = String::from_utf8_lossy(&out.stdout).into_owned();
            let stderr = String::from_utf8_lossy(&out.stderr).into_owned();
            let code = out.status.code().unwrap_or(-1);
            (stdout, stderr, code)
        }
        Err(e) => (String::new(), format!("{}: {}", cmd, e), 127),
    }
}

fn magic_bytes_ok(path: &Path) -> bool {
    let mut file = match File::open(path) {
        Ok(f) => f,
        Err(_) => return false,
    };
    let mut buf = [0u8; 5];
    if file.read_exact(&mut buf).is_err() {
        return false;
    }
    &buf == b"%PDF-"
}

fn parse_pdfinfo(stdout: &str) -> PdfInfo {
    let mut info = PdfInfo::default();
    for line in stdout.lines() {
        let Some((key, val)) = line.split_once(':') else {
            continue;
        };
        let key = key.trim();
        let val = val.trim();
        match key {
            "Pages" => match val.parse::<u32>() {
                Ok(n) => info.pages = n,
                Err(e) => info
                    .parse_warnings
                    .push(format!("pdfinfo Pages value '{}' unparseable: {}", val, e)),
            },
            "Creator" => info.creator = val.to_string(),
            "Producer" => info.producer = val.to_string(),
            "Encrypted" => info.encrypted = !val.to_lowercase().starts_with("no"),
            _ => {}
        }
    }
    info
}

fn producer_hint(creator: &str, producer: &str) -> Option<String> {
    let combined = format!("{} {}", creator, producer).to_lowercase();
    for (needle, hint) in PRODUCER_HINTS {
        if combined.contains(needle) {
            return Some((*hint).to_string());
        }
    }
    None
}

fn count_chars(text: &str) -> CharCounts {
    let mut c = CharCounts::default();
    for ch in text.chars() {
        if ch.is_whitespace() {
            continue;
        }
        c.non_space += 1;
        if (DEVA_LO..=DEVA_HI).contains(&ch) {
            c.deva += 1;
        } else if ch.is_ascii_alphabetic() {
            c.latin += 1;
        } else if ch.is_ascii_digit() {
            c.digits += 1;
        }
        if PREETI_SIGNATURE_CHARS.contains(&ch) {
            c.preeti_sig += 1;
        }
    }
    c
}

fn count_preeti_word_markers(text: &str) -> usize {
    PREETI_WORD_MARKERS
        .iter()
        .filter(|m| text.contains(*m))
        .count()
}

fn looks_like_english(text: &str) -> bool {
    let lower = text.to_lowercase();
    ENGLISH_MARKER_WORDS
        .iter()
        .filter(|w| lower.contains(*w))
        .count()
        >= 3
}

fn decide_tier(
    pages: u32,
    text_len: usize,
    counts: &CharCounts,
    preeti_word_hits: usize,
    preeti_sig_ratio: f64,
    deva_ratio: f64,
    raw_text: &str,
    producer_hint: Option<&str>,
) -> Decision {
    let mut warnings: Vec<String> = Vec::new();

    // Tier C: pages exist but no extractable text -> scanned image.
    if pages > 0 && text_len < 100 {
        let conf = match producer_hint {
            Some("C") | Some("C-or-B") => Confidence::High,
            _ => Confidence::Medium,
        };
        return Decision {
            tier: Tier::C,
            confidence: conf,
            legacy_family_hint: None,
            warnings,
        };
    }

    let has_unicode_nepali = counts.deva >= 50;
    // "essentially no Unicode Devanagari" — a small amount (<20) can leak in from
    // copyright strings, URLs, or a single Nepali character in a footer and shouldn't
    // disqualify the doc from being classified as E or B. Empirically tuned.
    let essentially_no_unicode = counts.deva < 20;
    // Preeti confirmation — layered to reduce false positives discovered at scale:
    //   - >= 3 word-marker hits is near-certain (coincidental 3-marker match on
    //     English text is vanishingly rare).
    //   - 2 hits is ambiguous: require either high sig-char density OR a non-English
    //     reading to confirm. (Nepal Building Code English docs had exactly 2 hits
    //     from technical tables — sig_ratio was 0.001 and `looks_like_english` true.)
    //   - sig-ratio-only branch: requires non-English reading to kick in (protects
    //     against English engineering docs with heavy `{`/`[`/`|` markup).
    let preeti_confirmed = preeti_word_hits >= 3
        || (preeti_word_hits >= 2
            && (preeti_sig_ratio >= 0.02 || !looks_like_english(raw_text)))
        || (essentially_no_unicode
            && counts.latin > 100
            && preeti_sig_ratio >= 0.05
            && !looks_like_english(raw_text));

    // Mixed: doc contains both Unicode Devanagari AND legacy-font signals.
    if has_unicode_nepali && preeti_confirmed {
        warnings.push(
            "document contains both Unicode Devanagari and Preeti signatures — mixed encoding"
                .to_string(),
        );
        return Decision {
            tier: Tier::Mixed,
            confidence: Confidence::Medium,
            legacy_family_hint: Some("preeti".to_string()),
            warnings,
        };
    }

    // Tier A: meaningful Unicode Devanagari content (bilingual docs tolerated).
    if has_unicode_nepali {
        let conf = if counts.deva >= 200 && deva_ratio >= 0.15 {
            Confidence::High
        } else {
            Confidence::Medium
        };
        if deva_ratio < 0.10 {
            warnings.push(format!(
                "low Devanagari ratio ({:.3}) — doc may be English-dominant with Nepali section",
                deva_ratio
            ));
        }
        return Decision {
            tier: Tier::A,
            confidence: conf,
            legacy_family_hint: None,
            warnings,
        };
    }

    // Tier B classic Preeti: zero Unicode + Preeti markers / signature density.
    if preeti_confirmed {
        let conf = if preeti_word_hits >= 5 {
            Confidence::High
        } else {
            Confidence::Medium
        };
        return Decision {
            tier: Tier::BPreeti,
            confidence: conf,
            legacy_family_hint: Some("preeti".to_string()),
            warnings,
        };
    }

    // Essentially no Devanagari + meaningful extractable content, no Preeti signal.
    // Either English/English-form or a non-Preeti legacy font (e.g. Canon scanner OCR).
    // Latin-alpha OR total content threshold — some legacy-font output has many
    // symbols and few ASCII letters (e.g. the daoramechhap scan had 78 latin in 2500+
    // non-space chars), so a Latin-only gate misses it.
    if essentially_no_unicode && (counts.latin > 50 || text_len > 500) {
        if looks_like_english(raw_text) {
            return Decision {
                tier: Tier::E,
                confidence: Confidence::Medium,
                legacy_family_hint: None,
                warnings,
            };
        }
        warnings.push(
            "no Devanagari, no Preeti markers, doesn't read as English — likely non-Preeti legacy font or garbled OCR"
                .to_string(),
        );
        let conf = match producer_hint {
            Some("B-legacy") => Confidence::Medium,
            _ => Confidence::Low,
        };
        return Decision {
            tier: Tier::BLegacyUnknown,
            confidence: conf,
            legacy_family_hint: Some("unknown-legacy".to_string()),
            warnings,
        };
    }

    if text_len < 500 {
        warnings.push(format!(
            "very short extracted text ({} chars) — classification uncertain",
            text_len
        ));
    }

    Decision {
        tier: Tier::Unknown,
        confidence: Confidence::Low,
        legacy_family_hint: None,
        warnings,
    }
}

fn make_preview(text: &str) -> String {
    let collapsed = text.split_whitespace().collect::<Vec<_>>().join(" ");
    collapsed.chars().take(200).collect()
}

fn round_to(x: f64, digits: u32) -> f64 {
    let factor = 10f64.powi(digits as i32);
    (x * factor).round() / factor
}

fn invalid_pdf_result(
    file_name: String,
    size_bytes: u64,
    warnings: Vec<String>,
    error: Option<String>,
) -> PdfClassification {
    PdfClassification {
        file: file_name,
        size_bytes,
        pages: 0,
        is_valid_pdf: false,
        is_encrypted: false,
        creator: String::new(),
        producer: String::new(),
        producer_hint: None,
        text_len: 0,
        devanagari_chars: 0,
        latin_alpha_chars: 0,
        digit_chars: 0,
        devanagari_ratio: 0.0,
        preeti_sig_ratio: 0.0,
        preeti_word_hits: 0,
        tier: Tier::XInvalid,
        confidence: Confidence::High,
        legacy_family_hint: None,
        warnings,
        error,
        preview: String::new(),
    }
}

/// Classify a single PDF file. Does NOT return `Result`: per-file data-quality
/// failures are captured in the struct's `error` / `warnings` so batch callers
/// can continue through a bad file instead of aborting.
pub fn classify_pdf(path: &Path) -> PdfClassification {
    let file_name = path
        .file_name()
        .map(|s| s.to_string_lossy().into_owned())
        .unwrap_or_else(|| path.to_string_lossy().into_owned());

    let meta = match metadata(path) {
        Ok(m) => m,
        Err(e) => {
            return invalid_pdf_result(
                file_name,
                0,
                Vec::new(),
                Some(format!("file stat failed: {}", e)),
            );
        }
    };
    let size = meta.len();

    if !magic_bytes_ok(path) {
        return invalid_pdf_result(
            file_name,
            size,
            vec![
                "file does not start with %PDF- magic bytes; likely HTML error page or corrupt"
                    .to_string(),
            ],
            None,
        );
    }

    let path_str = path.to_string_lossy();
    let (info_out, info_err, info_rc) = run_cmd("pdfinfo", &[path_str.as_ref()]);
    if info_rc != 0 {
        return invalid_pdf_result(
            file_name,
            size,
            Vec::new(),
            Some(format!(
                "pdfinfo failed (rc={}): {}",
                info_rc,
                info_err.trim()
            )),
        );
    }

    let info = parse_pdfinfo(&info_out);
    let hint = producer_hint(&info.creator, &info.producer);
    let mut warnings = info.parse_warnings.clone();
    if info.encrypted {
        warnings.push("PDF is encrypted — extraction may be blocked or incomplete".to_string());
    }

    let (text_out, text_err, text_rc) = run_cmd("pdftotext", &["-layout", path_str.as_ref(), "-"]);
    if text_rc != 0 && text_out.is_empty() {
        warnings.push(format!(
            "pdftotext failed (rc={}): {}",
            text_rc,
            text_err.trim()
        ));
    }

    let counts = count_chars(&text_out);
    let total_alpha = counts.deva + counts.latin;
    let deva_ratio = if total_alpha > 0 {
        counts.deva as f64 / total_alpha as f64
    } else {
        0.0
    };
    let preeti_sig_ratio = if counts.non_space > 0 {
        counts.preeti_sig as f64 / counts.non_space as f64
    } else {
        0.0
    };
    let preeti_word_hits = count_preeti_word_markers(&text_out);

    let decision = decide_tier(
        info.pages,
        text_out.len(),
        &counts,
        preeti_word_hits,
        preeti_sig_ratio,
        deva_ratio,
        &text_out,
        hint.as_deref(),
    );
    warnings.extend(decision.warnings);

    if matches!(hint.as_deref(), Some("C") | Some("C-or-B"))
        && !matches!(
            decision.tier,
            Tier::C | Tier::BPreeti | Tier::BLegacyUnknown | Tier::Mixed
        )
    {
        warnings.push(format!(
            "producer hint {:?} suggests scan/legacy but classifier said {:?}",
            hint, decision.tier
        ));
    }

    let preview = make_preview(&text_out);

    PdfClassification {
        file: file_name,
        size_bytes: size,
        pages: info.pages,
        is_valid_pdf: true,
        is_encrypted: info.encrypted,
        creator: info.creator,
        producer: info.producer,
        producer_hint: hint,
        text_len: text_out.len(),
        devanagari_chars: counts.deva,
        latin_alpha_chars: counts.latin,
        digit_chars: counts.digits,
        devanagari_ratio: round_to(deva_ratio, 3),
        preeti_sig_ratio: round_to(preeti_sig_ratio, 3),
        preeti_word_hits,
        tier: decision.tier,
        confidence: decision.confidence,
        legacy_family_hint: decision.legacy_family_hint,
        warnings,
        error: None,
        preview,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn looks_like_english_positive() {
        assert!(looks_like_english(
            "Government of Nepal Invitation for Bids. The project is to be completed."
        ));
    }

    #[test]
    fn looks_like_english_negative_on_legacy_garbage() {
        assert!(!looks_like_english("qEIT tflq qmfuT Eqq qBilor frfr :-"));
    }

    #[test]
    fn count_chars_counts_devanagari() {
        let c = count_chars("नेपाल सरकार Government");
        assert!(c.deva >= 8);
        assert!(c.latin >= 10);
    }

    #[test]
    fn preeti_markers_hit() {
        let text = "cfly{s jif{ @)*@ df}lb|s gLlt g]kfn /fi6«";
        let hits = count_preeti_word_markers(text);
        assert!(hits >= 3, "expected >=3 preeti marker hits, got {}", hits);
    }
}
