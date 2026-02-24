#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

MODE="preview"
TARGET_MODE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -u|--up)
      MODE="up"
      shift
      ;;
    -d|--destroy)
      MODE="destroy"
      shift
      ;;
    --test)
      TARGET_MODE="test"
      shift
      ;;
    --prod|--production)
      TARGET_MODE="production"
      shift
      ;;
    --both)
      TARGET_MODE="both"
      shift
      ;;
    -h|--help)
      echo "Usage: ./run-pulumi-up.sh [--test|--prod|--both] [-u|--up|-d|--destroy]"
      echo "  default: pulumi preview"
      echo "  -u:      pulumi up --yes"
      echo "  -d:      pulumi destroy --yes"
      echo "  --test:  run only test stack"
      echo "  --prod:  run only production stack"
      echo "  --both:  run test and production stacks"
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Usage: ./run-pulumi-up.sh [--test|--prod|--both] [-u|--up|-d|--destroy]" >&2
      exit 1
      ;;
  esac
done

if ! command -v pulumi >/dev/null 2>&1; then
  echo "Error: pulumi CLI is not installed or not on PATH." >&2
  exit 1
fi

if [[ -n "${TS_SERVER_LIST_PATH:-}" ]]; then
  echo "Warning: TS_SERVER_LIST_PATH is set in your shell and will be ignored by this script." >&2
fi

if [[ -n "${PULUMI_STACK:-}" ]]; then
  echo "Warning: PULUMI_STACK is set in your shell and will be ignored by this script." >&2
fi

run_pulumi() {
  env -u TS_SERVER_LIST_PATH -u PULUMI_STACK pulumi "$@"
}

ANSIBLE_PLAYBOOK="../linux-base-config-pulumi.yml"
REBOOT_PLAYBOOK="../reboot-linux-hosts.yml"
PRIMARY_INVENTORY="../../turner-services-sensitive-repo/inventories/ansible-inv-rack.proxmox.yml"
FALLBACK_INVENTORY="../../inventories/ansible-inv-example.proxmox.yml"
ANSIBLE_INVENTORY=""

collect_meaningfully_changed_vms() {
  local pulumi_output_file="$1"
  awk '
    /proxmoxve:VM:VirtualMachine/ {
      # Strip ANSI color codes so field parsing remains stable.
      gsub(/\x1b\[[0-9;]*[A-Za-z]/, "", $0)
      name=""
      status=""
      for (i = 1; i <= NF; i++) {
        if ($i == "proxmoxve:VM:VirtualMachine") {
          if (i + 1 <= NF) {
            name = $(i + 1)
          }
          if (i + 2 <= NF) {
            status = $(i + 2)
          }
          break
        }
      }
      if (name != "" && status ~ /^(create|created|update|updated|replace|replaced)$/) {
        print name
      }
    }
  ' "${pulumi_output_file}" | sort -u
}

if [[ "${MODE}" == "up" ]]; then
  if ! command -v ansible-playbook >/dev/null 2>&1; then
    echo "Error: ansible-playbook is not installed or not on PATH." >&2
    exit 1
  fi

  if [[ ! -f "${ANSIBLE_PLAYBOOK}" ]]; then
    echo "Error: Ansible playbook not found at ${ANSIBLE_PLAYBOOK}" >&2
    exit 1
  fi

  if [[ ! -f "${REBOOT_PLAYBOOK}" ]]; then
    echo "Error: Reboot playbook not found at ${REBOOT_PLAYBOOK}" >&2
    exit 1
  fi

  if [[ -f "${PRIMARY_INVENTORY}" ]]; then
    ANSIBLE_INVENTORY="${PRIMARY_INVENTORY}"
  elif [[ -f "${FALLBACK_INVENTORY}" ]]; then
    ANSIBLE_INVENTORY="${FALLBACK_INVENTORY}"
  else
    echo "Error: no Proxmox dynamic inventory file found." >&2
    echo "Checked: ${PRIMARY_INVENTORY}" >&2
    echo "Checked: ${FALLBACK_INVENTORY}" >&2
    exit 1
  fi
fi

PROD_SERVER_LIST="../../turner-services-sensitive-repo/server-list-prod.yml"
TEST_SERVER_LIST="../../turner-services-sensitive-repo/server-list-test.yml"
PROD_STACK="ts-proxmox-prod"
TEST_STACK="ts-proxmox-test"

if [[ ! -f "${PROD_SERVER_LIST}" ]]; then
  echo "Error: production server list not found at ${PROD_SERVER_LIST}" >&2
  exit 1
fi

if [[ ! -f "${TEST_SERVER_LIST}" ]]; then
  echo "Error: test server list not found at ${TEST_SERVER_LIST}" >&2
  exit 1
fi

targets=()
if [[ -n "${TARGET_MODE}" ]]; then
  case "${TARGET_MODE}" in
    test) targets=("test") ;;
    production) targets=("production") ;;
    both) targets=("test" "production") ;;
    *)
      echo "Invalid target mode: ${TARGET_MODE}" >&2
      exit 1
      ;;
  esac
else
  echo "Choose deployment target:"
  echo "1) test"
  echo "2) production"
  echo "3) both"
  read -r -p "Enter choice [1-3]: " choice

  case "${choice}" in
    1) targets=("test") ;;
    2) targets=("production") ;;
    3) targets=("test" "production") ;;
    *)
      echo "Invalid choice: ${choice}" >&2
      exit 1
      ;;
  esac
fi

for target in "${targets[@]}"; do
  if [[ "${target}" == "test" ]]; then
    stack="${TEST_STACK}"
    server_list="${TEST_SERVER_LIST}"
    environment="test"
  else
    stack="${PROD_STACK}"
    server_list="${PROD_SERVER_LIST}"
    environment="production"
  fi

  echo
  echo "Running pulumi ${MODE} for ${target} using stack '${stack}'..."
  echo "Using server list: ${server_list}"
  pulumi_output_file=""
  changed_host_limit=""
  run_pulumi config set serverListPath "${server_list}" --stack "${stack}"
  run_pulumi config set environment "${environment}" --stack "${stack}"
  if [[ "${MODE}" == "up" ]]; then
    pulumi_output_file="$(mktemp --suffix=.pulumi-up.log)"
    run_pulumi "${MODE}" --stack "${stack}" --yes --color always | tee "${pulumi_output_file}"
    mapfile -t changed_hosts < <(collect_meaningfully_changed_vms "${pulumi_output_file}")
    rm -f "${pulumi_output_file}"
    if [[ "${#changed_hosts[@]}" -gt 0 ]]; then
      changed_host_limit="$(IFS=:; echo "${changed_hosts[*]}")"
      echo "Meaningful VM updates detected: ${changed_host_limit}"
    else
      echo "No meaningful VM updates detected; reboot step will be skipped."
    fi
  elif [[ "${MODE}" == "destroy" ]]; then
    run_pulumi "${MODE}" --stack "${stack}" --yes
  else
    run_pulumi "${MODE}" --stack "${stack}"
  fi

  if [[ "${MODE}" == "up" ]]; then
    limit_expr="tag_pulumi:&tag_${environment}"
    echo "Running Ansible linux-base-config for ${target}..."
    echo "Using inventory: ${ANSIBLE_INVENTORY}"
    echo "Using limit: ${limit_expr}"
    ANSIBLE_CONFIG="${REPO_ROOT}/ansible.cfg" \
    ANSIBLE_ROLES_PATH="${REPO_ROOT}/roles${ANSIBLE_ROLES_PATH:+:${ANSIBLE_ROLES_PATH}}" \
    ansible-playbook \
      -i "${ANSIBLE_INVENTORY}" \
      "${ANSIBLE_PLAYBOOK}" \
      --limit "${limit_expr}"

    if [[ -n "${changed_host_limit}" ]]; then
      echo "Rebooting meaningfully updated VMs: ${changed_host_limit}"
      ANSIBLE_CONFIG="${REPO_ROOT}/ansible.cfg" \
      ANSIBLE_ROLES_PATH="${REPO_ROOT}/roles${ANSIBLE_ROLES_PATH:+:${ANSIBLE_ROLES_PATH}}" \
      ansible-playbook \
        -i "${ANSIBLE_INVENTORY}" \
        "${REBOOT_PLAYBOOK}" \
        --limit "${changed_host_limit}"
    fi
  fi
done
