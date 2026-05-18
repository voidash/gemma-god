# PreVillage Pi Inference Capture Shot Plan

Tmux session:

```bash
bash video_pi_recording/start_pi_inference_capture_tmux.sh previllage-pi-inference
tmux attach -t previllage-pi-inference
```

## Recording Order

1. Physical Pi shot, 2-3 seconds.
   Show the Raspberry Pi on the desk, connected to power/network. This anchors
   the edge-compute claim visually.

2. Window `1-gemma-live`.
   Record the terminal output showing:
   - Raspberry Pi 5 hardware
   - `google_gemma-4-E2B-it-Q4_K_M.gguf`
   - llama.cpp server health
   - live Gemma service-intake response
   - llama.cpp timing around 6-8 generated tok/s

3. Window `2-tts-shot`.
   Press Enter while recording. This temporarily stops llama.cpp to free RAM,
   starts the Nepali TTS worker, synthesizes a short Nepali service prompt, and
   shows the `X-Voice-Latency-Ms` headers plus WAV output files.

4. Window `3-asr-shot`.
   Press Enter while recording. It starts the FastConformer ASR worker, sends
   the TTS-generated WAV, and shows latency plus transcript. The small transcript
   errors are useful because they justify the Gemma fixer/intake step.

5. Window `4-restore`.
   Press Enter after the ASR shot. It stops voice workers, restores the Gemma
   llama.cpp server, and runs the final smoke test.

## Narration Line

```text
This is the technical point: an office does not need an L40 GPU for the first
line of service help. On a Raspberry Pi 5, Gemma E2B runs locally at about
6-8 tokens per second. The same edge box can also speak Nepali with our TTS
worker and transcribe short Nepali audio with our ASR worker. The full kiosk,
WhatsApp, and national RAG loop still belong on an onsite office computer, but
the fallback intake layer can live right here.
```

## Safe Caption

```text
Pi 5 edge proof: Gemma E2B local inference, Nepali TTS, Nepali ASR
```

## Do Not Say

```text
The Raspberry Pi runs the whole national RAG, WhatsApp bridge, ASR, TTS, and
Gemma stack concurrently.
```

Correct version:

```text
Pi = local edge proof and fallback intake.
Office computer = full RAG, WhatsApp, kiosk, ASR/TTS, admin loop.
```
