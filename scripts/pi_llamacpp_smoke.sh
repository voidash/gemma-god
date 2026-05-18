#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8081}"
MAX_TOKENS="${MAX_TOKENS:-80}"

payload="$(mktemp)"
trap 'rm -f "$payload"' EXIT

cat > "$payload" <<JSON
{
  "model": "speakgov-pi-e2b",
  "messages": [
    {
      "role": "system",
      "content": "You are SpeakGov, a concise Nepal government-service navigator."
    },
    {
      "role": "user",
      "content": "Say exactly: SpeakGov Pi E2B ready."
    }
  ],
  "temperature": 0.3,
  "top_p": 0.9,
  "max_tokens": $MAX_TOKENS,
  "stream": false
}
JSON

curl -fsS "$BASE_URL/health" >/dev/null
curl -fsS \
  -H "content-type: application/json" \
  --data @"$payload" \
  -w "\nlatency_total=%{time_total}s\n" \
  "$BASE_URL/v1/chat/completions" \
  | python3 -c 'import json,sys
raw=sys.stdin.read()
body, _, tail = raw.partition("\nlatency_total=")
data=json.loads(body)
content=data["choices"][0]["message"].get("content", "").strip()
if not content:
    raise SystemExit("empty assistant content")
print(content)
if tail:
    print("latency_total=" + tail.strip())
usage=data.get("usage") or {}
if usage:
    print("usage=" + json.dumps(usage, ensure_ascii=False))
'
