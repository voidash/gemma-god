#!/usr/bin/env bash
set -euo pipefail

ROOT="${ROOT:-/Users/k2/gemma-god}"
NODE_BIN_DIR="${NODE_BIN_DIR:-/Users/k2/.nvm/versions/node/v24.15.0/bin}"
PORT="${PORT:-8787}"
HOST="${HOST:-127.0.0.1}"
AUTH_DIR="${AUTH_DIR:-/Volumes/T9/gemma-god/whatsapp-auth}"
PID_FILE="${PID_FILE:-$ROOT/whatsapp/bridge.pid}"
LOG_FILE="${LOG_FILE:-/Volumes/T9/gemma-god/logs/whatsapp-bridge.log}"
TOKEN_FILE="${TOKEN_FILE:-$ROOT/.whatsapp_bridge_token}"
ADMIN_PASSWORD_FILE="${ADMIN_PASSWORD_FILE:-$ROOT/.admin_password}"
FFMPEG_BIN="${FFMPEG_BIN:-/opt/homebrew/bin/ffmpeg}"

cd "$ROOT"
mkdir -p "$(dirname "$LOG_FILE")" "$(dirname "$PID_FILE")"

if [[ ! -s "$TOKEN_FILE" ]]; then
  echo "missing WhatsApp bridge token file: $TOKEN_FILE" >&2
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

export PATH="$NODE_BIN_DIR:$PATH"
node --check whatsapp/src/server.mjs

API_TOKEN="$(cat "$TOKEN_FILE")"
ADMIN_PASSWORD_VALUE="${ADMIN_PASSWORD:-}"
if [[ -z "$ADMIN_PASSWORD_VALUE" && -f "$ADMIN_PASSWORD_FILE" ]]; then
  ADMIN_PASSWORD_VALUE="$(cat "$ADMIN_PASSWORD_FILE")"
fi

nohup env \
  PATH="$PATH" \
  PORT="$PORT" \
  HOST="$HOST" \
  AUTH_DIR="$AUTH_DIR" \
  API_TOKEN="$API_TOKEN" \
  HELP_DESK_BASE_URL="${HELP_DESK_BASE_URL:-http://127.0.0.1:8000}" \
  SPEAKGOV_QUERY_URL="${SPEAKGOV_QUERY_URL:-http://127.0.0.1:8000/query}" \
  ADMIN_USERNAME="${ADMIN_USERNAME:-admin}" \
  ADMIN_PASSWORD="$ADMIN_PASSWORD_VALUE" \
  HELP_DESK_ADMIN_USERNAME="${HELP_DESK_ADMIN_USERNAME:-${ADMIN_USERNAME:-admin}}" \
  HELP_DESK_ADMIN_PASSWORD="${HELP_DESK_ADMIN_PASSWORD:-$ADMIN_PASSWORD_VALUE}" \
  AUTO_CONNECT="${AUTO_CONNECT:-true}" \
  AUTO_REPLY="${AUTO_REPLY:-true}" \
  ALLOW_GROUPS="${ALLOW_GROUPS:-false}" \
  SEND_VOICE_REPLIES="${SEND_VOICE_REPLIES:-true}" \
  MAX_VOICE_REPLY_CHARS="${MAX_VOICE_REPLY_CHARS:-360}" \
  PROACTIVE_OUTREACH_DEMO="${PROACTIVE_OUTREACH_DEMO:-false}" \
  PROACTIVE_OUTREACH_AUTO_SEND="${PROACTIVE_OUTREACH_AUTO_SEND:-false}" \
  PROACTIVE_OUTREACH_TRIGGER="${PROACTIVE_OUTREACH_TRIGGER:-noted_gov_query}" \
  PROACTIVE_OUTREACH_NOTIFY_USER="${PROACTIVE_OUTREACH_NOTIFY_USER:-true}" \
  PROACTIVE_OUTREACH_LOG_FILE="${PROACTIVE_OUTREACH_LOG_FILE:-/Volumes/T9/gemma-god/logs/whatsapp-outreach-demo.jsonl}" \
  PROACTIVE_OUTREACH_USER_ALLOWLIST="${PROACTIVE_OUTREACH_USER_ALLOWLIST:-}" \
  FFMPEG_BIN="$FFMPEG_BIN" \
  LOG_LEVEL="${LOG_LEVEL:-info}" \
  node "$ROOT/whatsapp/src/server.mjs" \
  >> "$LOG_FILE" 2>&1 &

new_pid="$!"
printf "%s" "$new_pid" > "$PID_FILE"
echo "started whatsapp bridge pid=$new_pid log=$LOG_FILE"
