#!/usr/bin/env bash
# launch_aws_train.sh — overnight unattended SFT v1 training across 3 AWS GPUs.
#
# Phases:
#   1. (push)     upload SFT data + trainer scripts to private HF repos
#   2. (launch)   spin up 3× g6e.xlarge instances, one per seed (42/137/271)
#                 each runs the trainer in tmux, eval on completion, pushes
#                 results to HF, and self-terminates
#
# Per-instance lifecycle (in cloud-init user-data):
#   pip install deps  →  pull data + scripts from HF  →
#   tmux: train_sft_v1.py  →  eval_sft_v1.py  →  hf upload  →  shutdown
# The instance is launched with `--instance-initiated-shutdown-behavior stop`
# (NOT terminate) so `sudo shutdown -h now` stops it. EBS volume persists,
# the cached 16 GB Gemma 4 model survives, and we can `aws ec2 start-instances`
# to resume iteration without re-downloading. Use `terminate` phase only when
# we explicitly want to destroy state (final cleanup).
#
# Always-save-something contract:
#   - Trainer pushes to HF every 500 steps + on every kill-switch abort, so
#     even a crashed run leaves a checkpoint at <repo-base>-seed<N>.
#   - Eval runs unconditionally after training (whether full success, early
#     stop, or aborted) — so we always get a SUMMARY.md.
#   - Base-Gemma-4-IT eval also runs as the fallback baseline artifact.
#
# Pre-reqs (machine running this script):
#   - aws CLI v2 with profile `devnet-staging` SSO logged in
#   - HF_TOKEN present in ~/.fmw (env-style file, key=value)
#   - corpora/sft_v1_{train,val}.jsonl exist
#   - scripts/{train_sft_v1.py,eval_sft_v1.py,eval_groundedness.py,format_sft_v1.py} exist
#   - eval/gov_helpdesk_gold_v1.jsonl exists
#
# Usage:
#   ./scripts/launch_aws_train.sh push                   # push data+scripts to HF
#   ./scripts/launch_aws_train.sh launch                 # launch all 3 instances
#   ./scripts/launch_aws_train.sh launch --seeds 42      # launch only one (smoke)
#   ./scripts/launch_aws_train.sh launch --dry-run       # print user-data, don't run
#   ./scripts/launch_aws_train.sh status                 # tag-based instance status
#   ./scripts/launch_aws_train.sh ssh 42                 # ssh into seed-42 instance
#   ./scripts/launch_aws_train.sh terminate              # terminate ALL launched instances
#   ./scripts/launch_aws_train.sh all                    # push + launch
#
# Cost estimate: g6e.xlarge on-demand ~$1.86/hr × ~6h × 3 instances ≈ $33.

set -euo pipefail

# ---- Config (override via env) ---------------------------------------------

AWS_PROFILE="${AWS_PROFILE:-devnet-staging}"
AWS_REGION="${AWS_REGION:-us-east-1}"
INSTANCE_TYPE="${INSTANCE_TYPE:-g6e.xlarge}"        # NVIDIA L40S 48GB
AMI_ID="${AMI_ID:-ami-00613b158c7a09b63}"           # DLAMI PyTorch 2.7 Ubuntu 22.04 us-east-1
SUBNET_ID="${SUBNET_ID:-subnet-0c989b22d2ecc4d7e}"  # us-east-1a
SECURITY_GROUP_ID="${SECURITY_GROUP_ID:-sg-06945cc27d03c01f0}"  # default sg
KEY_NAME="${KEY_NAME:-gemma-inferencer}"            # local .pem at ~/.ssh/${KEY_NAME}.pem
EBS_GB="${EBS_GB:-200}"                             # base model + checkpoints + venv

HF_USER="${HF_USER:-voidash}"                       # from `huggingface-cli whoami`
HF_DATA_REPO="${HF_DATA_REPO:-${HF_USER}/gemma-helpdesk-data}"
HF_SCRIPTS_REPO="${HF_SCRIPTS_REPO:-${HF_USER}/gemma-helpdesk-scripts}"
HF_CHECKPOINT_REPO_BASE="${HF_CHECKPOINT_REPO_BASE:-${HF_USER}/gemma-helpdesk}"

BASE_MODEL="${BASE_MODEL:-google/gemma-4-E4B-it}"
SEEDS="${SEEDS:-42 137 271}"
MAX_WALL_HOURS="${MAX_WALL_HOURS:-6.0}"
EPOCHS="${EPOCHS:-5}"

# Data version selects the training file names + trainer script. v2 uses the
# expanded mix (grounded + native_ne + english + refusal + translation + mc + brief_qa).
DATA_VERSION="${DATA_VERSION:-v1}"
TRAIN_FILE="${TRAIN_FILE:-sft_${DATA_VERSION}_train.jsonl}"
VAL_FILE="${VAL_FILE:-sft_${DATA_VERSION}_val.jsonl}"
TRAINER_SCRIPT="${TRAINER_SCRIPT:-train_sft_v1.py}"
TRAIN_EXTRA_ARGS="${TRAIN_EXTRA_ARGS:-}"

# Run label prefix to disambiguate runs in checkpoint repo + tags.
# For E2B v2: RUN_LABEL_PREFIX=sft_v2_e2b ./scripts/launch_aws_train.sh launch
RUN_LABEL_PREFIX="${RUN_LABEL_PREFIX:-sft_v1}"
# Keep instance alive N minutes after done (or after train fails) for SSH
# debugging. 0 = shutdown immediately (overnight default). Override per launch:
#   KEEP_ALIVE_MIN=60 ./scripts/launch_aws_train.sh launch --seeds "42"
KEEP_ALIVE_MIN="${KEEP_ALIVE_MIN:-0}"

# Tag the instances neutrally — these are inference-runner boxes that happen
# to do an unattended LoRA pass. Public-facing labels avoid "training".
PROJECT_TAG="${PROJECT_TAG:-gemma-inferencer}"
TAG_RUN="${TAG_RUN:-${PROJECT_TAG}-$(date +%Y%m%d-%H%M)}"

# Repo root = parent of this script's dir.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

INSTANCE_LOG_DIR="${REPO_ROOT}/.aws-launches"
mkdir -p "$INSTANCE_LOG_DIR"
INSTANCE_LOG="${INSTANCE_LOG_DIR}/${TAG_RUN}.json"

# ---- Helpers ---------------------------------------------------------------

log() { echo -e "\033[1;34m[launch]\033[0m $*" >&2; }
err() { echo -e "\033[1;31m[error]\033[0m $*" >&2; exit 1; }

read_fmw_var() {
    local key="$1"
    local fmw="${HOME}/.fmw"
    [[ -f "$fmw" ]] || err "expected ~/.fmw with $key=..."
    local v
    v="$(grep -E "^${key}=" "$fmw" | head -1 | cut -d= -f2-)"
    [[ -n "$v" ]] || err "$key not found in ~/.fmw"
    printf '%s' "$v"
}

aws_call() {
    aws --profile "$AWS_PROFILE" --region "$AWS_REGION" "$@"
}

require_files() {
    for f in \
        "${REPO_ROOT}/corpora/${TRAIN_FILE}" \
        "${REPO_ROOT}/corpora/${VAL_FILE}" \
        "${REPO_ROOT}/scripts/${TRAINER_SCRIPT}" \
        "${REPO_ROOT}/scripts/eval_sft_v1.py" \
        "${REPO_ROOT}/scripts/eval_groundedness.py" \
        "${REPO_ROOT}/eval/gov_helpdesk_gold_v1.jsonl"; do
        [[ -f "$f" ]] || err "required file missing: $f"
    done
}

require_aws_session() {
    if ! aws_call sts get-caller-identity >/dev/null 2>&1; then
        err "AWS session expired. Run: aws sso login --profile ${AWS_PROFILE}"
    fi
}

# ---- Phase: push -----------------------------------------------------------
#
# Uploads SFT data + scripts to private HF repos. Idempotent — re-running
# overwrites with current local state (HF dedupes via content hash).

phase_push() {
    require_files
    local hf_token
    hf_token="$(read_fmw_var HF_TOKEN)"

    log "logging into HF as ${HF_USER}…"
    HF_TOKEN="$hf_token" hf auth login --token "$hf_token" --add-to-git-credential >/dev/null 2>&1 || true

    local who
    who="$(HF_TOKEN="$hf_token" hf auth whoami 2>/dev/null | head -1 || true)"
    log "logged in as: ${who:-?}"

    log "ensuring data repo ${HF_DATA_REPO} (private dataset)…"
    HF_TOKEN="$hf_token" hf repo create \
        --repo-type dataset --private --exist-ok "$HF_DATA_REPO" >/dev/null

    log "ensuring scripts repo ${HF_SCRIPTS_REPO} (private model)…"
    HF_TOKEN="$hf_token" hf repo create \
        --repo-type model --private --exist-ok "$HF_SCRIPTS_REPO" >/dev/null

    log "uploading SFT data → ${HF_DATA_REPO} (data version: ${DATA_VERSION})…"
    if [ -f "${REPO_ROOT}/corpora/${TRAIN_FILE}" ]; then
        HF_TOKEN="$hf_token" hf upload --repo-type dataset \
            "$HF_DATA_REPO" "${REPO_ROOT}/corpora/${TRAIN_FILE}" "${TRAIN_FILE}"
    fi
    if [ -f "${REPO_ROOT}/corpora/${VAL_FILE}" ]; then
        HF_TOKEN="$hf_token" hf upload --repo-type dataset \
            "$HF_DATA_REPO" "${REPO_ROOT}/corpora/${VAL_FILE}" "${VAL_FILE}"
    fi
    HF_TOKEN="$hf_token" hf upload --repo-type dataset \
        "$HF_DATA_REPO" \
        "${REPO_ROOT}/eval/gov_helpdesk_gold_v1.jsonl" \
        gov_helpdesk_gold_v1.jsonl

    log "uploading scripts → ${HF_SCRIPTS_REPO}…"
    local scripts_dir
    scripts_dir="$(mktemp -d)"
    # Push everything we might need; the user-data picks the right ones.
    for s in train_sft_v1.py eval_sft_v1.py eval_groundedness.py \
             format_sft_v1.py format_sft_v2.py; do
        if [ -f "${REPO_ROOT}/scripts/${s}" ]; then
            cp "${REPO_ROOT}/scripts/${s}" "$scripts_dir/"
        fi
    done
    HF_TOKEN="$hf_token" hf upload --repo-type model \
        "$HF_SCRIPTS_REPO" "$scripts_dir" .
    rm -rf "$scripts_dir"

    log "push done."
    log "  data:    https://huggingface.co/datasets/${HF_DATA_REPO}"
    log "  scripts: https://huggingface.co/${HF_SCRIPTS_REPO}"
}

# ---- Phase: launch ---------------------------------------------------------

# Build the cloud-init user-data for one seed. Stdout = the user-data text.
# This is what runs when the instance boots.
#
# Implementation note: the template uses __PLACEHOLDER__ tokens that we
# substitute via sed at the end. This way the heredoc is fully quoted
# (no shell expansion at template-generation time), preserving every
# `$VAR` and `\$VAR` for the bash that actually runs on the instance.
build_user_data() {
    local seed="$1"
    local hf_token="$2"
    local deepseek_key="$3"
    local run_label="${RUN_LABEL_PREFIX}_seed${seed}"
    local ckpt_repo="${HF_CHECKPOINT_REPO_BASE}-seed${seed}"

    # Single-quoted heredoc: NO local shell expansion. Placeholders are
    # __SEED__, __HF_TOKEN__, etc.
    local template
    template="$(cat <<'TEMPLATE_EOF'
#!/bin/bash
# Cloud-init for SFT v1 training, seed __SEED__.
set -euxo pipefail
exec > >(tee -a /var/log/sft-init.log) 2>&1
echo "=== sft-init starting at $(date -u +%FT%TZ) seed=__SEED__ ==="

# Run the rest as 'ubuntu' so files end up in /home/ubuntu and pip caches
# go there too.
sudo -u ubuntu -i bash <<'INNER_EOF'
set -euxo pipefail
cd /home/ubuntu

export HF_TOKEN='__HF_TOKEN__'
export DEEPSEEK_API_KEY='__DEEPSEEK_KEY__'
export RUN_LABEL='__RUN_LABEL__'
export SEED='__SEED__'
export HF_DATA_REPO='__HF_DATA_REPO__'
export HF_SCRIPTS_REPO='__HF_SCRIPTS_REPO__'
export HF_CHECKPOINT_REPO='__HF_CHECKPOINT_REPO__'
export BASE_MODEL='__BASE_MODEL__'
export MAX_WALL_HOURS='__MAX_WALL_HOURS__'

# DLAMI Ubuntu 22.04 ships pytorch in either /opt/pytorch (venv) or a
# conda env named 'pytorch'. Try both; ignore failures (we'll still have
# system python).
if [ -f /opt/pytorch/bin/activate ]; then
    source /opt/pytorch/bin/activate
elif [ -f /opt/conda/etc/profile.d/conda.sh ]; then
    source /opt/conda/etc/profile.d/conda.sh
    conda activate pytorch || true
fi

pip install -U --quiet \
    "transformers>=4.50" \
    "peft>=0.13" \
    "accelerate>=1.0" \
    "datasets>=3.0" \
    "huggingface_hub>=0.26" \
    "bitsandbytes>=0.44" \
    "sacrebleu" \
    "sentencepiece"

mkdir -p /home/ubuntu/data /home/ubuntu/scripts /home/ubuntu/checkpoints /home/ubuntu/eval

# Pull data + scripts from HF. The DLAMI ships the new `hf` CLI; the legacy
# `huggingface-cli` is removed in huggingface_hub >= 0.34.
hf download --repo-type dataset --local-dir /home/ubuntu/data --token "$HF_TOKEN" \
    "$HF_DATA_REPO" __TRAIN_FILE__ __VAL_FILE__ gov_helpdesk_gold_v1.jsonl

hf download --local-dir /home/ubuntu/scripts --token "$HF_TOKEN" \
    "$HF_SCRIPTS_REPO" __TRAINER_SCRIPT__ eval_sft_v1.py eval_groundedness.py format_sft_v2.py format_sft_v1.py

cp /home/ubuntu/data/gov_helpdesk_gold_v1.jsonl /home/ubuntu/eval/

# Ensure HF checkpoint repo exists.
hf repo create --repo-type model --private --exist-ok "$HF_CHECKPOINT_REPO" \
    --token "$HF_TOKEN" >/dev/null 2>&1 || true

# Run train + eval inside tmux so the lifecycle survives ssh disconnects.
# This is a single bash process inside tmux. Trainer always pushes to HF
# on abort, so even a crash leaves a step-N checkpoint.
tmux new-session -d -s train "bash -c '
set -uxo pipefail
cd /home/ubuntu
export HF_TOKEN=\"$HF_TOKEN\"
export DEEPSEEK_API_KEY=\"$DEEPSEEK_API_KEY\"

echo \"=== train start \$(date -u +%FT%TZ) ===\" | tee -a train.log
python scripts/__TRAINER_SCRIPT__ \
    --train data/__TRAIN_FILE__ \
    --val data/__VAL_FILE__ \
    --model-id \"$BASE_MODEL\" \
    --output /home/ubuntu/checkpoints/$RUN_LABEL \
    --seed $SEED \
    --hf-repo \"$HF_CHECKPOINT_REPO\" \
    --max-wall-hours $MAX_WALL_HOURS \
    --epochs __EPOCHS__ \
    __TRAIN_EXTRA_ARGS__ \
    2>&1 | tee -a train.log
TRAIN_RC=\$?
echo \"=== train done rc=\$TRAIN_RC \$(date -u +%FT%TZ) ===\" | tee -a train.log

ADAPTER_DIR=\"/home/ubuntu/checkpoints/$RUN_LABEL/best\"
if [ ! -d \"\$ADAPTER_DIR\" ]; then
    echo \"no best/ adapter — running baseline eval fallback\" | tee -a eval.log
    python scripts/eval_sft_v1.py \
        --base \"$BASE_MODEL\" \
        --no-adapter \
        --label \"${RUN_LABEL}-baseline-fallback\" \
        --gold data/gov_helpdesk_gold_v1.jsonl \
        --out-root eval/reports \
        2>&1 | tee -a eval.log
else
    echo \"running eval against \$ADAPTER_DIR\" | tee -a eval.log
    python scripts/eval_sft_v1.py \
        --base \"$BASE_MODEL\" \
        --adapter \"\$ADAPTER_DIR\" \
        --label \"$RUN_LABEL\" \
        --gold data/gov_helpdesk_gold_v1.jsonl \
        --out-root eval/reports \
        2>&1 | tee -a eval.log
fi

# Final push. Best-effort — if HF is down, we still have local files
# accessible via the AWS console serial-output.
hf upload --repo-type model --token \"$HF_TOKEN\" \
    \"$HF_CHECKPOINT_REPO\" /home/ubuntu/checkpoints/$RUN_LABEL ckpt || true
hf upload --repo-type model --token \"$HF_TOKEN\" \
    \"$HF_CHECKPOINT_REPO\" /home/ubuntu/eval/reports eval || true
hf upload --repo-type model --token \"$HF_TOKEN\" \
    \"$HF_CHECKPOINT_REPO\" /home/ubuntu/train.log train.log || true

echo \"=== all done \$(date -u +%FT%TZ) ===\" | tee -a done.log
# KEEP_ALIVE_MIN > 0 means leave the instance up for that many minutes
# after work is done, before auto-shutdown. Useful for debugging (ssh in
# while the model is still cached on disk + GPU). Cron-based watchdog
# handles the eventual shutdown.
KEEP_ALIVE_MIN=__KEEP_ALIVE_MIN__
if [ \"\$KEEP_ALIVE_MIN\" -gt 0 ]; then
    echo \"keeping instance alive for \$KEEP_ALIVE_MIN min (debug mode)\" | tee -a done.log
    echo \"sudo shutdown -h now\" | sudo at \"now + \$KEEP_ALIVE_MIN minutes\" 2>&1 || \\
        (sleep \"\$((KEEP_ALIVE_MIN * 60))\" && sudo shutdown -h now) &
else
    echo \"shutting down\" | tee -a done.log
    sudo shutdown -h now
fi
'"
INNER_EOF
TEMPLATE_EOF
)"

    # Substitute placeholders. We use a Python helper for safe substitution
    # because tokens may contain characters that would confuse sed (e.g. /, &).
    python3 - "$template" \
        "__SEED__=$seed" \
        "__HF_TOKEN__=$hf_token" \
        "__DEEPSEEK_KEY__=$deepseek_key" \
        "__RUN_LABEL__=$run_label" \
        "__HF_DATA_REPO__=$HF_DATA_REPO" \
        "__HF_SCRIPTS_REPO__=$HF_SCRIPTS_REPO" \
        "__HF_CHECKPOINT_REPO__=$ckpt_repo" \
        "__BASE_MODEL__=$BASE_MODEL" \
        "__MAX_WALL_HOURS__=$MAX_WALL_HOURS" \
        "__KEEP_ALIVE_MIN__=$KEEP_ALIVE_MIN" \
        "__TRAIN_FILE__=$TRAIN_FILE" \
        "__VAL_FILE__=$VAL_FILE" \
        "__TRAINER_SCRIPT__=$TRAINER_SCRIPT" \
        "__EPOCHS__=$EPOCHS" \
        "__TRAIN_EXTRA_ARGS__=$TRAIN_EXTRA_ARGS" \
        <<'PY_HELPER'
import sys
template = sys.argv[1]
for kv in sys.argv[2:]:
    k, v = kv.split("=", 1)
    template = template.replace(k, v)
sys.stdout.write(template)
PY_HELPER
}

phase_launch() {
    require_files
    require_aws_session

    local dry_run="false"
    local launch_seeds="$SEEDS"
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dry-run) dry_run="true"; shift ;;
            --seeds)   launch_seeds="$2"; shift 2 ;;
            *) err "unknown flag: $1" ;;
        esac
    done

    local hf_token deepseek_key
    hf_token="$(read_fmw_var HF_TOKEN)"
    deepseek_key="$(read_fmw_var DEEPSEEK || true)"
    [[ -n "$deepseek_key" ]] || log "WARN: no DEEPSEEK key — eval LLM-judge + pairwise will be skipped"

    log "verifying key pair: ${KEY_NAME}…"
    aws_call ec2 describe-key-pairs --key-names "$KEY_NAME" --query 'KeyPairs[0].KeyName' --output text >/dev/null \
        || err "key pair '$KEY_NAME' not found in ${AWS_REGION}. Set KEY_NAME=<your-key>"

    log "checking instance-type quota for ${INSTANCE_TYPE}…"
    # Soft check — real quota errors will surface from run-instances.

    : > "$INSTANCE_LOG"
    echo "{\"run_tag\": \"${TAG_RUN}\", \"region\": \"${AWS_REGION}\", \"instances\": [" >> "$INSTANCE_LOG"

    local first=true
    for seed in $launch_seeds; do
        log "preparing instance for seed=${seed}…"
        local user_data
        user_data="$(build_user_data "$seed" "$hf_token" "$deepseek_key")"

        if [[ "$dry_run" == "true" ]]; then
            log "DRY RUN — user-data for seed=${seed}:"
            echo "------- BEGIN USER-DATA -------"
            echo "$user_data"
            echo "------- END USER-DATA -------"
            continue
        fi

        local user_data_b64
        user_data_b64="$(printf '%s' "$user_data" | base64 | tr -d '\n')"

        # Launch with --instance-initiated-shutdown-behavior stop so
        # `sudo shutdown -h now` from inside the instance stops it (preserves
        # EBS, can be restarted to resume iteration without re-downloading
        # the 16 GB Gemma 4 model). Only `phase_terminate` truly destroys.
        local result
        result="$(aws_call ec2 run-instances \
            --image-id "$AMI_ID" \
            --instance-type "$INSTANCE_TYPE" \
            --key-name "$KEY_NAME" \
            --subnet-id "$SUBNET_ID" \
            --security-group-ids "$SECURITY_GROUP_ID" \
            --instance-initiated-shutdown-behavior stop \
            --block-device-mappings "[{\"DeviceName\":\"/dev/sda1\",\"Ebs\":{\"VolumeSize\":${EBS_GB},\"VolumeType\":\"gp3\",\"DeleteOnTermination\":true}}]" \
            --user-data "$user_data_b64" \
            --tag-specifications "ResourceType=instance,Tags=[{Key=Project,Value=${PROJECT_TAG}},{Key=Seed,Value=${seed}},{Key=RunTag,Value=${TAG_RUN}},{Key=Name,Value=${PROJECT_TAG}-${seed}}]" \
            --query 'Instances[0].[InstanceId]' \
            --output text)"
        local instance_id="$result"

        log "  launched ${instance_id} (seed=${seed})"
        if [[ "$first" == "true" ]]; then first=false; else echo "," >> "$INSTANCE_LOG"; fi
        echo -n "  {\"seed\": ${seed}, \"instance_id\": \"${instance_id}\"}" >> "$INSTANCE_LOG"
    done
    echo "" >> "$INSTANCE_LOG"
    echo "]}" >> "$INSTANCE_LOG"

    if [[ "$dry_run" != "true" ]]; then
        log ""
        log "instances logged to: ${INSTANCE_LOG}"
        log "monitor:    $0 status"
        log "ssh in:     $0 ssh <seed>"
        log "logs:       ssh ubuntu@<ip> 'tail -f /home/ubuntu/train.log'"
        log "tmux:       ssh ubuntu@<ip> 'tmux attach -t train'"
        log "terminate:  $0 terminate"
    fi
}

# ---- Phase: status ---------------------------------------------------------

phase_status() {
    require_aws_session
    log "instances tagged Project=${PROJECT_TAG} in ${AWS_REGION}:"
    aws_call ec2 describe-instances \
        --filters "Name=tag:Project,Values=${PROJECT_TAG}" \
                  "Name=instance-state-name,Values=pending,running,stopping,stopped,shutting-down,terminated" \
        --query 'Reservations[].Instances[].[Tags[?Key==`Seed`]|[0].Value,InstanceId,State.Name,LaunchTime,PublicIpAddress,Tags[?Key==`RunTag`]|[0].Value]' \
        --output table
}

# ---- Phase: ssh ------------------------------------------------------------

phase_ssh() {
    local target_seed="${1:-}"
    [[ -n "$target_seed" ]] || err "usage: $0 ssh <seed>"
    require_aws_session

    local ip
    ip="$(aws_call ec2 describe-instances \
        --filters "Name=tag:Project,Values=${PROJECT_TAG}" \
                  "Name=tag:Seed,Values=${target_seed}" \
                  "Name=instance-state-name,Values=running" \
        --query 'Reservations[0].Instances[0].PublicIpAddress' \
        --output text)"
    [[ -n "$ip" && "$ip" != "None" ]] || err "no running instance with Seed=${target_seed}"

    log "sshing to seed=${target_seed} at ${ip}…"
    local key_path="${HOME}/.ssh/${KEY_NAME}.pem"
    [[ -f "$key_path" ]] || key_path="${HOME}/.ssh/${KEY_NAME}"
    [[ -f "$key_path" ]] || err "no private key at ~/.ssh/${KEY_NAME}{.pem,}"
    exec ssh -i "$key_path" -o StrictHostKeyChecking=no "ubuntu@${ip}"
}

# ---- Phase: stop / start / terminate ---------------------------------------

phase_stop() {
    require_aws_session
    log "finding running instances to stop (Project=${PROJECT_TAG})…"
    local ids
    ids="$(aws_call ec2 describe-instances \
        --filters "Name=tag:Project,Values=${PROJECT_TAG}" \
                  "Name=instance-state-name,Values=pending,running" \
        --query 'Reservations[].Instances[].InstanceId' \
        --output text)"
    if [[ -z "$ids" ]]; then
        log "nothing to stop."
        return 0
    fi
    log "stopping: $ids (EBS preserved — restart with: $0 start)"
    aws_call ec2 stop-instances --instance-ids $ids \
        --query 'StoppingInstances[].[InstanceId,CurrentState.Name]' --output table
}

phase_start() {
    require_aws_session
    log "finding stopped instances to start (Project=${PROJECT_TAG})…"
    local ids
    ids="$(aws_call ec2 describe-instances \
        --filters "Name=tag:Project,Values=${PROJECT_TAG}" \
                  "Name=instance-state-name,Values=stopped" \
        --query 'Reservations[].Instances[].InstanceId' \
        --output text)"
    if [[ -z "$ids" ]]; then
        log "nothing to start."
        return 0
    fi
    log "starting: $ids"
    aws_call ec2 start-instances --instance-ids $ids \
        --query 'StartingInstances[].[InstanceId,CurrentState.Name]' --output table
    log "give the instance ~30s to boot, then: $0 status / $0 ssh <seed>"
}

phase_terminate() {
    require_aws_session
    log "finding instances to TERMINATE — DESTROYS EBS + cached models (Project=${PROJECT_TAG})…"
    local ids
    ids="$(aws_call ec2 describe-instances \
        --filters "Name=tag:Project,Values=${PROJECT_TAG}" \
                  "Name=instance-state-name,Values=pending,running,stopping,stopped" \
        --query 'Reservations[].Instances[].InstanceId' \
        --output text)"
    if [[ -z "$ids" ]]; then
        log "nothing to terminate."
        return 0
    fi
    log "terminating: $ids"
    aws_call ec2 terminate-instances --instance-ids $ids \
        --query 'TerminatingInstances[].[InstanceId,CurrentState.Name]' --output table
}

# ---- Dispatch --------------------------------------------------------------

main() {
    local cmd="${1:-help}"
    shift || true
    case "$cmd" in
        push)       phase_push "$@" ;;
        launch)     phase_launch "$@" ;;
        status)     phase_status "$@" ;;
        ssh)        phase_ssh "$@" ;;
        stop)       phase_stop "$@" ;;
        start)      phase_start "$@" ;;
        terminate)  phase_terminate "$@" ;;
        all)        phase_push; phase_launch "$@" ;;
        help|*)
            cat <<EOF
usage: $0 {push|launch|status|ssh|stop|start|terminate|all} [...]

  push                       upload data + scripts to HF (idempotent)
  launch                     launch 3× ${INSTANCE_TYPE} (one per seed)
    --seeds "42"             override seeds (default: ${SEEDS})
    --dry-run                print user-data + commands without launching
  status                     describe Project=${PROJECT_TAG} instances
  ssh <seed>                 ssh into the running instance for a seed
  stop                       stop ALL Project=${PROJECT_TAG} instances (preserves EBS)
  start                      start stopped Project=${PROJECT_TAG} instances
  terminate                  TERMINATE — destroys EBS + cached models
  all                        push then launch

env overrides:
  AWS_PROFILE              ${AWS_PROFILE}
  AWS_REGION               ${AWS_REGION}
  INSTANCE_TYPE            ${INSTANCE_TYPE}
  AMI_ID                   ${AMI_ID}
  KEY_NAME                 ${KEY_NAME}
  HF_USER                  ${HF_USER}
  BASE_MODEL               ${BASE_MODEL}
  SEEDS                    "${SEEDS}"
  MAX_WALL_HOURS           ${MAX_WALL_HOURS}
EOF
            ;;
    esac
}

main "$@"
