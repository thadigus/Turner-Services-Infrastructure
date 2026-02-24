#!/usr/bin/env bash
set -euo pipefail

RUNNER_HOME="/home/runner/actions-runner"
RUNNER_DIST="/opt/actions-runner-dist"

required_vars=(RUNNER_NAME RUNNER_WORKDIR)
for var_name in "${required_vars[@]}"; do
  if [[ -z "${!var_name:-}" ]]; then
    echo "Missing required environment variable: ${var_name}" >&2
    exit 1
  fi
done

mkdir -p "${RUNNER_HOME}"

if [[ ! -x "${RUNNER_HOME}/config.sh" ]]; then
  cp -a "${RUNNER_DIST}/." "${RUNNER_HOME}/"
fi

cd "${RUNNER_HOME}"

if [[ ! -f ".runner" ]]; then
  if [[ -z "${RUNNER_REPOSITORY_URL:-}" ]]; then
    echo "RUNNER_REPOSITORY_URL is required for first-time runner registration." >&2
    exit 1
  fi

  if [[ -z "${RUNNER_TOKEN:-}" ]]; then
    echo "RUNNER_TOKEN is required for first-time runner registration." >&2
    exit 1
  fi

  ./config.sh \
    --unattended \
    --url "${RUNNER_REPOSITORY_URL}" \
    --token "${RUNNER_TOKEN}" \
    --name "${RUNNER_NAME}" \
    --work "${RUNNER_WORKDIR}" \
    --labels "${RUNNER_LABELS:-self-hosted,linux,docker}" \
    --runnergroup "${RUNNER_GROUP:-Default}" \
    --replace
fi

exec ./run.sh
