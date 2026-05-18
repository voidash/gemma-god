#!/usr/bin/env bash
set -Eeuo pipefail

REPO_ID="${REPO_ID:-voidash/gemma-helpdesk-v4b-e2b-seed42}"
OUT_DIR="${OUT_DIR:-/home/ubuntu/eval/reports/sft_v4b_decode_sweep}"
LOG_FILE="${LOG_FILE:-/home/ubuntu/logs/sweep_v4b_decode.log}"
SHUTDOWN_DELAY_MIN="${SHUTDOWN_DELAY_MIN:-240}"

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
    hf upload "$REPO_ID" "$OUT_DIR" "eval/reports/$(basename "$OUT_DIR")" \
      "${hf_args[@]}" \
      --commit-message "Add v4b checkpoint decode sweep" >>"$LOG_FILE" 2>&1
  fi
  if [[ -f "$LOG_FILE" ]]; then
    hf upload "$REPO_ID" "$LOG_FILE" "logs/$(basename "$LOG_FILE")" \
      "${hf_args[@]}" \
      --commit-message "Add v4b checkpoint decode sweep log" >>"$LOG_FILE" 2>&1
  fi
  if [[ -f "$0" ]]; then
    hf upload "$REPO_ID" "$0" "logs/run_v4b_sweep.sh" \
      "${hf_args[@]}" \
      --commit-message "Add v4b sweep runner" >>"$LOG_FILE" 2>&1
  fi
}

finish() {
  local code=$?
  set +e +u
  echo "[v4b-sweep] finished with exit code ${code}; uploading artifacts, then stopping instance" | tee -a "$LOG_FILE"
  upload_artifacts
  sync
  sudo shutdown -h now
  exit "$code"
}
trap finish EXIT

mkdir -p "$(dirname "$LOG_FILE")"
rm -rf "$OUT_DIR"
mkdir -p "$OUT_DIR"
: >"$LOG_FILE"

sudo shutdown -c >/dev/null 2>&1 || true
sudo shutdown -h "+${SHUTDOWN_DELAY_MIN}" "v4b decode sweep hard fallback stop" || true

set -a
source /home/ubuntu/.v4b-env
set +a
source /home/ubuntu/v4-venv/bin/activate

echo "[v4b-sweep] starting $(date -Is)" | tee -a "$LOG_FILE"
echo "[v4b-sweep] repo=${REPO_ID} out=${OUT_DIR}" | tee -a "$LOG_FILE"
nvidia-smi --query-gpu=name,memory.total,memory.used --format=csv,noheader | tee -a "$LOG_FILE"

python /home/ubuntu/scripts/sweep_v4b_decode.py \
  --ckpt-root /home/ubuntu/checkpoints/sft_v4b_e2b_seed42 \
  --gold /home/ubuntu/eval/gov_helpdesk_gold_v1.jsonl \
  --previous-full-gold /home/ubuntu/eval/reports/sft_v4b_e2b_seed42/full_gold.json \
  --out-dir "$OUT_DIR" \
  --checkpoints step200,step400,step600,step800,step1000,step1200,step1400,final,best \
  --presets baseline_300,short_180,short_rep_180,rep_240,short_rep_trim_180 \
  2>&1 | tee -a "$LOG_FILE"
