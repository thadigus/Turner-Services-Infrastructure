#!/bin/bash
export git_curr_dir=$(git rev-parse --show-toplevel)
# Ensure your host agent is running and has keys
eval "$(ssh-agent)"            # if not auto-started by your OS
ssh-add -L || ssh-add ~/.ssh/*_rsa

# Capture host UID/GID for proper socket access
export docker_UID="$(id -u)"; export docker_GID="$(id -g)"

pulumienv_args=()
prompt_env() {
  local var_name="$1"
  local prompt_text="$2"
  local secret="${3:-false}"

  if [[ -n "${!var_name}" ]]; then
    return 0
  fi

  if [[ "$secret" == "true" ]]; then
    read -r -s -p "$prompt_text" "${var_name}"
    echo
  else
    read -r -p "$prompt_text" "${var_name}"
  fi
}

prompt_env "PULUMI_BACKEND_URL" "Pulumi backend URL (leave empty for default): "
prompt_env "PULUMI_ACCESS_TOKEN" "Pulumi access token (leave empty for local backend): " true
prompt_env "PULUMI_CONFIG_PASSPHRASE" "Pulumi config passphrase (leave empty to skip): " true
export PULUMI_STACK="${PULUMI_STACK:-ts-proxmox-test}"
export TS_SERVER_LIST_PATH="${TS_SERVER_LIST_PATH:-../../turner-services-sensitive-repo/server-list-test.yml}"

for pulumi_var in PULUMI_ACCESS_TOKEN PULUMI_BACKEND_URL PULUMI_CONFIG_PASSPHRASE PULUMI_PASSPHRASE PULUMI_STACK TS_SERVER_LIST_PATH; do
  if [[ -n "${!pulumi_var}" ]]; then
    pulumienv_args+=("-e" "${pulumi_var}=${!pulumi_var}")
  fi
done

if bash -c 'docker images | grep iac-runner'; then
  echo 'Image found locally, proceeding with run...'
else
  echo 'Image not found, building image...'
  docker build --build-arg UID="$docker_UID" --build-arg GID="$docker_GID" -t iac-runner:latest -f $git_curr_dir/images/iac-runner/Dockerfile .
fi

docker run --rm -it --network host -v "$SSH_AUTH_SOCK:/ssh-agent" -e SSH_AUTH_SOCK=/ssh-agent -v ./:/workspace "${pulumienv_args[@]}" iac-runner:latest
