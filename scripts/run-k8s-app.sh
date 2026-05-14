#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
K8S_APPS_DIR="${REPO_ROOT}/services/k8s-apps"
SENSITIVE_DIR="${REPO_ROOT}/turner-services-sensitive-repo"

LOCAL_PATH_PROVISIONER_VERSION="${LOCAL_PATH_PROVISIONER_VERSION:-v0.0.30}"
LOCAL_PATH_PROVISIONER_URL="https://raw.githubusercontent.com/rancher/local-path-provisioner/${LOCAL_PATH_PROVISIONER_VERSION}/deploy/local-path-storage.yaml"

usage() {
  cat <<USAGE
Usage: scripts/run-k8s-app.sh <subcommand> --env {test|prod} [options]

Subcommands:
  bootstrap   create namespaces, install local-path-provisioner, load secrets
  diff        helmfile diff
  apply       helmfile apply
  sync        helmfile sync
  destroy     helmfile destroy

Options:
  -e, --env <test|prod>      Target cluster (required)
  -l, --layer <platform|apps>  Limit to one release layer
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
[[ -n "${LAYER}" ]] && case "${LAYER}" in platform|apps) ;; *) die "--layer must be 'platform' or 'apps'";; esac

CONTEXT="ts-main-${ENV_NAME}"

if [[ -z "${KUBECONFIG:-}" ]]; then
  export KUBECONFIG="${SENSITIVE_DIR}/kubeconfigs/${CONTEXT}.conf"
fi
[[ -f "${KUBECONFIG%%:*}" ]] || die "kubeconfig not found at ${KUBECONFIG%%:*}"

bootstrap() {
  echo "==> Bootstrapping ${CONTEXT}"

  kubectl --context "${CONTEXT}" apply -f - <<'NS'
apiVersion: v1
kind: Namespace
metadata:
  name: platform
  labels:
    pod-security.kubernetes.io/enforce: baseline
    pod-security.kubernetes.io/enforce-version: latest
    pod-security.kubernetes.io/warn: baseline
---
apiVersion: v1
kind: Namespace
metadata:
  name: apps
  labels:
    pod-security.kubernetes.io/enforce: baseline
    pod-security.kubernetes.io/enforce-version: latest
    pod-security.kubernetes.io/warn: baseline
NS

  kubectl --context "${CONTEXT}" apply -f "${LOCAL_PATH_PROVISIONER_URL}"
  kubectl --context "${CONTEXT}" patch storageclass local-path \
    -p '{"metadata":{"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}' \
    || true

  local cf_token_file="${SENSITIVE_DIR}/cloudflare-dns01-token.txt"
  local cs_password_file="${SENSITIVE_DIR}/code-server-password.txt"

  if [[ -f "${cf_token_file}" ]]; then
    if grep -q REPLACE_WITH_CLOUDFLARE_API_TOKEN "${cf_token_file}"; then
      echo "    !! ${cf_token_file} still has placeholder content"
    else
      kubectl --context "${CONTEXT}" -n platform create secret generic cloudflare-api-token \
        --from-file=api-token="${cf_token_file}" \
        --dry-run=client -o yaml | kubectl --context "${CONTEXT}" apply -f -
    fi
  else
    echo "    !! ${cf_token_file} missing"
  fi

  if [[ -f "${cs_password_file}" ]]; then
    kubectl --context "${CONTEXT}" -n apps create secret generic code-server-password \
      --from-file=password="${cs_password_file}" \
      --dry-run=client -o yaml | kubectl --context "${CONTEXT}" apply -f -
  else
    echo "    !! ${cs_password_file} missing"
  fi

  echo "==> Bootstrap complete"
}

run_helmfile() {
  local args=(-e "${ENV_NAME}" -f "${K8S_APPS_DIR}/helmfile.yaml")
  [[ -n "${LAYER}" ]] && args+=(-l "layer=${LAYER}")
  echo "==> helmfile ${args[*]} $*"
  helmfile "${args[@]}" "$@"
}

case "${SUBCMD}" in
  bootstrap) bootstrap ;;
  diff)      run_helmfile diff ;;
  # --skip-diff-on-install lets apply work on a fresh cluster where some
  # releases reference CRDs that don't exist yet (cluster-issuer-le before
  # cert-manager has installed the CRDs in the same run).
  apply)     run_helmfile apply --skip-diff-on-install ;;
  sync)      run_helmfile sync ;;
  destroy)   run_helmfile destroy ;;
esac
