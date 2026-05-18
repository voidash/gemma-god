#!/usr/bin/env bash
set -euo pipefail

PI_SSH="${PI_SSH:-cdjk@pi}"
REMOTE_DIR="${REMOTE_DIR:-~/gemma-god-pi}"
RUN_INSTALL="${RUN_INSTALL:-1}"
RUN_START="${RUN_START:-1}"

SSH_OPTS=(-o StrictHostKeyChecking=no -o ConnectTimeout=10)
SCP_OPTS=(-o StrictHostKeyChecking=no -o ConnectTimeout=10)
SSH=(ssh "${SSH_OPTS[@]}")
SCP=(scp "${SCP_OPTS[@]}")

if [[ -n "${PI_PASSWORD:-}" ]]; then
  if ! command -v sshpass >/dev/null 2>&1; then
    echo "PI_PASSWORD is set but sshpass is not installed locally" >&2
    exit 2
  fi
  SSH=(sshpass -p "$PI_PASSWORD" ssh "${SSH_OPTS[@]}" -o PreferredAuthentications=password -o PubkeyAuthentication=no)
  SCP=(sshpass -p "$PI_PASSWORD" scp "${SCP_OPTS[@]}" -o PreferredAuthentications=password -o PubkeyAuthentication=no)
fi

mkdir -p /tmp/gemma-god-pi-deploy

"${SSH[@]}" "$PI_SSH" "mkdir -p $REMOTE_DIR/scripts"
"${SCP[@]}" \
  scripts/pi_llamacpp_install.sh \
  scripts/pi_llamacpp_start.sh \
  scripts/pi_llamacpp_smoke.sh \
  scripts/pi_llamacpp_office_demo.sh \
  "$PI_SSH:$REMOTE_DIR/scripts/"

"${SSH[@]}" "$PI_SSH" "chmod +x $REMOTE_DIR/scripts/pi_llamacpp_*.sh"

if [[ "$RUN_INSTALL" == "1" ]]; then
  "${SSH[@]}" "$PI_SSH" "bash $REMOTE_DIR/scripts/pi_llamacpp_install.sh"
fi

if [[ "$RUN_START" == "1" ]]; then
  "${SSH[@]}" "$PI_SSH" "bash $REMOTE_DIR/scripts/pi_llamacpp_start.sh"
  "${SSH[@]}" "$PI_SSH" "BASE_URL=http://127.0.0.1:8081 bash $REMOTE_DIR/scripts/pi_llamacpp_smoke.sh"
fi
