#!/usr/bin/env bash
set -euo pipefail

ROOT="${PI_ROOT:-$HOME/speakgov-pi}"
LLAMA_CPP_DIR="${LLAMA_CPP_DIR:-$ROOT/llama.cpp}"
LLAMA_SERVER="${LLAMA_SERVER:-$LLAMA_CPP_DIR/build/bin/llama-server}"
MODEL_DIR="${MODEL_DIR:-$ROOT/models}"
HF_VENV="${HF_VENV:-$ROOT/hf-venv}"

# Default to a Q4_K_M Gemma 4 E2B quant. The official ggml-org repo currently
# publishes Q8/bf16; Q4 is the safer Pi 5 8GB demo target.
MODEL_REPO="${MODEL_REPO:-bartowski/google_gemma-4-E2B-it-GGUF}"
MODEL_FILE="${MODEL_FILE:-google_gemma-4-E2B-it-Q4_K_M.gguf}"
MODEL_URL="${MODEL_URL:-https://huggingface.co/$MODEL_REPO/resolve/main/$MODEL_FILE}"

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8081}"
CTX_SIZE="${CTX_SIZE:-2048}"
THREADS="${THREADS:-$(nproc)}"
PARALLEL="${PARALLEL:-1}"
TEMP="${TEMP:-0.3}"
TOP_P="${TOP_P:-0.9}"
REASONING="${REASONING:-off}"
CACHE_RAM_MB="${CACHE_RAM_MB:-256}"

LOG_DIR="${LOG_DIR:-$ROOT/logs}"
PID_FILE="${PID_FILE:-$ROOT/llama-server.pid}"
LOG_FILE="${LOG_FILE:-$LOG_DIR/llama-server.log}"
MODEL_PATH="$MODEL_DIR/$MODEL_FILE"

mkdir -p "$MODEL_DIR" "$LOG_DIR" "$(dirname "$MODEL_PATH")"

if [[ ! -x "$LLAMA_SERVER" ]]; then
  echo "missing llama-server at $LLAMA_SERVER; run scripts/pi_llamacpp_install.sh first" >&2
  exit 2
fi

if [[ ! -f "$MODEL_PATH" ]]; then
  curl -L --fail --continue-at - --output "$MODEL_PATH" "$MODEL_URL"
fi

if [[ -f "$PID_FILE" ]]; then
  old_pid="$(cat "$PID_FILE" || true)"
  if [[ -n "$old_pid" ]] && kill -0 "$old_pid" >/dev/null 2>&1; then
    kill "$old_pid"
    sleep 1
  fi
fi

nohup "$LLAMA_SERVER" \
  -m "$MODEL_PATH" \
  --host "$HOST" \
  --port "$PORT" \
  --ctx-size "$CTX_SIZE" \
  --threads "$THREADS" \
  --parallel "$PARALLEL" \
  --jinja \
  --reasoning "$REASONING" \
  --cache-ram "$CACHE_RAM_MB" \
  --temp "$TEMP" \
  --top-p "$TOP_P" \
  >"$LOG_FILE" 2>&1 &

new_pid="$!"
echo "$new_pid" > "$PID_FILE"
echo "started llama-server pid=$new_pid model=$MODEL_PATH url=http://$HOST:$PORT log=$LOG_FILE"
