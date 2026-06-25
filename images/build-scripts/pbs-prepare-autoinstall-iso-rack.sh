#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"

if [[ -z "${TS_TURNERANS_SVC_SSH_PRIVKEY:-}" ]]; then
  if [[ -f "${REPO_ROOT}/.secrets/env.sh" ]]; then
    # shellcheck disable=SC1091
    source "${REPO_ROOT}/.secrets/env.sh"
  else
    echo "Error: TS_* env vars unset and ${REPO_ROOT}/.secrets/env.sh missing." >&2
    echo "Run scripts/bootstrap-secrets.sh after pass-cli login." >&2
    exit 1
  fi
fi

export PBS_AUTOINSTALL_ANSWER_FILE="${PBS_AUTOINSTALL_ANSWER_FILE:-${REPO_ROOT}/turner-services-sensitive-repo/proxmox-backup-server/answer.toml}"
export PBS_AUTOINSTALL_FIRST_BOOT_FILE="${PBS_AUTOINSTALL_FIRST_BOOT_FILE:-${REPO_ROOT}/images/proxmox-backup-server-autoinstall/first-boot.sh}"

ANSIBLE_CONFIG="${REPO_ROOT}/ansible.cfg" ansible-playbook \
  --private-key "${TS_TURNERANS_SVC_SSH_PRIVKEY}" \
  -i "${REPO_ROOT}/turner-services-sensitive-repo/inventories/servers.yml" \
  "${REPO_ROOT}/images/proxmox-backup-server-autoinstall/prepare-pbs-autoinstall-iso.yml"
