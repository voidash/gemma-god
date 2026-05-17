#!/usr/bin/env python3
"""Warm local Real Nepali TTS worker for kiosk/live voice.

This keeps the Piper/VITS checkpoint loaded in one process. It is intentionally
separate from the main FastAPI app because the production app currently runs in
the general Python environment, while local TTS needs a Python 3.10/3.11 voice
environment with piper-plus and nepali-text-frontend installed.
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from voice_real_nepali_tts import DEFAULT_MODEL_REPO, DEFAULT_SPEAKER, SAMPLE_RATE, _synthesize_local


MODEL_REPO = os.environ.get("VOICE_TTS_MODEL_REPO", DEFAULT_MODEL_REPO)
DEFAULT_WORKER_SPEAKER = os.environ.get("VOICE_TTS_SPEAKER", DEFAULT_SPEAKER)
MAX_CHARS = int(os.environ.get("VOICE_TTS_MAX_CHARS", "230"))

app = FastAPI(title="SpeakGov local TTS worker")


class TtsRequest(BaseModel):
    text: str
    speaker: str | None = None
    length_scale: float = Field(default=1.0, ge=0.5, le=2.0)
    noise_scale: float = Field(default=0.667, ge=0.0, le=2.0)
    noise_scale_w: float = Field(default=0.8, ge=0.0, le=2.0)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "provider": "real-nepali-worker",
        "model_repo": MODEL_REPO,
        "speaker": DEFAULT_WORKER_SPEAKER,
        "sample_rate": SAMPLE_RATE,
    }


@app.post("/synthesize")
def synthesize(req: TtsRequest):
    text = " ".join(req.text.split())
    if not text:
        raise HTTPException(400, "empty text")
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS].rsplit(" ", 1)[0].strip() or text[:MAX_CHARS]

    speaker = req.speaker or DEFAULT_WORKER_SPEAKER
    started = time.time()
    with tempfile.TemporaryDirectory(prefix="speakgov-tts-worker-") as tmp:
        output = Path(tmp) / "speech.wav"
        try:
            _synthesize_local(
                text,
                output,
                MODEL_REPO,
                speaker,
                req.length_scale,
                req.noise_scale,
                req.noise_scale_w,
            )
        except Exception as exc:
            raise HTTPException(502, f"tts worker failed: {str(exc)[:300]}") from exc
        audio = output.read_bytes()

    elapsed_ms = int((time.time() - started) * 1000)
    return Response(
        content=audio,
        media_type="audio/wav",
        headers={
            "X-Voice-Provider": "real-nepali-worker",
            "X-Voice-Model": MODEL_REPO,
            "X-Voice-Speaker": speaker,
            "X-Voice-Sample-Rate": str(SAMPLE_RATE),
            "X-Voice-Latency-Ms": str(elapsed_ms),
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "voice_tts_worker:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8788")),
        log_level=os.environ.get("LOG_LEVEL", "info"),
    )
