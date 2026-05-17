#!/usr/bin/env python3
"""Synthesize one WAV file with the Real Nepali Piper/VITS checkpoint.

HF Space mode (`--space-url`) is the practical demo path. Local mode mirrors
`ampixa/real-nepali-tts/app.py` and requires the Piper-plus training stack plus
the Nepali frontend package.
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import pathlib
import shutil
import sys
import threading
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_MODEL_REPO = "ampixa/real-nepali-v0.2-kala"
DEFAULT_SPEAKER = "kala"
SAMPLE_RATE = 22050
FRONTEND_DATA_ENV = "VOICE_TTS_FRONTEND_DATA_DIR"

PAD = "_"
BOS = "^"
EOS = "$"
BLANK = "#"

PROJECT_PHONES_ORDERED: list[str] = [
    "i", "e", "ax", "aa", "o", "u",
    "in", "en", "axn", "aan", "un",
    "axj", "axw", "aaj", "aaw", "oj", "ew", "ow",
    "axjn", "axwn", "aajn", "aawn", "ojn", "own",
    "p", "ph", "b", "bh",
    "t", "th", "d", "dh",
    "tx", "txh", "dx", "dxh",
    "k", "kh", "g", "gh",
    "ts", "tsh", "dz", "dzh",
    "m", "n", "ng",
    "r", "s", "h", "l", "y", "w",
    "sh", "sx", "ny", "nx",
    "f", "z",
    "p:", "ph:", "b:", "bh:",
    "t:", "th:", "d:", "dh:",
    "tx:", "txh:", "dx:", "dxh:",
    "k:", "kh:", "g:", "gh:",
    "ts:", "tsh:", "dz:", "dzh:",
    "m:", "n:", "ng:",
    "r:", "s:", "h:", "l:", "y:", "w:",
    "sh:", "sx:", "ny:", "nx:",
    "f:", "z:",
    "ch", "chh", "j", "jh",
    "ch:", "chh:", "j:", "jh:",
]

WARMSTART_BASE_IDS: dict[str, int] = {
    "i": 11,
    "e": 13,
    "aa": 10,
    "o": 14,
    "u": 12,
    "p": 42,
    "b": 44,
    "t": 38,
    "d": 40,
    "k": 32,
    "g": 35,
    "m": 59,
    "n": 57,
    "ng": 25,
    "r": 61,
    "s": 48,
    "h": 54,
    "l": 77,
    "y": 51,
    "w": 63,
    "f": 53,
    "z": 50,
}


def build_phoneme_id_map_warmstart() -> dict[str, list[int]]:
    mapping: dict[str, list[int]] = {
        PAD: [0],
        BOS: [1],
        EOS: [2],
        BLANK: [3],
    }
    used_ids = {0, 1, 2, 3}
    for phone, base_id in WARMSTART_BASE_IDS.items():
        mapping[phone] = [base_id]
        used_ids.add(base_id)

    free_ids = [i for i in range(4, 173) if i not in used_ids]
    cold_phones = [p for p in PROJECT_PHONES_ORDERED if p not in WARMSTART_BASE_IDS]
    if len(cold_phones) > len(free_ids):
        raise RuntimeError("not enough free Piper symbol IDs")
    for phone, free_id in zip(cold_phones, free_ids):
        mapping[phone] = [free_id]
    return mapping


def phones_to_ids(phones: list[str], id_map: dict[str, list[int]]) -> list[int]:
    ids = [id_map[BOS][0]]
    for phone in phones:
        if phone in {".", "|"}:
            continue
        if phone not in id_map:
            raise ValueError(f"unsupported phone emitted by G2P: {phone}")
        ids.extend(id_map[phone])
    ids.append(id_map[EOS][0])
    return ids


def _write_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def _read_text(args: argparse.Namespace) -> str:
    if args.text:
        return " ".join(args.text.split())
    if args.text_file:
        return " ".join(Path(args.text_file).read_text(encoding="utf-8").split())
    raise ValueError("provide --text or --text-file")


def _copy_gradio_audio(result: Any, output: Path) -> str:
    audio = result[0] if isinstance(result, (tuple, list)) and result else result
    if isinstance(audio, dict):
        audio = audio.get("path") or audio.get("name")
    if isinstance(audio, (tuple, list)) and len(audio) == 2:
        import numpy as np
        import soundfile as sf

        sr, data = audio
        sf.write(str(output), np.asarray(data), int(sr))
        return ""
    if not audio:
        raise RuntimeError(f"HF Space returned no audio: {result!r}")
    shutil.copyfile(str(audio), output)
    if isinstance(result, (tuple, list)) and len(result) > 1:
        return str(result[1])
    return ""


def _synthesize_via_space(
    text: str,
    output: Path,
    space_url: str,
    api_name: str,
    speaker: str,
    length_scale: float,
    noise_scale: float,
    noise_scale_w: float,
    timeout: float,
) -> str:
    try:
        from gradio_client import Client
    except Exception as exc:  # pragma: no cover - dependency guard
        raise RuntimeError("gradio_client is required for HF Space TTS mode") from exc

    client_kwargs: dict[str, Any] = {"httpx_kwargs": {"timeout": timeout}, "verbose": False}
    token = os.environ.get("HF_TOKEN") or None
    if token:
        token_arg = "hf_token" if "hf_token" in inspect.signature(Client).parameters else "token"
        client_kwargs[token_arg] = token
    client = Client(space_url, **client_kwargs)
    result = client.predict(text, speaker, length_scale, noise_scale, noise_scale_w, api_name=api_name)
    return _copy_gradio_audio(result, output)


@dataclass
class LoadedModel:
    model: object
    device: object
    speaker_id_map: dict[str, int]
    id_map: dict[str, list[int]]


_model_state: LoadedModel | None = None
_model_lock = threading.Lock()


def _install_pathlib_pickle_compat() -> None:
    local_mod = types.ModuleType("pathlib._local")
    for name in (
        "Path",
        "PosixPath",
        "WindowsPath",
        "PurePath",
        "PurePosixPath",
        "PureWindowsPath",
    ):
        setattr(local_mod, name, getattr(pathlib, name))
    sys.modules.setdefault("pathlib._local", local_mod)


def _load_local_model(model_repo: str) -> LoadedModel:
    global _model_state
    if _model_state is not None:
        return _model_state

    with _model_lock:
        if _model_state is not None:
            return _model_state

        import torch
        from huggingface_hub import hf_hub_download
        from piper_train.vits.lightning import VitsModel

        _install_pathlib_pickle_compat()
        checkpoint = Path(hf_hub_download(repo_id=model_repo, filename="checkpoint.ckpt"))
        speakers_path = Path(hf_hub_download(repo_id=model_repo, filename="speaker_id_map.json"))
        speaker_id_map = json.loads(speakers_path.read_text(encoding="utf-8"))
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model = VitsModel.load_from_checkpoint(
            str(checkpoint),
            dataset=None,
            map_location=device,
            weights_only=False,
        )
        model.eval()
        model.to(device)
        with torch.no_grad():
            model.model_g.dec.remove_weight_norm()

        _model_state = LoadedModel(
            model=model,
            device=device,
            speaker_id_map={str(k): int(v) for k, v in speaker_id_map.items()},
            id_map=build_phoneme_id_map_warmstart(),
        )
        return _model_state


def _phonemize(text: str, id_map: dict[str, list[int]]) -> tuple[list[int], str]:
    data_dir = os.environ.get(FRONTEND_DATA_ENV, "").strip()
    if data_dir:
        from nepali_frontend import data as frontend_data

        frontend_data.DATA_DIR = Path(data_dir)

    from real_nepali import g2p as real_nepali_g2p

    phones: list[str] = []
    for word in real_nepali_g2p.phonemize_text(text):
        if not word.phones:
            continue
        phones.extend(word.phones)
        phones.append("|")
    if phones and phones[-1] == "|":
        phones.pop()
    return phones_to_ids(phones, id_map), " ".join(phones)


def _synthesize_local(
    text: str,
    output: Path,
    model_repo: str,
    speaker: str,
    length_scale: float,
    noise_scale: float,
    noise_scale_w: float,
) -> str:
    import numpy as np
    import soundfile as sf
    import torch

    state = _load_local_model(model_repo)
    if speaker not in state.speaker_id_map:
        raise ValueError(f"unknown speaker {speaker!r}; available={sorted(state.speaker_id_map)}")

    phone_ids, phone_string = _phonemize(text, state.id_map)
    sid = torch.LongTensor([state.speaker_id_map[speaker]]).to(state.device)
    text_tensor = torch.LongTensor(phone_ids).unsqueeze(0).to(state.device)
    text_lengths = torch.LongTensor([len(phone_ids)]).to(state.device)
    scales = [noise_scale, length_scale, noise_scale_w]

    with _model_lock, torch.no_grad():
        audio = state.model(text_tensor, text_lengths, scales, sid=sid)
        if getattr(state.device, "type", "") == "cuda":
            torch.cuda.synchronize()
    audio_np = audio.detach().cpu().numpy().reshape(-1).astype(np.float32)
    audio_np = np.clip(audio_np, -1.0, 1.0)
    sf.write(str(output), audio_np, SAMPLE_RATE)
    return phone_string


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default="")
    ap.add_argument("--text-file", default="")
    ap.add_argument("--output", required=True)
    ap.add_argument("--model-repo", default=DEFAULT_MODEL_REPO)
    ap.add_argument("--speaker", default=DEFAULT_SPEAKER)
    ap.add_argument("--length-scale", type=float, default=1.0)
    ap.add_argument("--noise-scale", type=float, default=0.667)
    ap.add_argument("--noise-scale-w", type=float, default=0.8)
    ap.add_argument("--space-url", default="")
    ap.add_argument("--api-name", default="/synthesize")
    ap.add_argument("--timeout", type=float, default=240.0)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    text = _read_text(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    if args.space_url:
        phones = _synthesize_via_space(
            text,
            output,
            args.space_url,
            args.api_name,
            args.speaker,
            args.length_scale,
            args.noise_scale,
            args.noise_scale_w,
            args.timeout,
        )
        provider = "real-nepali-space"
    else:
        phones = _synthesize_local(
            text,
            output,
            args.model_repo,
            args.speaker,
            args.length_scale,
            args.noise_scale,
            args.noise_scale_w,
        )
        provider = "real-nepali-local"

    payload = {
        "output": str(output),
        "provider": provider,
        "model_repo": args.model_repo,
        "speaker": args.speaker,
        "sample_rate": SAMPLE_RATE,
        "phones": phones,
    }
    if args.json:
        _write_json(payload)
    else:
        print(str(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
