# gemma-god server

Single-process FastAPI server that wraps:
- mlx-lm inference of Gemma 4 + LoRA adapter
- SQLite + FTS5 retrieval over the crawler v2 corpus
- Citation extractor + refusal detector matching `eval_groundedness.py`

Runs on k2 (Mac Studio M2 Ultra) but starts up on any Mac with MLX. For
Linux/CUDA hosts, swap `mlx-lm` for `transformers` in `Composer`.

## Adapter is config, not code

```bash
# v1
ADAPTER_PATH=voidash/gemma-helpdesk-seed42 python -m uvicorn server.main:app

# v2 (when ready)
ADAPTER_PATH=voidash/gemma-helpdesk-v2-e2b-seed42 python -m uvicorn server.main:app

# v3, v4, ... same pattern
```

## Install (first time on k2)

```bash
# system Python is fine; mlx-lm takes care of metal
pip install fastapi uvicorn 'mlx-lm>=0.18' pydantic httpx

# verify mlx + metal
python -c "import mlx.core as mx; print(mx.metal.is_available())"  # True
```

## Run

```bash
# point at the production DB on the external drive
export DB_PATH=/Volumes/T9/gemma-god/corpus_v2/index.db
export ADAPTER_PATH=voidash/gemma-helpdesk-seed42
export MODEL_ID=mlx-community/gemma-4-e4b-it-bf16

# (optional) require a bearer token for /query
export BEARER_TOKEN=$(openssl rand -hex 24)

python -m uvicorn server.main:app --host 0.0.0.0 --port 8000
```

First start builds the FTS5 index over `chunks` (one-time, ~30s on 100k
chunks). Subsequent starts are sub-second after the model loads.

## Test

```bash
# liveness — no auth needed
curl localhost:8000/health

# admin — local only (or tailnet-only via X-Tailscale-User header)
curl localhost:8000/admin/info

# query
curl -X POST localhost:8000/query \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $BEARER_TOKEN" \
  -d '{"question": "नागरिकता प्रमाणपत्र हराएमा के गर्ने?"}' | jq .

# retrieval only — use this to debug RAG without generation
curl -X POST localhost:8000/retrieve \
  -H "Content-Type: application/json" \
  -d '{"question": "PAN number kasari banaune?", "top_k_tacit": 0, "top_k_gov": 5}' | jq .
```

Expected response shape:
```json
{
  "answer": "...",
  "citations": [{"url": "...", "rank": 1, "snippet": "..."}],
  "did_refuse": false,
  "retrieved_chunks": 5,
  "latency_ms": {"retrieval": 8, "generation": 2400, "total": 2410},
  "detected_lang": "devanagari"
}
```

## Tailscale Funnel

Once the server runs locally, expose it publicly:

```bash
# on k2
tailscale funnel --bg 8000

# now hittable from anywhere as
# https://k2.<your-tailnet>.ts.net
```

Funnel handles TLS automatically. Routes to `/admin/*` should be
tailnet-only — the server checks `X-Tailscale-User` header (set by Funnel
for tailnet origins) and rejects public requests.

## Endpoints

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/health` | none | liveness + adapter info |
| POST | `/retrieve` | none | retrieval-only RAG diagnostics |
| POST | `/query` | optional bearer | full RAG pipeline |
| GET | `/admin/info` | tailnet | model + db stats |
| POST | `/admin/reindex` | tailnet | rebuild FTS5 over `chunks` |

## Concurrency

mlx-lm is single-process and not thread-safe (Metal context). For >1 QPS,
either accept serialization (per-request lock — fine for the demo) or run
multiple uvicorn workers behind a separate retrieval process. v0.1 keeps
it simple: one worker, sequential generation. ~1-3 sec/query on M2 Ultra
with E4B BF16 (faster on E2B).

## Notes

- The adapter download from HF happens at startup. First boot with a new
  adapter takes ~1 min (download) + ~5-10s (load).
- `Gemma4ClippableLinear` unwrap is **not** needed in mlx-lm — that issue
  is specific to PyTorch's PEFT injection and doesn't affect MLX's adapter
  loading.
- The retrieval is BM25 over text. Vector search (LanceDB) is the next
  retrieval upgrade once the v0.1 ships.
