#!/usr/bin/env python3
"""Warm local FastConformer ASR worker for kiosk/live voice."""

from __future__ import annotations

import os
import tempfile
import threading
import time
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from voice_fastconformer_asr import DEFAULT_MODEL_ID, DEFAULT_NEMO_FILE, _ensure_wav, _patch_legacy_nemo_config


MODEL_ID = os.environ.get("VOICE_ASR_MODEL_ID", DEFAULT_MODEL_ID)
NEMO_FILE = os.environ.get("VOICE_ASR_NEMO_FILE", DEFAULT_NEMO_FILE)

app = FastAPI(title="SpeakGov local ASR worker")
LOG = logging.getLogger("speakgov.asr_worker")

_model: Any | None = None
_model_lock = threading.Lock()


class AsrHealth(BaseModel):
    status: str
    provider: str
    model_id: str
    nemo_file: str
    loaded: bool


def _load_model() -> Any:
    global _model
    if _model is not None:
        return _model

    with _model_lock:
        if _model is not None:
            return _model

        from huggingface_hub import hf_hub_download
        from nemo.collections.asr.models import EncDecCTCModelBPE

        local_nemo = hf_hub_download(
            repo_id=MODEL_ID,
            repo_type="dataset",
            filename=NEMO_FILE,
            token=os.environ.get("HF_TOKEN"),
        )
        cfg = EncDecCTCModelBPE.restore_from(local_nemo, return_config=True)
        cfg = _patch_legacy_nemo_config(cfg)
        model = EncDecCTCModelBPE.restore_from(
            local_nemo,
            override_config_path=cfg,
            map_location="cpu",
        )
        model.eval()
        model.freeze()
        _model = model
        return _model


@app.get("/health", response_model=AsrHealth)
def health() -> AsrHealth:
    return AsrHealth(
        status="ok",
        provider="fastconformer-worker",
        model_id=MODEL_ID,
        nemo_file=NEMO_FILE,
        loaded=_model is not None,
    )


@app.post("/transcribe")
async def transcribe(audio: UploadFile = File(...)) -> dict[str, Any]:
    content = await audio.read()
    if not content:
        raise HTTPException(400, "empty audio")

    started = time.time()
    suffix = Path(audio.filename or "audio.webm").suffix or ".webm"
    with tempfile.TemporaryDirectory(prefix="speakgov-asr-worker-") as tmp:
        audio_path = Path(tmp) / f"audio{suffix}"
        audio_path.write_bytes(content)
        try:
            wav_path = _ensure_wav(audio_path)
            try:
                model = _load_model()
                with _model_lock:
                    result = model.transcribe([str(wav_path)], batch_size=1)
            finally:
                wav_path.unlink(missing_ok=True)
        except Exception as exc:
            LOG.exception("asr worker failed for filename=%s bytes=%s", audio.filename, len(content))
            raise HTTPException(502, f"asr worker failed: {str(exc)[:300]}") from exc

    if isinstance(result, tuple):
        result = result[0]
    if result and not isinstance(result[0], str) and hasattr(result[0], "text"):
        transcript = str(result[0].text)
    else:
        transcript = str(result[0]) if result else ""

    elapsed_ms = int((time.time() - started) * 1000)
    return {
        "transcript": transcript.strip(),
        "provider": "fastconformer-worker",
        "model_id": MODEL_ID,
        "nemo_file": NEMO_FILE,
        "latency_ms": elapsed_ms,
        "bytes": len(content),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "voice_asr_worker:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8789")),
        log_level=os.environ.get("LOG_LEVEL", "info"),
    )
