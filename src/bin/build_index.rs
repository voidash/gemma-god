//! Build a minimal BM25 index from survey/corpus_chunks.jsonl.
//!
//! Tokenization: split on whitespace, lowercase ASCII alphanumeric, keep
//! Devanagari Unicode as-is, drop punctuation and single-char tokens.
//! No stemming (no reliable Nepali stemmer), no stopword removal.
//!
//! BM25 parameters: k1 = 1.5, b = 0.75 (standard).
//!
//! Persists the index to survey/bm25_index.json.

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs::File;
use std::io::{BufRead, BufReader, BufWriter, Write};
use std::path::PathBuf;

#[derive(Deserialize)]
struct Chunk {
    doc_id: String,
    chunk_id: usize,
    text: String,
    source_url: Option<String>,
    tier: String,
    #[allow(dead_code)]
    total_pages: u32,
    #[allow(dead_code)]
    char_start: usize,
    #[allow(dead_code)]
    char_end: usize,
}

#[derive(Serialize, Deserialize)]
pub struct ChunkMeta {
    pub doc_id: String,
    pub chunk_id: usize,
    pub source_url: Option<String>,
    pub tier: String,
    pub text: String,
}

#[derive(Serialize, Deserialize)]
pub struct Bm25Index {
    pub chunks: Vec<ChunkMeta>,
    /// term -> Vec<(chunk_idx, term_frequency)>
    pub postings: HashMap<String, Vec<(u32, u32)>>,
    pub doc_lens: Vec<u32>,
    pub avgdl: f64,
    pub num_docs: u32,
}

pub fn tokenize(text: &str) -> Vec<String> {
    let mut tokens = Vec::new();
    for raw in text.split_whitespace() {
        let mut s = String::with_capacity(raw.len());
        for c in raw.chars() {
            if c.is_ascii_alphanumeric() {
                for lc in c.to_lowercase() {
                    s.push(lc);
                }
            } else if ('\u{0900}'..='\u{097F}').contains(&c) {
                s.push(c);
            }
            // drop punctuation, symbols, etc.
        }
        if s.chars().count() >= 2 {
            tokens.push(s);
        }
    }
    tokens
}

fn main() -> std::io::Result<()> {
    let survey = PathBuf::from("survey");
    let in_path = survey.join("corpus_chunks.jsonl");
    let out_path = survey.join("bm25_index.json");

    if !in_path.is_file() {
        eprintln!("error: {} not found — run ingest first", in_path.display());
        std::process::exit(2);
    }

    eprintln!("reading {}", in_path.display());
    let file = File::open(&in_path)?;
    let reader = BufReader::new(file);

    let mut chunks_meta: Vec<ChunkMeta> = Vec::new();
    let mut doc_lens: Vec<u32> = Vec::new();
    let mut postings: HashMap<String, Vec<(u32, u32)>> = HashMap::new();
    let mut total_tokens: u64 = 0;

    for line in reader.lines() {
        let line = line?;
        if line.trim().is_empty() {
            continue;
        }
        let chunk: Chunk = match serde_json::from_str(&line) {
            Ok(c) => c,
            Err(e) => {
                eprintln!("skipping malformed line: {}", e);
                continue;
            }
        };

        let chunk_idx = chunks_meta.len() as u32;
        let tokens = tokenize(&chunk.text);
        let doc_len = tokens.len() as u32;

        // Compute term frequencies within the chunk
        let mut tf_map: HashMap<String, u32> = HashMap::new();
        for t in &tokens {
            *tf_map.entry(t.clone()).or_insert(0) += 1;
        }
        for (term, tf) in tf_map {
            postings.entry(term).or_default().push((chunk_idx, tf));
        }

        total_tokens += doc_len as u64;
        doc_lens.push(doc_len);
        chunks_meta.push(ChunkMeta {
            doc_id: chunk.doc_id,
            chunk_id: chunk.chunk_id,
            source_url: chunk.source_url,
            tier: chunk.tier,
            text: chunk.text,
        });
    }

    let num_docs = chunks_meta.len() as u32;
    let avgdl = if num_docs > 0 {
        total_tokens as f64 / num_docs as f64
    } else {
        0.0
    };

    eprintln!(
        "indexed {} chunks, {} unique terms, avgdl={:.1} tokens",
        num_docs,
        postings.len(),
        avgdl
    );

    let index = Bm25Index {
        chunks: chunks_meta,
        postings,
        doc_lens,
        avgdl,
        num_docs,
    };

    let out = File::create(&out_path)?;
    let mut writer = BufWriter::new(out);
    serde_json::to_writer(&mut writer, &index).expect("serialize index");
    writer.flush()?;

    let size = std::fs::metadata(&out_path)?.len();
    eprintln!(
        "wrote {} ({:.1} MB)",
        out_path.display(),
        size as f64 / 1_048_576.0
    );

    Ok(())
}
