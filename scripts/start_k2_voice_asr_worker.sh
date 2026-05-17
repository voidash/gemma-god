#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/Users/k2/gemma-god}"
PYTHON_BIN="${PYTHON_BIN:-/Users/k2/miniconda3/envs/speakgov-asr311/bin/python}"
PORT="${PORT:-8789}"
HOST="${HOST:-127.0.0.1}"
PID_FILE="${PID_FILE:-$ROOT/server/voice-asr-worker.pid}"
LOG_FILE="${LOG_FILE:-/Volumes/T9/gemma-god/logs/voice-asr-worker.log}"
TOKEN_FILE="${TOKEN_FILE:-$ROOT/.hf_token}"

cd "$ROOT"
mkdir -p "$(dirname "$LOG_FILE")" "$(dirname "$PID_FILE")"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "missing ASR env python: $PYTHON_BIN" >&2
  exit 2
fi

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

HF_TOKEN_VALUE="${HF_TOKEN:-}"
if [[ -z "$HF_TOKEN_VALUE" && -f "$TOKEN_FILE" ]]; then
  HF_TOKEN_VALUE="$(cat "$TOKEN_FILE")"
fi
VOICE_FFMPEG_BIN_DIR="${VOICE_FFMPEG_BIN_DIR:-/opt/homebrew/bin}"
WORKER_PATH="$VOICE_FFMPEG_BIN_DIR:/usr/local/bin:$PATH"

nohup env \
  PATH="$WORKER_PATH" \
  HF_HOME="${HF_HOME:-/Volumes/T9/hf_cache}" \
  HF_HUB_CACHE="${HF_HUB_CACHE:-/Volumes/T9/hf_cache/hub}" \
  HF_TOKEN="$HF_TOKEN_VALUE" \
  VOICE_ASR_MODEL_ID="${VOICE_ASR_MODEL_ID:-voidash/nepali-asr-staging}" \
  HOST="$HOST" \
  PORT="$PORT" \
  LOG_LEVEL="${LOG_LEVEL:-info}" \
  "$PYTHON_BIN" "$ROOT/scripts/voice_asr_worker.py" \
  >> "$LOG_FILE" 2>&1 &

new_pid="$!"
printf "%s" "$new_pid" > "$PID_FILE"
echo "started voice asr worker pid=$new_pid log=$LOG_FILE"
