#!/usr/bin/env bash
set -euo pipefail

ROOT="${PI_ROOT:-$HOME/speakgov-pi}"
LLAMA_CPP_DIR="${LLAMA_CPP_DIR:-$ROOT/llama.cpp}"
BUILD_DIR="$LLAMA_CPP_DIR/build"
HF_VENV="${HF_VENV:-$ROOT/hf-venv}"

mkdir -p "$ROOT"

if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y \
    build-essential \
    cmake \
    curl \
    git \
    libcurl4-openssl-dev \
    python3 \
    python3-pip \
    python3-venv
fi

if [[ ! -d "$LLAMA_CPP_DIR/.git" ]]; then
  git clone https://github.com/ggml-org/llama.cpp "$LLAMA_CPP_DIR"
else
  git -C "$LLAMA_CPP_DIR" pull --ff-only
fi

cmake -S "$LLAMA_CPP_DIR" -B "$BUILD_DIR" \
  -DCMAKE_BUILD_TYPE=Release \
  -DGGML_NATIVE=ON \
  -DLLAMA_CURL=ON \
  -DLLAMA_BUILD_TESTS=OFF \
  -DLLAMA_BUILD_TOOLS=ON \
  -DLLAMA_BUILD_EXAMPLES=ON \
  -DLLAMA_BUILD_SERVER=ON \
  -DLLAMA_BUILD_UI=OFF \
  -DLLAMA_BUILD_WEBUI=OFF
cmake --build "$BUILD_DIR" --config Release --target llama-server -j"$(nproc)"

if [[ ! -x "$HF_VENV/bin/hf" ]]; then
  python3 -m venv "$HF_VENV"
  "$HF_VENV/bin/pip" install -U pip "huggingface_hub[cli]"
fi

echo "llama.cpp ready:"
"$BUILD_DIR/bin/llama-server" --version || true
