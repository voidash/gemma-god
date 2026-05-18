#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8081}"
MODEL="${MODEL:-speakgov-pi-e2b}"
MAX_TOKENS="${MAX_TOKENS:-140}"

SYSTEM_PROMPT="${SYSTEM_PROMPT:-You are PreVillage edge mode running locally on an office computer. You are not connected to a central server in this demo. Do not invent official fees, phone numbers, or room numbers. For government-service questions, do intake first: ask for district, municipality or ward, and case type when needed. Say that exact steps need local official sources. Keep answers under five sentences.}"

PROMPTS=(
  "A citizen says: 'nagarikta banauna k garnu parcha?' What do you ask first?"
  "A person says they were sent from Tripureshwor to Kalimati to Kalanki for PAN. How should a government helpdesk respond?"
  "Why can running locally in a government office matter for privacy?"
)

payload="$(mktemp)"
response="$(mktemp)"
trap 'rm -f "$payload" "$response"' EXIT

echo "PreVillage Pi Gemma E2B local office demo"
echo "endpoint: $BASE_URL"
echo "model: $MODEL"
echo

curl -fsS "$BASE_URL/health" >/dev/null

for prompt in "${PROMPTS[@]}"; do
  python3 - "$MODEL" "$SYSTEM_PROMPT" "$prompt" "$MAX_TOKENS" > "$payload" <<'PY'
import json
import sys

model, system_prompt, user_prompt, max_tokens = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
print(json.dumps({
    "model": model,
    "messages": [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ],
    "temperature": 0.2,
    "top_p": 0.9,
    "max_tokens": max_tokens,
    "stream": False,
}, ensure_ascii=False))
PY

  echo "USER:"
  echo "$prompt"
  echo
  curl -fsS \
    -H "content-type: application/json" \
    --data @"$payload" \
    -w "\n__latency_total__=%{time_total}\n" \
    "$BASE_URL/v1/chat/completions" > "$response"

  python3 - "$response" <<'PY'
import json
import sys
from pathlib import Path

raw = Path(sys.argv[1]).read_text(encoding="utf-8")
body, _, tail = raw.partition("\n__latency_total__=")
data = json.loads(body)
message = data["choices"][0]["message"]["content"].strip()
usage = data.get("usage") or {}
print("GEMMA E2B LOCAL:")
print(message)
if tail:
    print(f"latency_total={tail.strip()}s")
if usage:
    print("usage=" + json.dumps(usage, ensure_ascii=False))
PY
  echo
  echo "------------------------------------------------------------"
  echo
done
