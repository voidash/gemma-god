//! BM25 query over the corpus index.
//!
//! Usage:
//!   ./target/release/query "company registration"
//!   ./target/release/query "PAN number" --top 10
//!   ./target/release/query "आर्थिक वर्ष" --top 5

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::fs::File;
use std::io::BufReader;
use std::path::PathBuf;

#[derive(Serialize, Deserialize)]
struct ChunkMeta {
    doc_id: String,
    chunk_id: usize,
    source_url: Option<String>,
    tier: String,
    text: String,
}

#[derive(Serialize, Deserialize)]
struct Bm25Index {
    chunks: Vec<ChunkMeta>,
    postings: HashMap<String, Vec<(u32, u32)>>,
    doc_lens: Vec<u32>,
    avgdl: f64,
    num_docs: u32,
}

fn tokenize(text: &str) -> Vec<String> {
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
        }
        if s.chars().count() >= 2 {
            tokens.push(s);
        }
    }
    tokens
}

fn bm25_score(
    index: &Bm25Index,
    query_terms: &[String],
) -> Vec<(u32, f64)> {
    const K1: f64 = 1.5;
    const B: f64 = 0.75;
    let mut scores: HashMap<u32, f64> = HashMap::new();
    let n = index.num_docs as f64;

    for term in query_terms {
        let Some(posts) = index.postings.get(term) else {
            continue;
        };
        let df = posts.len() as f64;
        // Okapi BM25 IDF — Lucene-style smoothing, clamped at >= 0.
        let idf = ((n - df + 0.5) / (df + 0.5) + 1.0).ln().max(0.0);
        for &(chunk_idx, tf) in posts {
            let dl = index.doc_lens[chunk_idx as usize] as f64;
            let tf = tf as f64;
            let norm = tf * (K1 + 1.0) / (tf + K1 * (1.0 - B + B * dl / index.avgdl));
            *scores.entry(chunk_idx).or_insert(0.0) += idf * norm;
        }
    }

    let mut ranked: Vec<(u32, f64)> = scores.into_iter().collect();
    ranked.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    ranked
}

fn main() -> std::io::Result<()> {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 2 {
        eprintln!("usage: query \"<query string>\" [--top N] [--json]");
        std::process::exit(2);
    }

    let mut query = String::new();
    let mut top_k: usize = 5;
    let mut as_json = false;
    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            "--top" => {
                if i + 1 >= args.len() {
                    eprintln!("--top requires a number");
                    std::process::exit(2);
                }
                top_k = args[i + 1].parse().unwrap_or(5);
                i += 2;
            }
            "--json" => {
                as_json = true;
                i += 1;
            }
            other => {
                if !query.is_empty() {
                    query.push(' ');
                }
                query.push_str(other);
                i += 1;
            }
        }
    }

    if query.trim().is_empty() {
        eprintln!("empty query");
        std::process::exit(2);
    }

    let index_path = PathBuf::from("survey/bm25_index.json");
    if !index_path.is_file() {
        eprintln!("error: {} not found — run build_index first", index_path.display());
        std::process::exit(2);
    }

    eprintln!("loading index from {}...", index_path.display());
    let file = File::open(&index_path)?;
    let reader = BufReader::new(file);
    let index: Bm25Index = serde_json::from_reader(reader).expect("index JSON must parse");
    eprintln!(
        "loaded: {} chunks, {} terms, avgdl={:.1}",
        index.num_docs,
        index.postings.len(),
        index.avgdl
    );

    let query_terms = tokenize(&query);
    eprintln!("query: {:?} -> tokens: {:?}", query, query_terms);
    if query_terms.is_empty() {
        eprintln!("no indexable tokens in query");
        std::process::exit(2);
    }

    let ranked = bm25_score(&index, &query_terms);
    let top: Vec<_> = ranked.into_iter().take(top_k).collect();

    if as_json {
        #[derive(Serialize)]
        struct Result<'a> {
            rank: usize,
            score: f64,
            doc_id: &'a str,
            chunk_id: usize,
            tier: &'a str,
            source_url: Option<&'a str>,
            text: &'a str,
        }
        let items: Vec<Result> = top
            .iter()
            .enumerate()
            .map(|(r, (idx, score))| {
                let m = &index.chunks[*idx as usize];
                Result {
                    rank: r + 1,
                    score: *score,
                    doc_id: &m.doc_id,
                    chunk_id: m.chunk_id,
                    tier: &m.tier,
                    source_url: m.source_url.as_deref(),
                    text: &m.text,
                }
            })
            .collect();
        println!("{}", serde_json::to_string_pretty(&items).unwrap());
    } else {
        println!("\n=== Top {} results for: {:?} ===\n", top.len(), query);
        for (rank, (idx, score)) in top.iter().enumerate() {
            let m = &index.chunks[*idx as usize];
            println!("[{}] score={:.3}  tier={}  doc={}", rank + 1, score, m.tier, m.doc_id);
            if let Some(url) = &m.source_url {
                println!("    source: {}", url);
            }
            let preview: String = m.text.chars().take(400).collect();
            println!("    {}", preview.replace('\n', " "));
            println!();
        }
    }

    Ok(())
}
