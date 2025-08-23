#!/bin/bash
export git_curr_dir=$(git rev-parse --show-toplevel)
# Ensure your host agent is running and has keys
eval "$(ssh-agent)"            # if not auto-started by your OS
ssh-add -L || ssh-add ~/.ssh/*_rsa

# Capture host UID/GID for proper socket access
export docker_UID="$(id -u)"; export docker_GID="$(id -g)"

if bash -c 'docker images | grep iac-runner'; then
  echo 'Image found locally, proceeding with run...'
else
  echo 'Image not found, building image...'
  docker build --build-arg UID="$docker_UID" --build-arg GID="$docker_GID" -t iac-runner:latest -f $git_curr_dir/images/iac-runner/Dockerfile .
fi

docker run --rm -it --network host -v "$SSH_AUTH_SOCK:/ssh-agent" -e SSH_AUTH_SOCK=/ssh-agent -v ./:/workspace iac-runner:latest