#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/Users/k2/gemma-god}"
PYTHON_BIN="${PYTHON_BIN:-/Users/k2/miniconda3/bin/python}"
PORT="${PORT:-8001}"
HOST="${HOST:-0.0.0.0}"
CKPT="${CKPT:-best}"
ADAPTER_ROOT="${ADAPTER_ROOT:-/Volumes/T9/gemma-god/adapters/gemma-helpdesk-v6-4-e4b-g6e-qlora-seed42}"
PID_FILE="${PID_FILE:-$ROOT/server/uvicorn-v6-4-private-${PORT}.pid}"
LOG_FILE="${LOG_FILE:-/Volumes/T9/gemma-god/logs/server-v6-4-private-${PORT}-${CKPT}.log}"

cd "$ROOT"

adapter_path="$ADAPTER_ROOT/$CKPT"
if [[ ! -f "$adapter_path/adapter_model.safetensors" ]]; then
  echo "missing adapter checkpoint: $adapter_path" >&2
  exit 2
fi

if [[ -f "$PID_FILE" ]]; then
  old_pid="$(cat "$PID_FILE" || true)"
  if [[ -n "${old_pid:-}" ]] && kill -0 "$old_pid" 2>/dev/null; then
    kill "$old_pid"
    for _ in $(seq 1 60); do
      kill -0 "$old_pid" 2>/dev/null || break
      sleep 1
    done
  fi
fi

mkdir -p "$(dirname "$LOG_FILE")"
: > "$LOG_FILE"

HF_TOKEN_VALUE="${HF_TOKEN:-}"
if [[ -z "$HF_TOKEN_VALUE" && -f "$ROOT/.hf_token" ]]; then
  HF_TOKEN_VALUE="$(cat "$ROOT/.hf_token")"
fi

env \
  HF_HOME="${HF_HOME:-/Volumes/T9/hf_cache}" \
  HF_HUB_CACHE="${HF_HUB_CACHE:-/Volumes/T9/hf_cache/hub}" \
  HF_TOKEN="$HF_TOKEN_VALUE" \
  MODEL_ID="${MODEL_ID:-google/gemma-4-E4B-it}" \
  ADAPTER_PATH="$adapter_path" \
  DB_PATH="${DB_PATH:-/Volumes/T9/gemma-god/corpus_v2/index.db}" \
  TACIT_DIR="${TACIT_DIR:-$ROOT/corpora/tacit/processed}" \
  TOP_K_TACIT="${TOP_K_TACIT:-3}" \
  TOP_K_GOV="${TOP_K_GOV:-3}" \
  MAX_NEW_TOKENS="${MAX_NEW_TOKENS:-360}" \
  DECODE_DO_SAMPLE="${DECODE_DO_SAMPLE:-false}" \
  DECODE_REPETITION_PENALTY="${DECODE_REPETITION_PENALTY:-1.05}" \
  "$PYTHON_BIN" -m uvicorn server.main:app --host "$HOST" --port "$PORT" \
  > "$LOG_FILE" 2>&1 &

new_pid="$!"
printf "%s" "$new_pid" > "$PID_FILE"
echo "started private v6.4 pid=$new_pid ckpt=$CKPT port=$PORT log=$LOG_FILE"
