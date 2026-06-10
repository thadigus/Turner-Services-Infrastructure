#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
K8S_APPS_DIR="${TS_K8S_APPS_DIR:-${REPO_ROOT}/turner-services-sensitive-repo/k8s-apps}"
LOCAL_SECRETS_ENV="${REPO_ROOT}/.secrets/env.sh"

if [[ -f "${LOCAL_SECRETS_ENV}" ]]; then
  # shellcheck disable=SC1091
  source "${LOCAL_SECRETS_ENV}"
elif [[ -z "${TS_KUBECONFIG_DIR:-}" ]]; then
  echo "Error: TS_* env vars unset and ${LOCAL_SECRETS_ENV} missing." >&2
  echo "Run scripts/bootstrap-secrets.sh (after pass-cli login)." >&2
  exit 1
fi


usage() {
  cat <<USAGE
Usage: scripts/run-k8s-app.sh <subcommand> --env {test|prod} [options]

Subcommands:
  bootstrap   run catalog-specific namespace and secret bootstrap
  diff        helmfile diff
  apply       helmfile apply
  sync        helmfile sync
  destroy     helmfile destroy

Options:
  -e, --env <test|prod>      Target cluster (required)
  -l, --layer <name>           Limit to one scaffold layer, e.g. 1-namespaces
  -h, --help                 Show this help
USAGE
}

die() { echo "Error: $*" >&2; exit 1; }

SUBCMD="${1:-}"
[[ -z "${SUBCMD}" ]] && { usage >&2; exit 1; }
shift || true

ENV_NAME=""
LAYER=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -e|--env)   ENV_NAME="${2:-}"; shift 2 ;;
    -l|--layer) LAYER="${2:-}";   shift 2 ;;
    -h|--help)  usage; exit 0 ;;
    *)          die "Unknown argument: $1" ;;
  esac
done

case "${SUBCMD}" in
  bootstrap|diff|apply|sync|destroy) ;;
  -h|--help|"") usage; exit 0 ;;
  *) die "Unknown subcommand: ${SUBCMD}" ;;
esac

[[ -z "${ENV_NAME}" ]] && die "--env is required (test or prod)"
case "${ENV_NAME}" in test|prod) ;; *) die "--env must be 'test' or 'prod'";; esac
# Any non-empty layer is passed through as a Helmfile label selector.

CONTEXT="ts-main-${ENV_NAME}"

# Avoid merging test/prod kubeconfigs; their authinfo names collide.
if [[ -n "${TS_KUBECONFIG_DIR:-}" ]]; then
  export KUBECONFIG="${TS_KUBECONFIG_DIR}/${CONTEXT}.conf"
fi
[[ -n "${KUBECONFIG:-}" ]] || die "KUBECONFIG is unset and TS_KUBECONFIG_DIR is unavailable"
[[ "${KUBECONFIG}" != *:* ]] || die "KUBECONFIG must resolve to one target file for this script, got a multi-file value"
[[ -f "${KUBECONFIG}" ]] || die "kubeconfig not found at ${KUBECONFIG}"

bootstrap() {
  echo "==> Bootstrapping ${CONTEXT}"

  local bootstrap_hook="${K8S_APPS_DIR}/bootstrap.sh"
  if [[ -x "${bootstrap_hook}" ]]; then
    "${bootstrap_hook}" "${CONTEXT}" "${REPO_ROOT}"
  else
    echo "    !! ${bootstrap_hook} missing or not executable; skipping catalog-specific bootstrap"
  fi

  echo "==> Bootstrap complete"
}
run_helmfile() {
  local args=(-e "${ENV_NAME}" -f "${K8S_APPS_DIR}/helmfile.yaml")
  [[ -n "${LAYER}" ]] && args+=(-l "layer=${LAYER}")
  echo "==> helmfile ${args[*]} $*"
  helmfile "${args[@]}" "$@"
}

sync_namespaces() {
  local args=(-e "${ENV_NAME}" -f "${K8S_APPS_DIR}/helmfile.yaml" -l layer=1-namespaces)
  echo "==> helmfile ${args[*]} sync"
  helmfile "${args[@]}" sync
}

prepare_for_converge() {
  sync_namespaces
  bootstrap
}

check_cluster_auth() {
  kubectl --context "${CONTEXT}" get --raw /version >/dev/null 2>&1 \
    || die "Kubernetes auth check failed for ${CONTEXT} using KUBECONFIG=${KUBECONFIG}. Re-run scripts/bootstrap-secrets.sh if the kubeconfig is stale."
}

check_cluster_auth

case "${SUBCMD}" in
  bootstrap) bootstrap ;;
  diff)      run_helmfile diff ;;
  # Fresh clusters may not have CRDs before cert-manager installs.
  apply)
    prepare_for_converge
    run_helmfile apply --skip-diff-on-install
    ;;
  sync)
    prepare_for_converge
    run_helmfile sync
    ;;
  destroy)   run_helmfile destroy ;;
esac
