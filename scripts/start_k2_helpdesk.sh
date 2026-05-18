#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/Users/k2/gemma-god}"
PYTHON_BIN="${PYTHON_BIN:-/Users/k2/miniconda3/bin/python}"
PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"
PID_FILE="${PID_FILE:-$ROOT/server/uvicorn.pid}"
LOG_FILE="${LOG_FILE:-/Volumes/T9/gemma-god/logs/helpdesk-public-${PORT}.log}"
ADMIN_PASSWORD_FILE="${ADMIN_PASSWORD_FILE:-$ROOT/.admin_password}"
WHATSAPP_BRIDGE_TOKEN_FILE="${WHATSAPP_BRIDGE_TOKEN_FILE:-$ROOT/.whatsapp_bridge_token}"

cd "$ROOT"

if [[ -f "$PID_FILE" ]]; then
  old_pid="$(cat "$PID_FILE" || true)"
  if [[ -n "${old_pid:-}" ]] && kill -0 "$old_pid" 2>/dev/null; then
    kill "$old_pid"
    for _ in $(seq 1 30); do
      kill -0 "$old_pid" 2>/dev/null || break
      sleep 1
    done
  fi
fi

mkdir -p "$(dirname "$LOG_FILE")" "$(dirname "$PID_FILE")"
: > "$LOG_FILE"

ADMIN_PASSWORD_VALUE="${ADMIN_PASSWORD:-}"
if [[ -z "$ADMIN_PASSWORD_VALUE" && -f "$ADMIN_PASSWORD_FILE" ]]; then
  ADMIN_PASSWORD_VALUE="$(cat "$ADMIN_PASSWORD_FILE")"
fi

WHATSAPP_BRIDGE_TOKEN_VALUE="${WHATSAPP_BRIDGE_TOKEN:-}"
if [[ -z "$WHATSAPP_BRIDGE_TOKEN_VALUE" && -f "$WHATSAPP_BRIDGE_TOKEN_FILE" ]]; then
  WHATSAPP_BRIDGE_TOKEN_VALUE="$(cat "$WHATSAPP_BRIDGE_TOKEN_FILE")"
fi

env -u ADAPTER_PATH \
  MODEL_ID="${MODEL_ID:-google/gemma-4-E2B-it}" \
  WEB_DIR="${WEB_DIR:-$ROOT/frontend/dist}" \
  VERTEX_KEY_FILE="${VERTEX_KEY_FILE:-/Users/k2/.vertex_key}" \
  DB_PATH="${DB_PATH:-/Volumes/T9/gemma-god/corpus_v2/index.db}" \
  TACIT_DIR="${TACIT_DIR:-$ROOT/corpora/tacit/processed}" \
  TOP_K_TACIT="${TOP_K_TACIT:-3}" \
  TOP_K_GOV="${TOP_K_GOV:-3}" \
  MAX_NEW_TOKENS="${MAX_NEW_TOKENS:-600}" \
  DECODE_DO_SAMPLE="${DECODE_DO_SAMPLE:-false}" \
  ADMIN_USERNAME="${ADMIN_USERNAME:-admin}" \
  ADMIN_PASSWORD="$ADMIN_PASSWORD_VALUE" \
  VOICE_ASR_PROVIDER="${VOICE_ASR_PROVIDER:-fastconformer-worker}" \
  VOICE_ASR_SPACE_URL="${VOICE_ASR_SPACE_URL:-https://voidash-nepali-fastconformer-demo.hf.space}" \
  VOICE_ASR_SPACE_API_NAME="${VOICE_ASR_SPACE_API_NAME:-/transcribe}" \
  VOICE_ASR_WORKER_URL="${VOICE_ASR_WORKER_URL:-http://127.0.0.1:8789}" \
  VOICE_TTS_PROVIDER="${VOICE_TTS_PROVIDER:-real-nepali-worker}" \
  VOICE_TTS_SPACE_URL="${VOICE_TTS_SPACE_URL:-https://ampixa-real-nepali-tts.hf.space}" \
  VOICE_TTS_SPACE_API_NAME="${VOICE_TTS_SPACE_API_NAME:-/synthesize}" \
  VOICE_TTS_WORKER_URL="${VOICE_TTS_WORKER_URL:-http://127.0.0.1:8788}" \
  VOICE_TTS_MODEL_REPO="${VOICE_TTS_MODEL_REPO:-ampixa/real-nepali-v0.2-kala}" \
  VOICE_TTS_SPEAKER="${VOICE_TTS_SPEAKER:-kala}" \
  VOICE_TIMEOUT_SECONDS="${VOICE_TIMEOUT_SECONDS:-240}" \
  VOICE_TTS_MAX_CHARS="${VOICE_TTS_MAX_CHARS:-230}" \
  WHATSAPP_BRIDGE_URL="${WHATSAPP_BRIDGE_URL:-http://127.0.0.1:8787}" \
  WHATSAPP_BRIDGE_TOKEN="$WHATSAPP_BRIDGE_TOKEN_VALUE" \
  "$PYTHON_BIN" -m uvicorn server.main:app --host "$HOST" --port "$PORT" \
  > "$LOG_FILE" 2>&1 &

new_pid="$!"
printf "%s" "$new_pid" > "$PID_FILE"
echo "started helpdesk pid=$new_pid model=${MODEL_ID:-google/gemma-4-E2B-it} log=$LOG_FILE"
