# SpeakGov Pi E2B demo

Purpose: show that the small open Gemma E2B class model can run locally on a
Raspberry Pi as an edge/offline fallback. This is not the full RAG stack; k2
still serves the main retrieval and service-navigator pipeline.

## Current Pi

```text
ssh: cdjk@<pi-tailnet-ip>
hostname: raspberrypi
os: Debian 13 trixie, aarch64
ram: 7.9 GiB
server: http://<pi-tailnet-ip>:8081
api: http://<pi-tailnet-ip>:8081/v1/chat/completions
```

`cdjk@pi` is the intended shorthand, but it did not resolve from the Mac during
setup. Use `cdjk@<pi-tailnet-ip>` unless DNS/MagicDNS is fixed.

## What is running

```text
runtime: llama.cpp llama-server
model: google_gemma-4-E2B-it-Q4_K_M.gguf
source repo: bartowski/google_gemma-4-E2B-it-GGUF
model size: ~3.46 GB
install root: /home/cdjk/speakgov-pi
pid file: /home/cdjk/speakgov-pi/llama-server.pid
log: /home/cdjk/speakgov-pi/logs/llama-server.log
```

Startup flags:

```text
--ctx-size 2048
--threads 4
--parallel 1
--jinja
--reasoning off
--cache-ram 256
--temp 0.3
--top-p 0.9
```

The memory/disk target is intentionally conservative:

```text
project footprint: ~3.9 GB under /home/cdjk/speakgov-pi
runtime RSS: ~5.0 GB
prompt cache cap: 256 MB
root disk free after setup: ~16 GB
```

## Performance

Measured on 2026-05-17:

```text
generation: ~7.5 tokens/sec
prompt processing: ~25-30 tokens/sec
short remote smoke: 1.76 s end-to-end
short local smoke: 2.85 s end-to-end
```

Demo expectation:

```text
30 generated tokens: ~4-5 s
60 generated tokens: ~8-10 s
100 generated tokens: ~14-16 s
```

This is good for an edge/offline fallback story, not the primary low-latency
voice kiosk path.

## Health check

```bash
curl http://<pi-tailnet-ip>:8081/health
```

Expected:

```json
{"status":"ok"}
```

## Smoke test from this repo

```bash
BASE_URL=http://<pi-tailnet-ip>:8081 ./scripts/pi_llamacpp_smoke.sh
```

Expected shape:

```text
SpeakGov Pi E2B ready.
latency_total=...
usage=...
```

## Direct API call

```bash
curl -sS http://<pi-tailnet-ip>:8081/v1/chat/completions \
  -H 'content-type: application/json' \
  --data '{
    "messages": [
      {
        "role": "system",
        "content": "You are SpeakGov, a concise Nepal government-service navigator."
      },
      {
        "role": "user",
        "content": "Say exactly: Pi route is reachable."
      }
    ],
    "temperature": 0.3,
    "max_tokens": 30
  }'
```

## Restart

```bash
ssh cdjk@<pi-tailnet-ip> 'bash ~/gemma-god-pi/scripts/pi_llamacpp_start.sh'
```

Check process:

```bash
ssh cdjk@<pi-tailnet-ip> \
  'ps -p $(cat ~/speakgov-pi/llama-server.pid) -o pid,etime,%cpu,%mem,rss,command'
```

Watch logs:

```bash
ssh cdjk@<pi-tailnet-ip> 'tail -f ~/speakgov-pi/logs/llama-server.log'
```

## Fresh install/rebuild

```bash
PI_SSH=cdjk@<pi-tailnet-ip> ./scripts/deploy_pi_llamacpp.sh
```

This copies scripts, installs/builds `llama.cpp`, downloads the GGUF with
resumable `curl`, starts the server, and runs smoke.

If running directly on the Pi:

```bash
bash ~/gemma-god-pi/scripts/pi_llamacpp_install.sh
bash ~/gemma-god-pi/scripts/pi_llamacpp_start.sh
BASE_URL=http://127.0.0.1:8081 bash ~/gemma-god-pi/scripts/pi_llamacpp_smoke.sh
```

## Video talking points

Use this as a short clip:

1. Show SSH into the Pi.
2. Show `free -h` and the running `llama-server` process.
3. Show `/health`.
4. Send one short chat-completion request.
5. Say:

> The main SpeakGov service runs on the Mac Studio with the full government
> corpus and voice pipeline. But the same small open E2B-class model also runs
> locally on a Raspberry Pi. That gives us an edge fallback path for offices,
> kiosks, or low-connectivity settings.

Do not say the Pi is serving full RAG unless we explicitly copy the retrieval
DB and wire the source pipeline there.
