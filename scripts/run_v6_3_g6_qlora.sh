#!/usr/bin/env bash
set -euo pipefail

cd /home/ubuntu

if [ -f /opt/pytorch/bin/activate ]; then
  # shellcheck disable=SC1091
  source /opt/pytorch/bin/activate
elif [ -f /opt/conda/etc/profile.d/conda.sh ]; then
  # shellcheck disable=SC1091
  source /opt/conda/etc/profile.d/conda.sh
  conda activate pytorch || true
fi

if [ -f /home/ubuntu/.fmw ]; then
  set -a
  # shellcheck disable=SC1091
  source /home/ubuntu/.fmw
  set +a
fi

export HF_TOKEN="${HF_TOKEN:?missing HF_TOKEN}"
export DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-${DEEPSEEK:-}}"
export PYTORCH_CUDA_ALLOC_CONF="${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}"

RUN_LABEL="sft_v6_3_e4b_g6_qlora_r16_seed42"
CKPT_REPO="voidash/gemma-helpdesk-v6-3-e4b-g6-qlora-r16-seed42"
BASE_MODEL="google/gemma-4-E4B-it"

cleanup() {
  rc=$?
  set +e
  hf upload --repo-type model --token "$HF_TOKEN" "$CKPT_REPO" "/home/ubuntu/checkpoints/$RUN_LABEL" ckpt
  hf upload --repo-type model --token "$HF_TOKEN" "$CKPT_REPO" /home/ubuntu/eval/reports eval
  hf upload --repo-type model --token "$HF_TOKEN" "$CKPT_REPO" /home/ubuntu/train_v6_3_g6_qlora.log train_v6_3_g6_qlora.log
  hf upload --repo-type model --token "$HF_TOKEN" "$CKPT_REPO" /home/ubuntu/eval_v6_3_g6_qlora.log eval_v6_3_g6_qlora.log
  echo "=== exit rc=$rc $(date -u +%FT%TZ) ===" | tee -a /home/ubuntu/done_v6_3_g6_qlora.log
  sudo shutdown -h now
  exit "$rc"
}
trap cleanup EXIT

mkdir -p /home/ubuntu/data /home/ubuntu/scripts /home/ubuntu/checkpoints /home/ubuntu/eval/reports

python -m pip install -U --quiet \
  "transformers>=4.50" \
  "peft>=0.13" \
  "accelerate>=1.0" \
  "datasets>=3.0" \
  "huggingface_hub>=0.26" \
  "bitsandbytes>=0.44" \
  "sacrebleu" \
  "sentencepiece"

hf download --repo-type dataset --local-dir /home/ubuntu/data --token "$HF_TOKEN" \
  voidash/gemma-helpdesk-data sft_v6_3_train.jsonl sft_v6_3_val.jsonl gov_helpdesk_gold_v1.jsonl

hf download --local-dir /home/ubuntu/scripts --token "$HF_TOKEN" \
  voidash/gemma-helpdesk-scripts train_sft_v1.py eval_sft_v1.py eval_groundedness.py format_sft_v2.py format_sft_v1.py

hf repo create --repo-type model --private --exist-ok "$CKPT_REPO" --token "$HF_TOKEN" >/dev/null 2>&1 || true

{
  echo "=== train start $(date -u +%FT%TZ) ==="
  python scripts/train_sft_v1.py \
    --train data/sft_v6_3_train.jsonl \
    --val data/sft_v6_3_val.jsonl \
    --model-id "$BASE_MODEL" \
    --output "/home/ubuntu/checkpoints/$RUN_LABEL" \
    --seed 42 \
    --hf-repo "$CKPT_REPO" \
    --max-wall-hours 3.0 \
    --epochs 6 \
    --per-device-batch 1 \
    --grad-accum 4 \
    --warmup-steps 10 \
    --eval-every-steps 30 \
    --save-every-steps 60 \
    --push-every-steps 60 \
    --lora-rank 16 \
    --lora-alpha 32 \
    --max-seq-length 2048 \
    --load-in-4bit
  echo "=== train done $(date -u +%FT%TZ) ==="
} 2>&1 | tee -a /home/ubuntu/train_v6_3_g6_qlora.log

ADAPTER_DIR="/home/ubuntu/checkpoints/$RUN_LABEL/best"
{
  echo "=== eval start $(date -u +%FT%TZ) ==="
  python scripts/eval_sft_v1.py \
    --base "$BASE_MODEL" \
    --adapter "$ADAPTER_DIR" \
    --label "${RUN_LABEL}_quick48" \
    --gold data/gov_helpdesk_gold_v1.jsonl \
    --out-root eval/reports \
    --load-in-4bit \
    --batch-size 1 \
    --limit 48 \
    --judge-n 12 \
    --max-new-tokens 220 \
    --skip belebele,gsm8k,side_by_side
  echo "=== eval done $(date -u +%FT%TZ) ==="
} 2>&1 | tee -a /home/ubuntu/eval_v6_3_g6_qlora.log

echo "=== all done $(date -u +%FT%TZ) ===" | tee -a /home/ubuntu/done_v6_3_g6_qlora.log
