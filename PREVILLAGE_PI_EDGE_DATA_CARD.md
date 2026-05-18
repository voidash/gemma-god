# PreVillage Pi Edge Data Card

Snapshot date: 2026-05-17.

## Why This Matters

The Pi is the proof that PreVillage is not only an expensive cloud demo.

The full public demo can use the stronger Mac/k2 stack for national RAG, ASR,
TTS, WhatsApp, and kiosk UX. But the Pi proves the open-model edge lane:
an office can run a small Gemma E2B-class model locally for intake, privacy,
fallback, and short service-navigation answers.

Safe claim:

> The full RAG and voice stack can run on an office computer. A Raspberry Pi 5
> can already run the local Gemma E2B edge mode for intake and fallback, and it
> can run the Nepali TTS and ASR workers as measured edge components.

Avoid:

> The Pi serves the full national RAG corpus.

Do not say that unless the retrieval DB and source index are copied and wired on
the Pi.

## Current Pi

```text
host: cdjk@<pi-tailnet-ip>
hostname: raspberrypi
hardware: Raspberry Pi 5 Model B Rev 1.0
os: Debian 13 trixie, aarch64
ram: 7.9 GiB
server: http://<pi-tailnet-ip>:8081
api: /v1/chat/completions
runtime: llama.cpp llama-server
```

## Model

```text
repo: bartowski/google_gemma-4-E2B-it-GGUF
file: google_gemma-4-E2B-it-Q4_K_M.gguf
local file size on Pi: 3.3G
HF file size: 3,462,678,272 bytes
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

Measured resource use:

```text
project footprint: 3.9G under /home/cdjk/speakgov-pi
root disk after voice benchmark: 28G total, 12G free
llama-server RSS: ~5.0G
RAM total: 7.9G
```

## Pi Performance

Fresh smoke from this repo:

```text
SpeakGov Pi E2B ready.
latency_total=2.770245s
usage={"completion_tokens":9,"prompt_tokens":38,"total_tokens":47}
```

Office-demo prompts from this repo:

```text
47 completion tokens: 11.35s end-to-end
57 completion tokens:  9.09s end-to-end
55 completion tokens: 10.74s end-to-end
```

llama.cpp internal timings from the same run:

```text
prompt eval: 20-29 tok/s in recent short calls
generation: 5.6-8.0 tok/s in recent short calls
typical short answer: 30 tokens in ~4-5s, 60 tokens in ~8-10s
```

Use narration number:

> On a Raspberry Pi 5, Gemma E2B Q4 runs locally at roughly 6-8 generated
> tokens per second for short service-navigation answers.

Final restore smoke after ASR/TTS benchmark:

```text
SpeakGov Pi E2B ready.
latency_total=3.054785s
usage={"completion_tokens":9,"prompt_tokens":38,"total_tokens":47}
generation: 6.95 tok/s
llama-server RSS: 4,708,560 KB
```

## Voice Stack Data

Current deployed voice providers:

```text
ASR provider: fastconformer-worker
ASR model: voidash/nepali-asr-staging
TTS provider: real-nepali-worker
TTS model: ampixa/real-nepali-v0.2-kala
TTS speaker: kala
```

Warm local worker latency from `HACKATHON_DEMO_RUNBOOK.md`:

```text
ASR old HF Space: 12.9s server-side
ASR local warm worker: ~498-532 ms server-side
TTS old HF Space: 11.8s server-side
TTS local warm worker: ~290-310 ms server-side
```

Artifact sizes checked from Hugging Face metadata:

```text
TTS checkpoint ampixa/real-nepali-v0.2-kala/checkpoint.ckpt: 935,178,960 bytes
ASR selected .nemo artifact: 122,828,800 bytes
ASR larger CTC .nemo artifacts: 436,275,200 bytes
Gemma E2B Q4_K_M GGUF: 3,462,678,272 bytes
```

Pi voice benchmark on 2026-05-17:

```text
Pi: Raspberry Pi 5, Debian 13 aarch64, 7.9 GiB RAM
Python env: ~/speakgov-voice-pi/venv-sys with system torch 2.6.0+debian
TTS model: ampixa/real-nepali-v0.2-kala, speaker kala
ASR model: voidash/nepali-asr-staging FastConformer .nemo
Sample text/audio: "नागरिकता बनाउन कुन जिल्ला र वडा हो पहिले भन्नुहोस्।"

TTS worker:
  cold first call including model download/load: 111.314s
  warm call 2: 1.111s server-side
  warm call 3: 1.440s server-side
  worker RSS after calls: ~2.1 GB

ASR worker:
  offline CLI cold restore + transcription: 30.660s
  worker cold first request including model load: 12.185s
  warm request 2: 2.857s server-side
  warm request 3: 3.012s server-side
  worker RSS after calls: ~1.06 GB

ASR transcript on TTS-generated test audio:
  नागरिकता बनाउन कुन् जिल्ला रवडाउ पहिले भनुोस् ⁇
```

Careful wording:

> The voice models are small enough for local warm workers on office hardware.
> We also proved TTS and ASR can run on the Raspberry Pi 5 as edge components:
> TTS warm responses in about 1.1-1.4s and ASR warm transcription in about
> 2.9-3.0s for a short Nepali WAV. The full production kiosk should still be
> framed as an office-computer stack; the Pi is the low-cost local edge lane,
> not the whole national RAG server.

## Shot List

1. Physical Pi on desk beside monitor.
2. Terminal:
   ```bash
   ssh cdjk@<pi-tailnet-ip>
   cat /proc/device-tree/model
   free -h
   ls -lh ~/speakgov-pi/models/*.gguf
   ```
3. Show process:
   ```bash
   ps -p $(cat ~/speakgov-pi/llama-server.pid) -o pid,etime,%cpu,%mem,rss,command
   ```
4. Show health:
   ```bash
   curl http://<pi-tailnet-ip>:8081/health
   ```
5. Show live smoke:
   ```bash
   BASE_URL=http://<pi-tailnet-ip>:8081 bash scripts/pi_llamacpp_smoke.sh
   ```
6. Show voice component benchmark files:
   ```bash
   ssh cdjk@<pi-tailnet-ip>
   ls -lh ~/speakgov-voice-pi/benchmarks
   cat ~/speakgov-voice-pi/benchmarks/asr_worker_call_2.txt
   cat ~/speakgov-voice-pi/benchmarks/tts_headers_2.txt
   ```
7. Cut from Pi terminal to kiosk UI to make the distinction clear:
   Pi = edge model proof; kiosk = full voice/RAG experience.

## Narration Insert

> This is where Gemma matters technically. The main demo uses a stronger office
> computer for the full RAG and voice pipeline. But the same open E2B-class model
> also runs locally on a Raspberry Pi 5. The model file is about 3.5 GB, the
> server uses around 5 GB of RAM, and short service-navigation answers generate
> at roughly 6 to 8 tokens per second.

> That means an office does not need an L40 GPU to have a local intake layer.
> The Pi can ask the first questions, speak Nepali replies with our TTS worker,
> transcribe short Nepali audio with our FastConformer ASR worker, and keep
> working as an edge fallback. For the full experience, ASR, TTS, RAG, WhatsApp,
> and kiosk can run on a modest onsite office computer.

## One-Line Caption

```text
Gemma E2B on Pi 5: 6-8 tok/s, Nepali TTS warm 1.1-1.4s, ASR warm 2.9-3.0s
```
