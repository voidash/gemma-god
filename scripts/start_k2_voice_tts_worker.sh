#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/Users/k2/gemma-god}"
PYTHON_BIN="${PYTHON_BIN:-/Users/k2/miniconda3/envs/speakgov-voice311/bin/python}"
PORT="${PORT:-8788}"
HOST="${HOST:-127.0.0.1}"
PID_FILE="${PID_FILE:-$ROOT/server/voice-tts-worker.pid}"
LOG_FILE="${LOG_FILE:-/Volumes/T9/gemma-god/logs/voice-tts-worker.log}"
FRONTEND_DATA_DIR="${VOICE_TTS_FRONTEND_DATA_DIR:-$ROOT/voice_data/frontend}"

cd "$ROOT"
mkdir -p "$(dirname "$LOG_FILE")" "$(dirname "$PID_FILE")"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "missing voice env python: $PYTHON_BIN" >&2
  exit 2
fi
if [[ ! -f "$FRONTEND_DATA_DIR/candidates_lexicon.tsv" ]]; then
  echo "missing TTS frontend data: $FRONTEND_DATA_DIR" >&2
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

nohup env \
  HF_HOME="${HF_HOME:-/Volumes/T9/hf_cache}" \
  HF_HUB_CACHE="${HF_HUB_CACHE:-/Volumes/T9/hf_cache/hub}" \
  VOICE_TTS_FRONTEND_DATA_DIR="$FRONTEND_DATA_DIR" \
  VOICE_TTS_MODEL_REPO="${VOICE_TTS_MODEL_REPO:-ampixa/real-nepali-v0.2-kala}" \
  VOICE_TTS_SPEAKER="${VOICE_TTS_SPEAKER:-kala}" \
  VOICE_TTS_MAX_CHARS="${VOICE_TTS_MAX_CHARS:-230}" \
  HOST="$HOST" \
  PORT="$PORT" \
  LOG_LEVEL="${LOG_LEVEL:-info}" \
  "$PYTHON_BIN" "$ROOT/scripts/voice_tts_worker.py" \
  >> "$LOG_FILE" 2>&1 &

new_pid="$!"
printf "%s" "$new_pid" > "$PID_FILE"
echo "started voice tts worker pid=$new_pid log=$LOG_FILE"
