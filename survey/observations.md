# Nepal Gov Corpus Survey — Round 1

Date: 2026-04-18. Scope: 15 candidate government sites probed via WebFetch + curl; 10 PDFs downloaded and empirically classified with `pdfinfo` + `pdftotext`.

## 1. Site liveness (15 probed)

| Status | Count | Sites |
|---|---|---|
| Alive, valid TLS | 10 | ocr, ird, nepalpassport, dotm, dos, lawcommission, dop, opmcm, sebon, nrb |
| Alive, **broken TLS** (works with `-k`) | 4 | moha, immigration, mof, kathmandu |
| Dead / unreachable | 1 | **nepal.gov.np** (national portal, ironically) |

Crawler MUST tolerate broken certs — ~27% of gov sites have bad TLS chains. Log and continue; don't crash. `mof.gov.np` initially returned ECONNREFUSED on WebFetch and 200 on curl — transient issues are normal, add retries.

## 2. Shared gov CDN — corpus shortcut

Most agencies host PDFs on a single shared CDN: **`https://giwmscdnone.gov.np/media/pdf_upload/*`** and `/media/app/...`. Exceptions self-host: **SEBON** (`/uploads/...`), **NRB** (`/contents/uploads/...`). Financial regulators run their own infra.

Implication: crawling `giwmscdnone.gov.np` directly (dir-listing or link-harvesting across agency homepages) can enumerate thousands of docs in one pass. Massive volume shortcut, but no inherent agency tagging — must join back via referring agency pages.

## 3. Tier distribution from 10-PDF empirical sample

| File | Pages | Empirical Tier | Producer | Devanagari ratio | Notes |
|---|---|---|---|---|---|
| lawcom_maxims.pdf | 529 | **A** native Unicode | MS Word 2013 | 0.408 | gold-standard content |
| ocr_eservice.pdf | 1 | **A** native Unicode | MS Print to PDF | 0.582 | short, clean |
| nrb_monetary.pdf | 54 | **B** legacy-font (Preeti) | Adobe InDesign | 0.000, 9 Preeti markers | **central bank's monetary policy is in Preeti** |
| sebon_annual.pdf | 123 | **B / mixed** | NAPS2 + PDFium | 0.114, 10 Preeti markers | same doc: some Unicode, some legacy |
| dop_press_falgun.pdf | 1 | **B** legacy-font (other) | Canon SC1011 scanner | 0.000 | Canon scanner → Latin-looking non-Preeti |
| dos_bida_vivaran.pdf | 1 | **B** legacy-font (other) | Canon SC1011 scanner | 0.000 | same pattern |
| dos_sunya_file.pdf | 10 | **B/C** ambiguous | iLovePDF | 0.000 | noisy, likely legacy-font scan |
| ocr_camscanner.pdf | 2 | **C** scanned image | iOS Quartz (CamScanner) | 0.000, text_len=2 | zero extractable |
| opmcm_notice.pdf | 1 | **E** English only | MS Print to PDF | 0 Devanagari, 2070 Latin | bid invitation — govt uses English for bids |
| lawcom_humanrights.pdf | 0 | **X** invalid | — | — | 651-byte HTML error, `.pdf` extension lied |

Distribution: 2 A, 4 B (Preeti-family legacy fonts), 1 mixed, 1 B/C ambiguous, 1 C, 1 E, 1 X. Not a scientific sample, but the signal is clear: **legacy-font is the dominant Nepali tier**, not Unicode.

## 4. Key findings that shape the detector

**Preeti is not a legacy fringe — it's the central bank.** NRB publishes current monetary policy in Preeti-encoded Adobe InDesign. SEBON's annual report is mixed Preeti + Unicode in the same doc. A pipeline that skips Preeti detection silently indexes garbage like `cfly{s jif{ @)*@÷*# sf] df}lb|s gLlt`.

**It's not just Preeti — there's a legacy-font family.** NRB's text matches classic Preeti markers. Canon SC1011 scanner output (DoP, DoS) uses a DIFFERENT encoding (symbols like `qEIT`, `frfr :-`, `qBilor`) that my Preeti marker list missed — probably Kantipur, Himali, or Sagarmatha. Detector must classify "legacy non-Unicode Devanagari font" as a class, then identify which font via conversion trial.

**Mixed-encoding documents exist.** SEBON's 123-page annual report is Preeti in some sections, Unicode in others. Detector needs **per-page or per-block** classification, not per-document.

**Producer/Creator metadata is a free pre-triage signal.** Proposed lookup:
- `CamScanner` / iOS Quartz → probably C (scanned)
- `Canon *` + `Adobe PSL` → legacy-font (scanner's on-device OCR emits legacy bytes)
- `NAPS2` → scanner-derived; check extraction
- `Microsoft Word` / `Microsoft: Print To PDF` → probably A (Unicode)
- `Adobe InDesign` → ambiguous — NRB hit Preeti here despite pro tooling
- `iLovePDF` → re-processed, possibly lossy

**CDN returns HTML on missing PDFs.** The 651-byte `.pdf` was XML/UTF-8 HTML. Always validate magic bytes via `file` or the first 4 bytes (`%PDF`) AFTER download, reject non-PDFs loudly.

**Initial Preeti-marker heuristic was too narrow.** Caught NRB and SEBON (classic Preeti), missed Canon-scanner output (different legacy font). Move from hardcoded marker list → **statistical character-frequency distribution**: legacy-font text has high symbol ratio (`{`, `}`, `[`, `]`, `/`, `;`, `+`, `|`, `=`) because these map to Devanagari diacritics and vowel modifiers. Threshold: if Devanagari = 0, Latin > 100, and punct/Latin ratio > 0.15 → high-probability legacy-font.

## 5. Proposed detector architecture

Three passes, cheapest first. Every document gets a tier + confidence.

**Pass A — metadata triage (zero extraction cost):**
- Read `Creator` + `Producer`. Apply lookup table above. Emit `pre_tier` (hint).

**Pass B — text extraction + statistical classification:**
- `pdftotext -layout` (fallback: `pdfminer.six`).
- Count: Devanagari Unicode (U+0900–U+097F), Latin alpha, punctuation, digits.
- Decision tree:
  - `text_len < 100 && pages > 0` → **C** (scanned image)
  - `deva >= 50 && deva_ratio >= 0.15` → **A** (native Unicode)
  - `deva == 0 && latin > 100 && punct_ratio > 0.15` → **B candidate** → go to Pass C
  - `0 < deva_ratio < 0.15 && latin > 100` → **mixed** → per-block re-classification
  - else → **E** (English-only) or unknown

**Pass C — legacy-font identification (only for B candidates):**
- Try Preeti → Unicode conversion. If output Devanagari ratio > 0.3 → confirmed Preeti.
- Fall back in order: Kantipur, Himali, Sagarmatha, Mangal. Record which worked.
- Store both raw legacy bytes AND converted Unicode.

**Pass D — mixed-encoding per-block:**
- For SEBON-style mixed docs: split per-page, classify each page independently, stitch.

## 6. Tooling gaps to close next

- Install `tesseract-lang` for Nepali OCR (Tier C).
- Install `pdfminer.six` as fallback extractor.
- Find / vendor a legacy-font → Unicode converter. Python options: `preeti-unicode`, `nepali-fonts`, or port from JS (`preeti-unicode` on npm). Must cover Preeti + Kantipur at minimum.
- Validate detector on a larger batch: harvest ~100 PDFs from `giwmscdnone.gov.np` and re-run classification to confirm tier distribution at scale.

## 7. Open questions for the detector (user decisions)

1. **HTML encoding survey** — we verified PDF tier distribution, not HTML. Some gov pages render Devanagari via loaded Preeti `.ttf` (text is Latin ASCII that LOOKS like Devanagari in browser). Round 2 should sample HTML bytes from a few pages to check.
2. **Mixed-doc handling strategy** — per-page re-classification is correct but more expensive. Acceptable for hackathon scope?
3. **OCR budget** — if Tier C volume is high (likely, given CamScanner culture), does this go to local Tesseract (slow, mediocre Nepali) or Google Document AI (paid but far better)?
