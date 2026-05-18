#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8081}"
MODEL="${MODEL:-speakgov-pi-e2b}"
MAX_TOKENS="${MAX_TOKENS:-120}"
OUT="${OUT:-}"

SYSTEM_PROMPT="${SYSTEM_PROMPT:-You are PreVillage edge mode running locally on an office computer. You are a concise Nepal government-service navigator. Ask compact follow-up questions when intent is incomplete. Do not invent official fees, room numbers, or phone numbers.}"

PROMPTS=(
  "Say exactly: SpeakGov Pi E2B ready."
  "A citizen says: nagarikta banauna k garnu parcha? What do you ask first?"
  "A person says they were sent from Tripureshwor to Kalimati to Kalanki for PAN. How should a government helpdesk respond?"
  "Why can running locally in a government office matter for privacy?"
)

payload="$(mktemp)"
response="$(mktemp)"
records="$(mktemp)"
trap 'rm -f "$payload" "$response" "$records"' EXIT

echo "PreVillage Pi Gemma E2B benchmark"
echo "endpoint: $BASE_URL"
echo "model: $MODEL"
echo "max_tokens: $MAX_TOKENS"
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

  curl -fsS \
    -H "content-type: application/json" \
    --data @"$payload" \
    -w "\n__latency_total__=%{time_total}\n" \
    "$BASE_URL/v1/chat/completions" > "$response"

  python3 - "$response" "$prompt" >> "$records" <<'PY'
import json
import sys
from pathlib import Path

raw = Path(sys.argv[1]).read_text(encoding="utf-8")
prompt = sys.argv[2]
body, _, tail = raw.partition("\n__latency_total__=")
latency = float(tail.strip() or 0.0)
data = json.loads(body)
usage = data.get("usage") or {}
message = data["choices"][0]["message"].get("content", "").strip()
completion_tokens = int(usage.get("completion_tokens") or 0)
prompt_tokens = int(usage.get("prompt_tokens") or 0)
approx_completion_tps = completion_tokens / latency if latency > 0 else 0.0
print(json.dumps({
    "prompt": prompt,
    "latency_total_sec": round(latency, 3),
    "prompt_tokens": prompt_tokens,
    "completion_tokens": completion_tokens,
    "total_tokens": int(usage.get("total_tokens") or 0),
    "approx_completion_tokens_per_sec_including_http": round(approx_completion_tps, 2),
    "answer_preview": message[:180],
}, ensure_ascii=False))
PY
done

cat "$records"

echo
python3 - "$records" <<'PY'
import json
import statistics
import sys
from pathlib import Path

rows = [json.loads(line) for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines() if line.strip()]
if not rows:
    raise SystemExit(0)
lat = [r["latency_total_sec"] for r in rows]
tps = [r["approx_completion_tokens_per_sec_including_http"] for r in rows if r["completion_tokens"] > 0]
print("summary:")
print(f"  calls: {len(rows)}")
print(f"  latency_sec_min/median/max: {min(lat):.2f} / {statistics.median(lat):.2f} / {max(lat):.2f}")
if tps:
    print(f"  approx_completion_tps_including_http_median: {statistics.median(tps):.2f}")
PY

if [[ -n "$OUT" ]]; then
  mkdir -p "$(dirname "$OUT")"
  cp "$records" "$OUT"
  echo "wrote: $OUT"
fi
