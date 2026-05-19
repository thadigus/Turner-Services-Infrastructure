#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEFAULT_RECORDS_ROOT="${REPO_ROOT}/turner-services-sensitive-repo/unifi-dns"

if [[ -z "${TS_UNIFI_API_KEY:-}" ]]; then
  if [[ -f "${REPO_ROOT}/.secrets/env.sh" ]]; then
    # shellcheck disable=SC1091
    source "${REPO_ROOT}/.secrets/env.sh"
  else
    echo "Error: TS_UNIFI_API_KEY unset and ${REPO_ROOT}/.secrets/env.sh missing." >&2
    echo "Run scripts/bootstrap-secrets.sh (after pass-cli login)." >&2
    exit 1
  fi
fi

export UNIFI_DNS_RECORDS_ROOT="${UNIFI_DNS_RECORDS_ROOT:-${DEFAULT_RECORDS_ROOT}}"

exec python3 "${SCRIPT_DIR}/unifi-dns-reconcile.py" "$@"
