#!/usr/bin/env bash
set -euo pipefail

# Demo-only mode: incoming WhatsApp queries are logged to a visible JSONL file
# and meaningful government-service questions can auto-send a sanitized outreach
# draft to the official mobile contact selected by the backend.

ROOT="${ROOT:-/Users/k2/gemma-god}"
LOG_DIR="${LOG_DIR:-/Volumes/T9/gemma-god/logs}"

mkdir -p "$LOG_DIR"
: > "${PROACTIVE_OUTREACH_LOG_FILE:-$LOG_DIR/whatsapp-outreach-demo.jsonl}"

export ROOT
export PROACTIVE_OUTREACH_DEMO="${PROACTIVE_OUTREACH_DEMO:-true}"
export PROACTIVE_OUTREACH_AUTO_SEND="${PROACTIVE_OUTREACH_AUTO_SEND:-true}"
export PROACTIVE_OUTREACH_TRIGGER="${PROACTIVE_OUTREACH_TRIGGER:-noted_gov_query}"
export PROACTIVE_OUTREACH_NOTIFY_USER="${PROACTIVE_OUTREACH_NOTIFY_USER:-true}"
export PROACTIVE_OUTREACH_LOG_FILE="${PROACTIVE_OUTREACH_LOG_FILE:-$LOG_DIR/whatsapp-outreach-demo.jsonl}"
export LOG_LEVEL="${LOG_LEVEL:-info}"

exec "$ROOT/scripts/start_k2_whatsapp_bridge.sh"
