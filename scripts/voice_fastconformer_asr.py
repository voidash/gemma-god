#!/usr/bin/env python3
"""Transcribe one audio file with the SpeakGov Nepali FastConformer ASR.

Two execution modes are supported:

1. HF Space mode (`--space-url`) for the hackathon demo. This calls the
   deployed `voidash/nepali-fastconformer-demo` Gradio app, which runs the same
   private NeMo artifact.
2. Local mode, which downloads the `.nemo` artifact from
   `voidash/nepali-asr-staging` and runs NeMo directly. This requires
   `nemo_toolkit[asr]`, `librosa`, `soundfile`, `torch`, and an `HF_TOKEN` with
   dataset read access.
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import tempfile
from pathlib import Path
from typing import Any


DEFAULT_MODEL_ID = "voidash/nepali-asr-staging"
DEFAULT_NEMO_FILE = (
    "training-artifacts/fastconformer/hi_ctc_medium_slr54init_mixed491h_e10/"
    "checkpoints/ne-fastconformer-hybrid-bpe-v256-stt-hi-ctc-medium-"
    "slr54init-mixed491h-e10-lr5e5.nemo"
)


def _write_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def _transcribe_via_space(audio_path: Path, space_url: str, api_name: str, timeout: float) -> str:
    try:
        from gradio_client import Client, handle_file
    except Exception as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("gradio_client is required for HF Space ASR mode") from exc

    client_kwargs: dict[str, Any] = {"httpx_kwargs": {"timeout": timeout}, "verbose": False}
    token = os.environ.get("HF_TOKEN") or None
    if token:
        token_arg = "hf_token" if "hf_token" in inspect.signature(Client).parameters else "token"
        client_kwargs[token_arg] = token
    client = Client(space_url, **client_kwargs)
    result = client.predict(handle_file(str(audio_path)), api_name=api_name)
    if isinstance(result, str):
        if result.startswith("Error:"):
            raise RuntimeError(result)
        return result
    if isinstance(result, (list, tuple)) and result:
        first = result[0]
        if isinstance(first, str):
            return first
    return str(result or "")


def _patch_legacy_nemo_config(cfg: Any) -> Any:
    from omegaconf import OmegaConf

    OmegaConf.set_struct(cfg, False)
    decoding = cfg.get("decoding")
    if decoding is None:
        return cfg

    for section_name in ("greedy", "beam", "wfst"):
        section = decoding.get(section_name)
        if section is None:
            continue
        boosting_tree = section.get("boosting_tree")
        if boosting_tree is None:
            continue
        if "key_phrase_items_list" not in boosting_tree:
            boosting_tree.key_phrase_items_list = None
    return cfg


def _ensure_wav(audio_path: Path) -> Path:
    import librosa
    import soundfile as sf

    data, sr = librosa.load(str(audio_path), sr=16000, mono=True)
    out = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    out.close()
    sf.write(out.name, data, sr, subtype="PCM_16")
    return Path(out.name)


def _transcribe_local(audio_path: Path, model_id: str, nemo_file: str) -> str:
    import torch
    from huggingface_hub import hf_hub_download
    from nemo.collections.asr.models import EncDecCTCModelBPE

    token = os.environ.get("HF_TOKEN")
    local_nemo = hf_hub_download(
        repo_id=model_id,
        repo_type="dataset",
        filename=nemo_file,
        token=token,
    )
    device = "cuda" if torch.cuda.is_available() else "cpu"
    cfg = EncDecCTCModelBPE.restore_from(local_nemo, return_config=True)
    cfg = _patch_legacy_nemo_config(cfg)
    model = EncDecCTCModelBPE.restore_from(
        local_nemo,
        override_config_path=cfg,
        map_location=device,
    )
    model.eval()
    model.freeze()
    model = model.to(device)

    wav_path = _ensure_wav(audio_path)
    try:
        result = model.transcribe([str(wav_path)], batch_size=1)
    finally:
        wav_path.unlink(missing_ok=True)
    if isinstance(result, tuple):
        result = result[0]
    if result and not isinstance(result[0], str) and hasattr(result[0], "text"):
        return str(result[0].text)
    return str(result[0]) if result else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True)
    ap.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    ap.add_argument("--nemo-file", default=DEFAULT_NEMO_FILE)
    ap.add_argument("--space-url", default="")
    ap.add_argument("--api-name", default="/transcribe")
    ap.add_argument("--timeout", type=float, default=240.0)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    audio_path = Path(args.audio)
    if not audio_path.exists():
        raise FileNotFoundError(audio_path)

    if args.space_url:
        transcript = _transcribe_via_space(audio_path, args.space_url, args.api_name, args.timeout)
        provider = "fastconformer-space"
    else:
        transcript = _transcribe_local(audio_path, args.model_id, args.nemo_file)
        provider = "fastconformer-local"

    payload = {
        "transcript": transcript.strip(),
        "provider": provider,
        "model_id": args.model_id,
        "nemo_file": args.nemo_file,
    }
    if args.json:
        _write_json(payload)
    else:
        print(payload["transcript"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
