//! Legacy Nepali font (Preeti, Kantipur, Sagarmatha, Himali, PCS Nepali) to
//! Unicode Devanagari converter.
//!
//! Ports the mapping rules from the GPL-3.0 project `casualsnek/npttf2utf`
//! (see third_party/npttf2utf/LICENSE). Algorithm:
//!   1. pre-rules   — regex substitutions before character mapping
//!   2. character   — per-char (or longest-prefix) substitution from legacy ASCII
//!                    to Unicode Devanagari fragments
//!   3. post-rules  — regex substitutions to fix repha placement, matra reordering,
//!                    conjuncts, and vowel normalization
//!
//! Mapping table is embedded at compile time via `include_str!` on map.json.

use regex::Regex;
use serde::Deserialize;
use std::collections::HashMap;
use std::sync::OnceLock;

const MAP_JSON: &str = include_str!("../third_party/npttf2utf/map.json");

#[derive(Debug, Deserialize)]
struct RawRules {
    #[serde(rename = "character-map")]
    character_map: HashMap<String, String>,
    #[serde(rename = "pre-rules", default)]
    pre_rules: Vec<(String, String)>,
    #[serde(rename = "post-rules", default)]
    post_rules: Vec<(String, String)>,
}

#[derive(Debug, Deserialize)]
struct RawFont {
    #[allow(dead_code)]
    version: String,
    rules: RawRules,
}

struct CompiledFont {
    // Single-char keys: direct lookup.
    char_map: HashMap<char, String>,
    // Multi-char keys: pre-pass substitution, longest-first. Rare in Preeti (0 entries)
    // but may appear in other fonts.
    multi_char_map: Vec<(String, String)>,
    pre_rules: Vec<(Regex, String)>,
    post_rules: Vec<(Regex, String)>,
}

static FONTS: OnceLock<HashMap<String, CompiledFont>> = OnceLock::new();

/// Lazily parse and compile the embedded mapping on first use.
fn load_and_compile() -> HashMap<String, CompiledFont> {
    let raw: HashMap<String, RawFont> = serde_json::from_str(MAP_JSON)
        .expect("embedded map.json must parse — this is a build-time invariant");

    let mut out = HashMap::new();
    for (name, rf) in raw {
        let mut char_map: HashMap<char, String> = HashMap::new();
        let mut multi_char_map: Vec<(String, String)> = Vec::new();

        for (k, v) in rf.rules.character_map {
            let mut chars = k.chars();
            let first = chars.next();
            let second = chars.next();
            match (first, second) {
                (Some(c), None) => {
                    char_map.insert(c, v);
                }
                (Some(_), Some(_)) => {
                    multi_char_map.push((k, v));
                }
                _ => {}
            }
        }
        // Longest-prefix match: apply longer patterns before shorter ones.
        multi_char_map.sort_by_key(|(k, _)| std::cmp::Reverse(k.len()));

        let compile_rules = |rules: Vec<(String, String)>| -> Vec<(Regex, String)> {
            rules
                .into_iter()
                .map(|(pat, rep)| {
                    let adjusted = python_pattern_to_rust(&pat);
                    let rep = backref_python_to_rust(&rep);
                    let re = Regex::new(&adjusted).unwrap_or_else(|e| {
                        panic!(
                            "failed to compile regex for font {:?}, pattern {:?} (adjusted {:?}): {}",
                            name, pat, adjusted, e
                        )
                    });
                    (re, rep)
                })
                .collect()
        };

        out.insert(
            name.clone(),
            CompiledFont {
                char_map,
                multi_char_map,
                pre_rules: compile_rules(rf.rules.pre_rules),
                post_rules: compile_rules(rf.rules.post_rules),
            },
        );
    }
    out
}

/// Translate Python-style regex backreferences (`\1`, `\2`, ...) in a replacement
/// string to Rust's `regex` crate style (`${1}`, `${2}`, ...). We use the braced
/// form to avoid ambiguity when a backref is adjacent to digits in the replacement.
fn backref_python_to_rust(s: &str) -> String {
    // The regex literal `\\(\d+)` matches backslash followed by digits.
    // The closure emits `${N}` where N is the captured digit sequence.
    let re = Regex::new(r"\\(\d+)").expect("static regex compiles");
    re.replace_all(s, |caps: &regex::Captures| format!("${{{}}}", &caps[1]))
        .into_owned()
}

/// Translate a Python-regex pattern to be Rust-`regex`-crate compatible.
/// Rust's regex treats `{` as always starting a counted-repetition `{N}` /
/// `{N,M}` construct and errors if malformed, while Python only activates
/// `{...}` when it clearly looks like counted repetition.
///
/// The Preeti/Kantipur/Sagarmatha mapping uses `{` as a literal character (the
/// repha marker), never as counted repetition. So we escape every unescaped
/// `{` and `}` to `\{` / `\}`. If the upstream mapping ever grows a pattern
/// with legit counted repetition, this needs a real parser; for now it is a
/// safe blanket escape verified against every pattern in third_party/map.json.
fn python_pattern_to_rust(pattern: &str) -> String {
    let mut out = String::with_capacity(pattern.len() + 8);
    let mut chars = pattern.chars().peekable();
    while let Some(ch) = chars.next() {
        match ch {
            '\\' => {
                // Preserve existing escapes untouched.
                out.push('\\');
                if let Some(&next) = chars.peek() {
                    out.push(next);
                    chars.next();
                }
            }
            '{' | '}' => {
                out.push('\\');
                out.push(ch);
            }
            other => out.push(other),
        }
    }
    out
}

/// List of font names supported by the embedded mapping.
pub fn supported_fonts() -> Vec<&'static str> {
    let fonts = FONTS.get_or_init(load_and_compile);
    let mut names: Vec<&'static str> = fonts.keys().map(|s| s.as_str()).collect();
    names.sort();
    // Return owned-&'static borrows via a workaround: leak or re-use the keys.
    // Simpler: just return a Vec<String> in practice. But for API ergonomics we
    // return &'static strs by using a hardcoded list matching the embedded JSON.
    let _ = names; // discard — we return hardcoded names below for &'static guarantee
    vec![
        "Preeti",
        "Kantipur",
        "Sagarmatha",
        "FONTASY_HIMALI_TT",
        "PCS NEPALI",
    ]
}

/// Convert text encoded in a legacy Nepali font to Unicode Devanagari.
/// If the font name is not in the embedded table, returns the input unchanged.
pub fn convert(input: &str, font: &str) -> String {
    let fonts = FONTS.get_or_init(load_and_compile);
    let font_def = match fonts.get(font) {
        Some(f) => f,
        None => return input.to_string(),
    };

    // Stage 1 — pre-rules (regex).
    let mut text = input.to_string();
    for (re, rep) in &font_def.pre_rules {
        text = re.replace_all(&text, rep.as_str()).into_owned();
    }

    // Stage 2a — multi-char greedy substitutions (longest-first from sort).
    if !font_def.multi_char_map.is_empty() {
        for (k, v) in &font_def.multi_char_map {
            text = text.replace(k.as_str(), v.as_str());
        }
    }

    // Stage 2b — per-char substitutions. Unknown chars pass through.
    let mut mapped = String::with_capacity(text.len() * 2);
    for ch in text.chars() {
        if let Some(replacement) = font_def.char_map.get(&ch) {
            mapped.push_str(replacement);
        } else {
            mapped.push(ch);
        }
    }

    // Stage 3 — post-rules (regex).
    let mut out = mapped;
    for (re, rep) in &font_def.post_rules {
        out = re.replace_all(&out, rep.as_str()).into_owned();
    }

    out
}

/// Convenience wrapper for the most common case.
pub fn preeti_to_unicode(input: &str) -> String {
    convert(input, "Preeti")
}

// Common English / Nepali-admin-English words. Tokens matching (case-insensitively)
// are classified as English and preserved during convert_mixed. Covers:
// (a) high-frequency function words and stopwords (the, of, and, ...)
// (b) gov-document vocabulary seen in the batch (ministry, report, fiscal, ...)
// (c) generic admin/document structure terms (chapter, annex, table, ...)
const COMMON_ENGLISH_WORDS: &[&str] = &[
    "a", "an", "the", "of", "and", "or", "but", "not", "in", "on", "at", "to", "from",
    "by", "for", "with", "without", "within", "into", "onto", "upon", "about", "as",
    "is", "was", "are", "were", "be", "been", "being", "am", "have", "has", "had",
    "do", "does", "did", "will", "shall", "may", "might", "must", "can", "could",
    "should", "would", "it", "its", "it's", "this", "that", "these", "those",
    "which", "who", "whom", "whose", "what", "where", "when", "why", "how",
    "all", "any", "some", "many", "few", "more", "most", "less", "least", "much",
    "other", "others", "such", "same", "than", "then", "so", "also", "too", "only",
    "even", "just", "well", "between", "among", "during", "through", "before",
    "after", "above", "below", "over", "under", "if", "while", "each", "every", "no",
    // gov/admin vocabulary
    "report", "date", "name", "number", "type", "code", "chapter", "section",
    "article", "annex", "appendix", "schedule", "table", "form", "notice",
    "notification", "circular", "introduction", "summary", "conclusion", "reference",
    "references", "definitions", "scope", "purpose", "objective", "background",
    "methodology", "results", "analysis", "recommendation", "general", "provision",
    "procedure", "requirement", "application", "information", "details", "total",
    "subtotal", "amount", "balance", "payment", "fee", "tax", "revenue", "budget",
    "expenditure", "account", "bank", "banking", "finance", "financial", "economic",
    "economy", "development", "infrastructure", "public", "private", "sector",
    "enterprise", "company", "corporation", "limited", "ltd", "pvt", "group",
    "board", "council", "committee", "chairman", "director", "manager", "officer",
    "secretary", "staff", "employee", "training", "education", "health", "service",
    "services", "business", "industry", "industrial", "agriculture", "agricultural",
    "commerce", "commercial", "trade", "foreign", "international", "domestic", "local",
    "rural", "urban", "province", "district", "municipal", "municipality", "village",
    "ward", "unit", "division", "branch", "headquarters", "central", "regional",
    "provincial", "nepal", "nepalese", "nepali", "government", "ministry",
    "department", "office", "national", "policy", "fiscal", "year", "act", "rule",
    "regulation", "amendment", "license", "address", "page", "no", "yes",
    "invitation", "bid", "bids", "bidder", "tender", "project", "works", "plan",
    "standard", "classification", "growing", "rice", "cereals", "except", "registration",
    "registered", "applicable", "applicant", "form", "submit", "submission", "online",
    "offline", "copy", "original", "attach", "required", "optional", "mandatory",
    "description", "amount", "quantity", "price", "cost", "rate", "rates", "unit",
    "date", "time", "from", "to", "at", "on", "by", "per", "via",
];

static ENGLISH_WORD_SET: OnceLock<std::collections::HashSet<&'static str>> = OnceLock::new();

fn english_word_set() -> &'static std::collections::HashSet<&'static str> {
    ENGLISH_WORD_SET.get_or_init(|| COMMON_ENGLISH_WORDS.iter().copied().collect())
}

// Broader set used for word-level classification during convert_mixed. These
// characters are common in Preeti but also appear in normal ASCII text (URLs,
// dates), so using them for doc-level ratios would false-positive. At token
// level though, their presence inside a word is a strong Preeti signal.
const PREETI_WORD_INDICATOR_CHARS: &[char] = &[
    '{', '}', '[', ']', '|', ':', ';', '/', '\\', '=', '+',
];

// Preeti digit characters — `!@#$%^&*()` map to १२३४५६७८९०.
const PREETI_DIGIT_CHARS: &[char] = &['!', '@', '#', '$', '%', '^', '&', '*', '(', ')'];

const PREETI_WORD_MARKERS: &[&str] = &[
    "g]kfn", ";/sf/", "sf7df8f", "gful/s", "sDkgL", "xf]", "df}nL", "dlxgf", "cfly{s",
    "ljefu", "kof{j/0f", "lg0f{o", "sfof{no", "jif{", "gLlt", "a}+s",
];

// Preeti-looking word prefixes. These digraphs are rare/impossible as English
// word starts but common in Preeti because Preeti uses specific ASCII patterns
// to encode Devanagari matras (vowel modifiers) before consonants.
const PREETI_LIKE_PREFIXES: &[&str] = &[
    "lj", "lq", "lg", "lk", "lz", "lh", "ld", "lw", "lv", "lx", "lb", "lc", "lm", "ln",
    "gf", "df", "sf", "kf", "hf", "cf", "bf", "jf", "tf", "rf", "af", "ef", "zf", "xf",
    "Nf", "Kf", "Sf", "Df", "Bf", "Mf", "Rf", "Tf", "Pf",
    "gL", "kL", "sL", "bL", "jL", "tL", "nL", "dL",
    "/s", "{", "}+",
];

// Common English suffixes. A word ending in one of these is almost certainly English.
const ENGLISH_SUFFIXES: &[&str] = &[
    "tion", "sion", "ing", "ed", "ly", "ment", "ness", "able", "ible", "ship",
    "ful", "less", "est", "age", "ance", "ence", "ity", "ism", "ist", "ous",
    "al", "ive",
];

/// Token-level classification for Mixed-doc conversion.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum WordKind {
    /// Preserve as-is (Devanagari, English, acronym, digit, or empty)
    Keep,
    /// Apply legacy-font char-map
    Convert,
}

fn classify_word(word: &str) -> WordKind {
    if word.is_empty() {
        return WordKind::Keep;
    }

    // 1) Any Devanagari Unicode -> already converted, keep.
    if word.chars().any(|c| ('\u{0900}'..='\u{097F}').contains(&c)) {
        return WordKind::Keep;
    }

    // 2) Preeti word-indicator characters (broader than doc-level sig set — includes
    //    `:` `;` `/` `=` `+` etc. which appear inside Preeti words but also in normal
    //    text; safe at token level).
    if word.chars().any(|c| PREETI_WORD_INDICATOR_CHARS.contains(&c)) {
        return WordKind::Convert;
    }

    // 3) All-symbol token built from Preeti digit chars -> Preeti digits.
    //    e.g. `@)&*` = २०७८ (year 2078). Don't fire if token has letters — a
    //    stray `!` in "Hello!" shouldn't trigger.
    if !word.is_empty()
        && word.chars().all(|c| {
            PREETI_DIGIT_CHARS.contains(&c) || c == '_' || c == '-' || c == '.'
        })
        && word.chars().any(|c| PREETI_DIGIT_CHARS.contains(&c))
    {
        return WordKind::Convert;
    }

    // 4) Preeti word-marker substring -> Preeti.
    if PREETI_WORD_MARKERS.iter().any(|m| word.contains(*m)) {
        return WordKind::Convert;
    }

    // 5) Preeti-looking prefix -> Preeti.
    if PREETI_LIKE_PREFIXES.iter().any(|p| word.starts_with(*p)) {
        return WordKind::Convert;
    }

    // Strip leading/trailing punctuation for the textual analysis that follows.
    let stripped = word.trim_matches(|c: char| !c.is_alphanumeric());
    if stripped.is_empty() {
        return WordKind::Keep;
    }

    // 5) Pure digits / numeric-looking -> keep.
    if stripped
        .chars()
        .all(|c| c.is_ascii_digit() || "-./:%,".contains(c))
    {
        return WordKind::Keep;
    }

    let alpha: Vec<char> = stripped.chars().filter(|c| c.is_ascii_alphabetic()).collect();
    if alpha.is_empty() {
        return WordKind::Keep;
    }

    // 6) All uppercase acronym (NEPAL, NBC, PAN, VAT).
    if alpha.iter().all(|c| c.is_ascii_uppercase()) && alpha.len() >= 2 {
        return WordKind::Keep;
    }

    // 7) Common English dictionary word (case-insensitive).
    let lower = stripped.to_ascii_lowercase();
    if english_word_set().contains(lower.as_str()) {
        return WordKind::Keep;
    }

    // 8) Clear English suffix (-tion, -ing, -ment, ...).
    if ENGLISH_SUFFIXES.iter().any(|s| lower.ends_with(s)) && alpha.len() >= 4 {
        return WordKind::Keep;
    }

    // 9) Title case proper noun: first cap + rest lower + has vowel.
    let first_upper = alpha[0].is_ascii_uppercase();
    let rest_lower = alpha[1..].iter().all(|c| c.is_ascii_lowercase());
    let has_vowel = alpha.iter().any(|c| "aeiouyAEIOUY".contains(*c));
    if first_upper && rest_lower && has_vowel && alpha.len() >= 3 {
        return WordKind::Keep;
    }

    // 10) All lowercase with healthy English vowel ratio.
    if alpha.iter().all(|c| c.is_ascii_lowercase()) && alpha.len() >= 4 {
        let vowels = alpha
            .iter()
            .copied()
            .filter(|c| "aeiouy".contains(*c))
            .count();
        let ratio = vowels as f64 / alpha.len() as f64;
        if ratio >= 0.30 {
            return WordKind::Keep;
        }
    }

    // Default in a Mixed doc: unknown ASCII token is most likely Preeti that
    // escaped the explicit signal checks. Convert.
    WordKind::Convert
}

enum Segment<'a> {
    Whitespace(&'a str),
    Word(&'a str),
}

fn segment<'a>(input: &'a str) -> Vec<Segment<'a>> {
    let mut out = Vec::new();
    let bytes = input.as_bytes();
    let mut i = 0;
    while i < bytes.len() {
        // Find next boundary: whitespace runs vs non-whitespace runs, counted in chars.
        let start = i;
        let first = input[i..].chars().next().expect("non-empty slice");
        let is_ws = first.is_whitespace();
        while i < bytes.len() {
            let ch = input[i..].chars().next().expect("in-range");
            if ch.is_whitespace() != is_ws {
                break;
            }
            i += ch.len_utf8();
        }
        let slice = &input[start..i];
        if is_ws {
            out.push(Segment::Whitespace(slice));
        } else {
            out.push(Segment::Word(slice));
        }
    }
    out
}

/// Convert a document that contains a mix of Unicode Devanagari + Preeti-encoded
/// Nepali + English content. Applies the legacy-font pipeline only to words
/// classified as Preeti-like; preserves Devanagari and English words untouched.
///
/// IMPORTANT: the full pipeline (pre-rules + char-map + post-rules) runs
/// PER-SEGMENT on Convert words, not globally on the combined document. This is
/// essential because Preeti post-rules assume their input came from the char-map
/// (specific ASCII markers like `{` and `m`, Devanagari cluster patterns). If
/// applied globally, they silently corrupt:
///   - English words containing `m` (rule 4 relocates the `m`, rule 7 turns
///     adjacent `प` into `फ`), and
///   - already-Unicode Devanagari (rule 9 reorders i-matra around consonants
///     that were already in correct logical order).
/// Empirically confirmed on `"नेपाल Government"` which corrupted to
/// `"नेफाल Governent"` under global post-rules.
pub fn convert_mixed(input: &str, font: &str) -> String {
    let fonts = FONTS.get_or_init(load_and_compile);
    if !fonts.contains_key(font) {
        return input.to_string();
    }

    let mut out = String::with_capacity(input.len() * 2);
    for seg in segment(input) {
        match seg {
            Segment::Whitespace(ws) => out.push_str(ws),
            Segment::Word(w) => match classify_word(w) {
                WordKind::Keep => out.push_str(w),
                WordKind::Convert => out.push_str(&convert(w, font)),
            },
        }
    }
    out
}

/// High-frequency Nepali words — used as a *quality* gate on conversion output.
/// Unlike the raw Devanagari ratio (which fires on any successful char-map even
/// if the result is gibberish), hitting these words means the converter
/// produced real Nepali morphemes, not random Devanagari noise.
/// Chosen for governmental/administrative document frequency.
pub const NEPALI_HIGH_FREQ_WORDS: &[&str] = &[
    "नेपाल", "सरकार", "आर्थिक", "वर्ष", "मन्त्रालय", "कार्यालय", "विभाग",
    "समिति", "प्रतिवेदन", "नीति", "ऐन", "नियम", "सम्बन्धी", "प्रदेश", "जिल्ला",
    "गाउँ", "नगर", "पालिका", "राष्ट्र", "आयोग", "अधिकार", "व्यवस्थापन",
    "मिति", "प्रमुख", "बारेमा", "केन्द्रीय", "राजपत्र", "राजस्व", "कर",
    "बैंक", "भन्सार", "शिक्षा", "स्वास्थ्य", "सूचना", "सेवा", "प्रक्रिया",
];

/// Count how many known high-frequency Nepali words appear in the text.
/// This is the trustworthy signal for "conversion actually produced Nepali".
pub fn nepali_word_hits(text: &str) -> usize {
    NEPALI_HIGH_FREQ_WORDS
        .iter()
        .filter(|w| text.contains(*w))
        .count()
}

/// Result of a best-effort legacy-font guess.
#[derive(Debug, Clone)]
pub struct BestEffortResult {
    pub font: &'static str,
    pub text: String,
    /// Unicode Devanagari ratio of the converted output — caveat: a high ratio
    /// does NOT mean the output is real Nepali. Combine with `nepali_word_hits`.
    pub devanagari_ratio: f64,
    /// Count of known high-frequency Nepali words in the output. Primary quality
    /// signal. A result with >=3 hits is likely a correct font identification;
    /// 0 hits after conversion means no supported font matches the source.
    pub nepali_word_hits: usize,
}

/// Try converting the input with each supported legacy font. Scores results by
/// `nepali_word_hits` first (real-word count), using Devanagari ratio only as
/// a tiebreaker. If NO font yields any Nepali words, the result's hits will be
/// 0 — callers should treat that as "font family unknown; do not trust the
/// conversion" rather than a successful identification.
pub fn best_effort_convert(input: &str) -> BestEffortResult {
    let mut best: Option<BestEffortResult> = None;
    for font in supported_fonts() {
        let text = convert(input, font);
        let deva = devanagari_ratio(&text);
        let hits = nepali_word_hits(&text);
        let candidate = BestEffortResult {
            font,
            text,
            devanagari_ratio: deva,
            nepali_word_hits: hits,
        };
        let take = match &best {
            None => true,
            Some(b) => {
                // Primary: more Nepali words. Secondary: higher Devanagari ratio.
                candidate.nepali_word_hits > b.nepali_word_hits
                    || (candidate.nepali_word_hits == b.nepali_word_hits
                        && candidate.devanagari_ratio > b.devanagari_ratio)
            }
        };
        if take {
            best = Some(candidate);
        }
    }
    best.unwrap_or(BestEffortResult {
        font: "Preeti",
        text: input.to_string(),
        devanagari_ratio: 0.0,
        nepali_word_hits: 0,
    })
}

fn devanagari_ratio(text: &str) -> f64 {
    let mut deva = 0usize;
    let mut latin = 0usize;
    for ch in text.chars() {
        if ('\u{0900}'..='\u{097F}').contains(&ch) {
            deva += 1;
        } else if ch.is_ascii_alphabetic() {
            latin += 1;
        }
    }
    if deva + latin == 0 {
        0.0
    } else {
        deva as f64 / (deva + latin) as f64
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn preeti_converts_kathmandu() {
        // From Shuvayatra/preeti README: `sf7df08"` -> `काठमाण्डू`
        assert_eq!(preeti_to_unicode("sf7df08\""), "काठमाण्डू");
    }

    #[test]
    fn preeti_converts_nepal() {
        // From NRB sample preview: `g]kfn` -> `नेपाल`
        assert_eq!(preeti_to_unicode("g]kfn"), "नेपाल");
    }

    #[test]
    fn preeti_converts_fiscal_year_phrase() {
        // From NRB monetary-policy preview: `cfly{s jif{` -> `आर्थिक वर्ष`
        // This exercises the repha reordering post-rules (`{` -> `र्`).
        assert_eq!(preeti_to_unicode("cfly{s jif{"), "आर्थिक वर्ष");
    }

    #[test]
    fn unknown_font_passes_through() {
        assert_eq!(convert("hello", "NonExistentFont"), "hello");
    }

    #[test]
    fn empty_input_returns_empty() {
        assert_eq!(preeti_to_unicode(""), "");
    }

    #[test]
    fn preeti_dot_maps_to_danda() {
        // Preeti maps `.` to `।` (Devanagari danda, Nepali full stop).
        // This was surprising during test authoring — documenting it here.
        assert_eq!(preeti_to_unicode("."), "।");
    }

    #[test]
    fn preeti_unmapped_ascii_passes_through() {
        // `@` is mapped (to Nepali digit २), but email-like text with unmapped
        // surrounding characters still partially passes through. Testing `^`
        // which IS mapped (to ६ — digit 6) is not useful. Truly unmapped ASCII:
        // space, tab, newline pass through. Check whitespace:
        assert_eq!(preeti_to_unicode("\n"), "\n");
    }

    #[test]
    fn supported_fonts_includes_preeti() {
        let fonts = supported_fonts();
        assert!(fonts.contains(&"Preeti"));
        assert!(fonts.contains(&"Kantipur"));
    }

    #[test]
    fn best_effort_convert_picks_preeti_for_preeti_input() {
        let result = best_effort_convert("g]kfn /fi6« a}+s");
        assert_eq!(result.font, "Preeti", "expected Preeti to win on Preeti input");
        assert!(
            result.devanagari_ratio > 0.5,
            "expected high Devanagari ratio, got {}",
            result.devanagari_ratio
        );
        assert!(
            result.nepali_word_hits >= 2,
            "expected Nepali words in converted output, got {}",
            result.nepali_word_hits
        );
    }

    #[test]
    fn best_effort_convert_gives_low_word_hits_for_random_ascii_garbage() {
        // Garbage ASCII should NOT produce high Nepali word hits even if the
        // char-map produces many Devanagari chars. This is the safety check
        // that stops false-positive font identifications on BLegacyUnknown
        // docs (like Canon scanner output that isn't actually Preeti).
        let result = best_effort_convert("zzzz qqqq aaaa bbbb ffff cccc");
        assert!(
            result.nepali_word_hits <= 1,
            "garbage ASCII should not produce real Nepali words, got {} hits (text: {})",
            result.nepali_word_hits, result.text
        );
    }

    #[test]
    fn nepali_word_hits_detects_real_nepali() {
        assert!(nepali_word_hits("नेपाल सरकार आर्थिक वर्ष") >= 4);
        assert_eq!(nepali_word_hits("random english text"), 0);
    }

    #[test]
    fn post_rule_removes_standalone_halant_before_aa() {
        // Post-rule 0 removes `्ा` (stranded halant before aa-matra). Ensure it fires.
        let out = preeti_to_unicode("sf"); // `s` -> `क`, `f` -> `ा`. Expect `का`, no halant.
        assert_eq!(out, "का");
    }

    #[test]
    fn classify_word_flags_preeti_signal_chars() {
        assert_eq!(classify_word("cfly{s"), WordKind::Convert);
        assert_eq!(classify_word("jif{"), WordKind::Convert);
        assert_eq!(classify_word("sf7df8f"), WordKind::Convert);
    }

    #[test]
    fn classify_word_keeps_english_and_devanagari() {
        assert_eq!(classify_word("Government"), WordKind::Keep);
        assert_eq!(classify_word("Nepal"), WordKind::Keep);
        assert_eq!(classify_word("cereals"), WordKind::Keep);
        assert_eq!(classify_word("the"), WordKind::Keep);
        assert_eq!(classify_word("NBC"), WordKind::Keep); // acronym
        assert_eq!(classify_word("123"), WordKind::Keep); // digits
        assert_eq!(classify_word("नेपाल"), WordKind::Keep); // Devanagari
    }

    #[test]
    fn classify_word_converts_preeti_prefix_forms() {
        // Preeti words without sig chars but with characteristic prefixes should convert.
        assert_eq!(classify_word("ljefu"), WordKind::Convert); // "विभाग" (department)
    }

    #[test]
    fn convert_mixed_preserves_english_sections() {
        let input = "Nepal Standard Industrial Classification lqmofsnfksf gfd tyf ljj/0f";
        let out = convert_mixed(input, "Preeti");
        assert!(out.contains("Nepal"), "expected 'Nepal' preserved, got: {}", out);
        assert!(out.contains("Standard"), "expected 'Standard' preserved, got: {}", out);
        assert!(out.contains("Industrial"), "expected 'Industrial' preserved, got: {}", out);
        assert!(
            out.contains("Classification"),
            "expected 'Classification' preserved, got: {}",
            out
        );
        let deva_count = out
            .chars()
            .filter(|c| ('\u{0900}'..='\u{097F}').contains(c))
            .count();
        assert!(
            deva_count > 5,
            "expected Devanagari chars from Preeti conversion, got {}",
            deva_count
        );
    }

    #[test]
    fn convert_mixed_preserves_existing_devanagari() {
        let input = "नेपाल सरकार Government of Nepal";
        let out = convert_mixed(input, "Preeti");
        assert!(out.contains("नेपाल"));
        assert!(out.contains("सरकार"));
        assert!(out.contains("Government"));
    }

    #[test]
    fn convert_mixed_on_pure_preeti_yields_nepali_words() {
        let input = "g]kfn /fi6« a}+s";
        let mixed = convert_mixed(input, "Preeti");
        assert!(
            nepali_word_hits(&mixed) >= 1,
            "convert_mixed on pure Preeti should yield Nepali words, got: {}",
            mixed
        );
    }

    #[test]
    fn convert_mixed_preserves_acronyms_and_numbers() {
        let input = "PAN VAT 2081 NBC 205";
        let out = convert_mixed(input, "Preeti");
        assert_eq!(out, input, "expected acronyms/numbers untouched, got: {}", out);
    }
}
