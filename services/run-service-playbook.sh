#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEFAULT_INVENTORY="${REPO_ROOT}/turner-services-sensitive-repo/inventories/ansible-inv-rack.proxmox.yml"

usage() {
  cat <<USAGE
Usage: services/run-service-playbook.sh [options] [-- <ansible-playbook args>]

Run a service Ansible playbook from the services directory.

Options:
  -s, --service <name>     Service directory path relative to services/
                           Examples: github-runner-vm, k8s-cluster/primary
  -i, --inventory <path>   Inventory file path
                           Default: ${DEFAULT_INVENTORY}
  -l, --list               List discovered services and exit
      --check              Run ansible-playbook --syntax-check
      --limit <pattern>    Pass --limit to ansible-playbook
  -h, --help               Show this help

Examples:
  services/run-service-playbook.sh --service github-runner-vm
  services/run-service-playbook.sh --service k8s-cluster/test --check
  services/run-service-playbook.sh --service k8s-cluster/primary -- --diff -vv
USAGE
}

discover_services() {
  find "${SCRIPT_DIR}" -mindepth 2 -maxdepth 4 -type f -name 'site.yml' \
    | sed -E "s#^${SCRIPT_DIR}/##" \
    | sed -E 's#/site.yml$##' \
    | sort
}

select_service_interactive() {
  local -n _services_ref="$1"

  if [[ ! -t 0 ]]; then
    echo "Error: no --service provided and stdin is not interactive." >&2
    echo "Use --service <name> for CI/non-interactive usage." >&2
    exit 1
  fi

  echo "Select a service:" >&2
  local i=1
  for service in "${_services_ref[@]}"; do
    echo "${i}) ${service}" >&2
    ((i++))
  done

  local choice
  read -r -p "Enter choice [1-${#_services_ref[@]}]: " choice

  if [[ ! "${choice}" =~ ^[0-9]+$ ]] || (( choice < 1 || choice > ${#_services_ref[@]} )); then
    echo "Invalid choice: ${choice}" >&2
    exit 1
  fi

  echo "${_services_ref[$((choice - 1))]}"
}

SERVICE=""
INVENTORY="${DEFAULT_INVENTORY}"
CHECK_ONLY=0
LIST_ONLY=0
LIMIT_PATTERN=""
EXTRA_ARGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    -s|--service)
      SERVICE="${2:-}"
      shift 2
      ;;
    -i|--inventory)
      INVENTORY="${2:-}"
      shift 2
      ;;
    -l|--list)
      LIST_ONLY=1
      shift
      ;;
    --check)
      CHECK_ONLY=1
      shift
      ;;
    --limit)
      LIMIT_PATTERN="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      EXTRA_ARGS=("$@")
      break
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

mapfile -t SERVICES < <(discover_services)

if (( ${#SERVICES[@]} == 0 )); then
  echo "Error: no service playbooks found under ${SCRIPT_DIR}" >&2
  exit 1
fi

if (( LIST_ONLY == 1 )); then
  printf '%s\n' "${SERVICES[@]}"
  exit 0
fi

if [[ -z "${SERVICE}" ]]; then
  SERVICE="$(select_service_interactive SERVICES)"
fi

PLAYBOOK_PATH="${SCRIPT_DIR}/${SERVICE}/site.yml"
if [[ ! -f "${PLAYBOOK_PATH}" ]]; then
  echo "Error: service '${SERVICE}' not found. Use --list to view valid options." >&2
  exit 1
fi

if [[ ! -f "${INVENTORY}" ]]; then
  echo "Error: inventory file not found at ${INVENTORY}" >&2
  exit 1
fi

if ! command -v ansible-playbook >/dev/null 2>&1; then
  echo "Error: ansible-playbook is not installed or not on PATH." >&2
  exit 1
fi

CMD=(ansible-playbook -i "${INVENTORY}" "${PLAYBOOK_PATH}")
if (( CHECK_ONLY == 1 )); then
  CMD+=(--syntax-check)
fi
if [[ -n "${LIMIT_PATTERN}" ]]; then
  CMD+=(--limit "${LIMIT_PATTERN}")
fi
if (( ${#EXTRA_ARGS[@]} > 0 )); then
  CMD+=("${EXTRA_ARGS[@]}")
fi

echo "Service: ${SERVICE}"
echo "Playbook: ${PLAYBOOK_PATH}"
echo "Inventory: ${INVENTORY}"

ANSIBLE_CONFIG="${REPO_ROOT}/ansible.cfg" \
ANSIBLE_ROLES_PATH="${REPO_ROOT}/roles${ANSIBLE_ROLES_PATH:+:${ANSIBLE_ROLES_PATH}}" \
"${CMD[@]}"
