# Pi Gemma 4 E2B llama.cpp runbook

Goal: have a Raspberry Pi run Gemma 4 E2B locally for the demo as an edge
fallback/story lane. The Pi does not replace k2 RAG. It proves the composer can
run on low-power local hardware.

## Current status

The reachable Pi target from this Mac is:

```text
cdjk@<pi-tailnet-ip>
```

The user-facing shorthand is `cdjk@pi`, but `pi`/`pi.local` does not currently
resolve on this Mac. Use the Tailscale IP unless MagicDNS/local DNS is fixed.

Deployed on 2026-05-17:

```text
host: cdjk@<pi-tailnet-ip>
os: Debian 13 trixie, aarch64
ram: 7.9 GiB
disk root: 28 GB total
server: http://<pi-tailnet-ip>:8081
model path: /home/cdjk/speakgov-pi/models/google_gemma-4-E2B-it-Q4_K_M.gguf
llama-server pid file: /home/cdjk/speakgov-pi/llama-server.pid
log: /home/cdjk/speakgov-pi/logs/llama-server.log
```

Measured after startup:

```text
project footprint: ~3.9 GB under /home/cdjk/speakgov-pi
server RSS: ~60% of 7.9 GiB after model load
prompt cache cap: 256 MiB
generation: ~7.5 tok/s on a short chat prompt
```

## Model choice

Default:

```text
repo: bartowski/google_gemma-4-E2B-it-GGUF
file: google_gemma-4-E2B-it-Q4_K_M.gguf
size: ~3.46 GB
```

Reason: official `ggml-org/gemma-4-E2B-it-GGUF` currently has Q8 and bf16
files. Q8 is about 4.97 GB and bf16 is about 9.31 GB; Q4_K_M is a safer Pi 5
8GB target.

Optional "our old SFT" artifact:

```text
repo: voidash/gemma-helpdesk-v2-e2b-seed42
file: gguf/gemma-helpdesk-v2-e2b-Q4_K_M.gguf
size: ~3.42 GB
```

Use this only if we specifically want to show the historical SFT artifact. For
the current demo behavior, base E2B is cleaner because the navigator/RAG layer
does the service routing.

## Deploy from this repo

If SSH key auth works:

```bash
PI_SSH=cdjk@<pi-tailnet-ip> ./scripts/deploy_pi_llamacpp.sh
```

If password auth is needed:

```bash
PI_PASSWORD='...' PI_SSH=cdjk@<pi-tailnet-ip> ./scripts/deploy_pi_llamacpp.sh
```

The deploy script:

1. Copies the Pi scripts.
2. Installs build dependencies with `apt-get` when available.
3. Builds latest `llama.cpp`.
4. Downloads the Q4_K_M GGUF.
5. Starts `llama-server` on `0.0.0.0:8081`.
6. Runs an OpenAI-compatible smoke test.

## Run directly on the Pi

```bash
bash ~/gemma-god-pi/scripts/pi_llamacpp_install.sh
bash ~/gemma-god-pi/scripts/pi_llamacpp_start.sh
BASE_URL=http://127.0.0.1:8081 bash ~/gemma-god-pi/scripts/pi_llamacpp_smoke.sh
BASE_URL=http://127.0.0.1:8081 bash ~/gemma-god-pi/scripts/pi_llamacpp_office_demo.sh
```

To use the old `voidash` v2 GGUF instead:

```bash
MODEL_REPO=voidash/gemma-helpdesk-v2-e2b-seed42 \
MODEL_FILE=gguf/gemma-helpdesk-v2-e2b-Q4_K_M.gguf \
bash ~/gemma-god-pi/scripts/pi_llamacpp_start.sh
```

## Runtime endpoint

`llama-server` exposes an OpenAI-compatible endpoint:

```text
http://<pi-ip>:8081/v1/chat/completions
```

Smoke:

```bash
BASE_URL=http://<pi-ip>:8081 ./scripts/pi_llamacpp_smoke.sh
BASE_URL=http://<pi-ip>:8081 ./scripts/pi_llamacpp_office_demo.sh
```

## Expected performance

This is a demo edge lane, not the main UX path.

- Pi 5 8GB + Q4_K_M should fit.
- Use `CTX_SIZE=2048` first. Raise only if memory is stable.
- Keep `PARALLEL=1` for demo stability.
- Start script disables reasoning by default (`REASONING=off`) so short demo
  answers appear in `message.content` instead of hidden reasoning fields.
- Prompt cache is capped at 256 MiB by default (`CACHE_RAM_MB=256`) to avoid
  memory creep during repeated kiosk/demo requests.
- Expect slower answers than k2. Use short prompts and `MAX_TOKENS=80-160`.

## Demo framing

Say:

> The same small open Gemma E2B class model can run locally on a Pi. In
> production, a kiosk or office machine can keep answering basic/service-router
> flows even when the cloud path is unavailable.

Do not claim the Pi is serving the full current RAG stack unless we explicitly
wire retrieval and source DB access on the Pi.

## Video capture

Show the Pi as the local edge lane:

```bash
ssh pi@<pi-ip>
cat /proc/device-tree/model
free -h
ls -lh ~/speakgov-pi/models/*.gguf
bash ~/gemma-god-pi/scripts/pi_llamacpp_start.sh
BASE_URL=http://127.0.0.1:8081 bash ~/gemma-god-pi/scripts/pi_llamacpp_office_demo.sh
```

Good shot sequence:

1. Physical Pi beside a keyboard/monitor in an office-like setup.
2. Terminal showing the hardware model and GGUF file.
3. `llama-server` start line.
4. Local demo script answering service-navigation prompts.
5. Cut to the kiosk UI for the full ASR/RAG/TTS experience.

Caption:

```text
Gemma E2B local edge mode on a low-cost office machine
```
