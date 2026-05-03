#!/usr/bin/env bash
# setup_v4_venv.sh — bootstrap the SFT v4 training environment on a GPU box.
#
# Replaces the ad-hoc shell history that built v3a-venv. Idempotent: re-running
# is safe (won't re-create venv if present, won't re-patch peft if already
# patched).
#
# Usage on AWS g6e.xlarge (L40S):
#     curl -O https://raw.githubusercontent.com/voidash/.../setup_v4_venv.sh
#     bash setup_v4_venv.sh
# OR via scp:
#     scp scripts/setup_v4_venv.sh requirements-train.txt ubuntu@<ip>:/home/ubuntu/
#     ssh ubuntu@<ip> 'bash /home/ubuntu/setup_v4_venv.sh'
#
# The venv ends up at /home/ubuntu/v4-venv (override with VENV_DIR=...).
# Activate: `source /home/ubuntu/v4-venv/bin/activate`
set -euo pipefail

VENV_DIR="${VENV_DIR:-/home/ubuntu/v4-venv}"
REQ_FILE="${REQ_FILE:-/home/ubuntu/requirements-train.txt}"
# CUDA wheel index — matches DLAMI driver. cu130 is right for current g6e.xlarge.
TORCH_INDEX="${TORCH_INDEX:-https://download.pytorch.org/whl/cu130}"

log() { echo -e "\033[1;34m[setup-v4]\033[0m $*" >&2; }
err() { echo -e "\033[1;31m[setup-v4 ERROR]\033[0m $*" >&2; exit 1; }

[ -f "$REQ_FILE" ] || err "missing $REQ_FILE — scp it first"

# ---- 1. venv -------------------------------------------------------------
if [ -d "$VENV_DIR" ]; then
    log "venv exists at $VENV_DIR — skipping create"
else
    log "creating venv at $VENV_DIR"
    python3 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
pip install -q --upgrade pip wheel

# ---- 2. torch (CUDA wheel index) ----------------------------------------
# Install torch FIRST from the cu* index. If we let the requirements pull
# it transitively from PyPI default, we get the CPU wheel and CUDA dies.
# Pin not specified — let pip resolve to whatever cu130 has that satisfies
# transformers/peft. v3a empirically landed on torch 2.11.0+cu130.
if python -c 'import torch; assert torch.cuda.is_available()' >/dev/null 2>&1; then
    log "torch with CUDA already installed: $(python -c 'import torch; print(torch.__version__)')"
else
    log "installing torch + torchvision from $TORCH_INDEX (this is the heavy step)"
    pip install -q torch torchvision --index-url "$TORCH_INDEX"
fi

# ---- 3. requirements -----------------------------------------------------
log "installing pinned training stack from $REQ_FILE"
pip install -q -r "$REQ_FILE"

# ---- 4. peft compat patch -----------------------------------------------
# peft 0.19.1 imports `BloomPreTrainedModel` from transformers, which 5.x
# removed. Patch the import to be optional. After patching, the downstream
# `hasattr(BloomPreTrainedModel, ...)` evaluates False and the Bloom-specific
# code path is skipped — exactly what we want on non-Bloom models.
PEFT_CONST="$VENV_DIR/lib/python3.10/site-packages/peft/utils/constants.py"
if [ ! -f "$PEFT_CONST" ]; then
    # Find the right python version dir
    PEFT_CONST=$(find "$VENV_DIR/lib" -path "*/peft/utils/constants.py" | head -1)
fi
[ -f "$PEFT_CONST" ] || err "couldn't locate peft constants.py under $VENV_DIR/lib"

if grep -q "except (ImportError, ModuleNotFoundError):" "$PEFT_CONST"; then
    log "peft constants.py already patched"
else
    log "patching peft constants.py: BloomPreTrainedModel import → optional"
    python - <<PY
import sys
p = "$PEFT_CONST"
src = open(p).read()
old = 'from transformers import BloomPreTrainedModel'
new = '''try:
    from transformers import BloomPreTrainedModel
except (ImportError, ModuleNotFoundError):
    BloomPreTrainedModel = None'''
if old not in src:
    print(f"WARN: target line not in {p} — peft API may have changed", file=sys.stderr)
    sys.exit(0)  # don't fail; try without the patch
open(p, "w").write(src.replace(old, new))
print("patched OK")
PY
fi

# ---- 5. hf CLI -----------------------------------------------------------
# Provided by huggingface_hub[cli]; ensure binary is on PATH.
if ! command -v hf >/dev/null 2>&1; then
    log "installing hf CLI"
    pip install -q 'huggingface_hub[cli]'
fi

# ---- 6. smoke test -------------------------------------------------------
log "smoke test: imports + CUDA"
python - <<'PY'
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import LoraConfig, get_peft_model
import bitsandbytes as bnb
import accelerate
print(f"  torch        {torch.__version__}  cuda={torch.cuda.is_available()}  device={torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'}")
print(f"  transformers {__import__('transformers').__version__}")
print(f"  peft         {__import__('peft').__version__}")
print(f"  accelerate   {accelerate.__version__}")
print(f"  bitsandbytes {bnb.__version__}")
PY

log "DONE. Activate with: source $VENV_DIR/bin/activate"
