use gemma_god::{classify_pdf, Tier};
use std::path::PathBuf;

fn samples_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("survey")
        .join("samples")
}

struct Expected {
    file: &'static str,
    tier: Tier,
}

// Ground truth from survey/observations.md round 1.
// dos_sunya_file.pdf is intentionally omitted: genuinely ambiguous (iLovePDF-reprocessed
// noise, no clear Unicode/legacy signal); gets classified but not asserted until we
// collect more data or manually resolve.
const EXPECTED: &[Expected] = &[
    Expected { file: "lawcom_maxims.pdf",      tier: Tier::A },
    Expected { file: "ocr_eservice.pdf",       tier: Tier::A },
    Expected { file: "nrb_monetary.pdf",       tier: Tier::BPreeti },
    Expected { file: "sebon_annual.pdf",       tier: Tier::Mixed },
    Expected { file: "dop_press_falgun.pdf",   tier: Tier::BLegacyUnknown },
    Expected { file: "dos_bida_vivaran.pdf",   tier: Tier::BLegacyUnknown },
    Expected { file: "ocr_camscanner.pdf",     tier: Tier::C },
    Expected { file: "opmcm_notice.pdf",       tier: Tier::E },
    Expected { file: "lawcom_humanrights.pdf", tier: Tier::XInvalid },
];

#[test]
fn classifies_ground_truth_samples() {
    let base = samples_dir();
    assert!(
        base.is_dir(),
        "samples dir not found at {} — did round 1 survey download the files?",
        base.display()
    );

    let mut failures: Vec<String> = Vec::new();
    for e in EXPECTED {
        let path = base.join(e.file);
        if !path.exists() {
            failures.push(format!("  {}: missing at {}", e.file, path.display()));
            continue;
        }
        let result = classify_pdf(&path);
        if result.tier != e.tier {
            let preview: String = result.preview.chars().take(120).collect();
            failures.push(format!(
                "  {}: expected {:?}, got {:?}\n    stats: pages={} text_len={} deva={} latin={} ratio={:.3} sig_ratio={:.3} preeti_hits={}\n    producer_hint={:?}\n    warnings={:?}\n    preview={}",
                e.file,
                e.tier,
                result.tier,
                result.pages,
                result.text_len,
                result.devanagari_chars,
                result.latin_alpha_chars,
                result.devanagari_ratio,
                result.preeti_sig_ratio,
                result.preeti_word_hits,
                result.producer_hint,
                result.warnings,
                preview,
            ));
        }
    }

    assert!(
        failures.is_empty(),
        "Tier classification mismatches ({} file(s)):\n\n{}",
        failures.len(),
        failures.join("\n\n")
    );
}
