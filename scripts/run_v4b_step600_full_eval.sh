#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ID="${REPO_ID:-voidash/gemma-helpdesk-v4b-e2b-seed42}"
LABEL="${LABEL:-sft_v4b_step600_baseline300_full_eval}"
OUT_ROOT="${OUT_ROOT:-/home/ubuntu/eval/reports}"
OUT_DIR="${OUT_ROOT}/${LABEL}"
LOG_FILE="${LOG_FILE:-/home/ubuntu/logs/eval_v4b_step600_baseline300.log}"
SHUTDOWN_DELAY_MIN="${SHUTDOWN_DELAY_MIN:-360}"

upload_artifacts() {
  set +e +u
  source /home/ubuntu/v4-venv/bin/activate >/dev/null 2>&1 || true
  if [[ -f /home/ubuntu/.v4b-env ]]; then
    set -a
    source /home/ubuntu/.v4b-env >/dev/null 2>&1
    set +a
  fi

  local hf_args=(--repo-type model)
  if [[ -n "${HF_TOKEN:-}" ]]; then
    hf_args+=(--token "$HF_TOKEN")
  fi

  if [[ -d "$OUT_DIR" ]]; then
    hf upload "$REPO_ID" "$OUT_DIR" "eval/reports/${LABEL}" \
      "${hf_args[@]}" \
      --commit-message "Add v4b step600 baseline300 full eval" >>"$LOG_FILE" 2>&1
  fi
  if [[ -f "$LOG_FILE" ]]; then
    hf upload "$REPO_ID" "$LOG_FILE" "logs/$(basename "$LOG_FILE")" \
      "${hf_args[@]}" \
      --commit-message "Add v4b step600 baseline300 eval log" >>"$LOG_FILE" 2>&1
  fi
  if [[ -f "$0" ]]; then
    hf upload "$REPO_ID" "$0" "logs/run_v4b_step600_full_eval.sh" \
      "${hf_args[@]}" \
      --commit-message "Add v4b step600 eval runner" >>"$LOG_FILE" 2>&1
  fi
}

finish() {
  local code=$?
  set +e +u
  echo "[v4b-full-eval] finished with exit code ${code}; uploading artifacts, then stopping instance" | tee -a "$LOG_FILE"
  upload_artifacts
  sync
  sudo shutdown -h now
  exit "$code"
}
trap finish EXIT

mkdir -p "$(dirname "$LOG_FILE")" "$OUT_ROOT"
rm -rf "$OUT_DIR"
: >"$LOG_FILE"

sudo shutdown -c >/dev/null 2>&1 || true
sudo shutdown -h "+${SHUTDOWN_DELAY_MIN}" "v4b step600 full eval hard fallback stop" || true

set -a
source /home/ubuntu/.v4b-env
set +a
source /home/ubuntu/v4-venv/bin/activate

echo "[v4b-full-eval] starting $(date -Is)" | tee -a "$LOG_FILE"
echo "[v4b-full-eval] repo=${REPO_ID} label=${LABEL}" | tee -a "$LOG_FILE"
nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv,noheader | tee -a "$LOG_FILE"

python /home/ubuntu/scripts/eval_sft_v1.py \
  --base google/gemma-4-E2B-it \
  --adapter /home/ubuntu/checkpoints/sft_v4b_e2b_seed42/step600 \
  --label "$LABEL" \
  --out-root "$OUT_ROOT" \
  --gold /home/ubuntu/eval/gov_helpdesk_gold_v1.jsonl \
  --batch-size 4 \
  --max-new-tokens 300 \
  --judge-n 50 \
  --belebele-n 50 \
  --gsm8k-n 30 \
  --side-by-side-n 10 \
  --seed 42 \
  2>&1 | tee -a "$LOG_FILE"
