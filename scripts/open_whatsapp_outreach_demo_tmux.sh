#!/usr/bin/env bash
set -euo pipefail

SESSION="${SESSION:-speakgov-wa-demo}"
K2_HOST="${K2_HOST:-}"
K2_USER="${K2_USER:-}"
K2_PASS="${K2_PASS:-}"
HELPDESK_URL="${HELPDESK_URL:-https://helpdesk.ampixa.com}"
REMOTE_ROOT="${REMOTE_ROOT:-/Users/k2/gemma-god}"
DEMO_LOG="${DEMO_LOG:-/Volumes/T9/gemma-god/logs/whatsapp-outreach-demo.jsonl}"
BRIDGE_LOG="${BRIDGE_LOG:-/Volumes/T9/gemma-god/logs/whatsapp-bridge.log}"
HELPDESK_LOG="${HELPDESK_LOG:-/Volumes/T9/gemma-god/logs/helpdesk-public-8000.log}"

ssh_k2() {
  if [[ -n "$K2_PASS" ]]; then
    sshpass -p "$K2_PASS" ssh -o StrictHostKeyChecking=no "$K2_USER@$K2_HOST" "$@"
  else
    ssh -o StrictHostKeyChecking=no "$K2_USER@$K2_HOST" "$@"
  fi
}

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux is required" >&2
  exit 2
fi
if [[ -z "$K2_HOST" || -z "$K2_USER" ]]; then
  echo "Set K2_HOST and K2_USER before starting the demo tmux session." >&2
  exit 2
fi
if [[ -n "$K2_PASS" ]] && ! command -v sshpass >/dev/null 2>&1; then
  echo "sshpass is required when K2_PASS is set" >&2
  exit 2
fi

if tmux has-session -t "$SESSION" 2>/dev/null; then
  tmux kill-session -t "$SESSION"
fi

tmux new-session -d -s "$SESSION" -n whatsapp-demo \
  "$(declare -f ssh_k2); K2_PASS='$K2_PASS' K2_USER='$K2_USER' K2_HOST='$K2_HOST' ssh_k2 \"python3 -u '$REMOTE_ROOT/scripts/watch_whatsapp_outreach_demo.py' '$DEMO_LOG'\""

tmux split-window -h -t "$SESSION:0" \
  "printf 'WhatsApp bridge log\\n\\n'; $(declare -f ssh_k2); K2_PASS='$K2_PASS' K2_USER='$K2_USER' K2_HOST='$K2_HOST' ssh_k2 \"tail -n 80 -F '$BRIDGE_LOG'\""

tmux split-window -v -t "$SESSION:0.0" \
  "$(declare -f ssh_k2); K2_PASS='$K2_PASS' K2_USER='$K2_USER' K2_HOST='$K2_HOST'; while true; do clear; date; echo; echo 'Bridge status:'; ssh_k2 'TOKEN=\$(cat $REMOTE_ROOT/.whatsapp_bridge_token); curl -s http://127.0.0.1:8787/status -H \"Authorization: Bearer \$TOKEN\"'; echo; echo; echo 'Recent demo events:'; ssh_k2 'tail -n 12 $DEMO_LOG 2>/dev/null || true'; sleep 4; done"

tmux split-window -v -t "$SESSION:0.1" \
  "printf 'Helpdesk log\\n\\n'; $(declare -f ssh_k2); K2_PASS='$K2_PASS' K2_USER='$K2_USER' K2_HOST='$K2_HOST' ssh_k2 \"tail -n 80 -F '$HELPDESK_LOG'\""

tmux select-layout -t "$SESSION:0" tiled >/dev/null

if command -v open >/dev/null 2>&1; then
  open "$HELPDESK_URL/whatsapp" >/dev/null 2>&1 || true
  open "https://web.whatsapp.com" >/dev/null 2>&1 || true
fi

echo "tmux session ready: $SESSION"
echo "Attach with: tmux attach -t $SESSION"
