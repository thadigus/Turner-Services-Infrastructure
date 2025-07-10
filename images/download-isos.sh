#!/bin/bash
export git_curr_dir=$(git rev-parse --show-toplevel)
docker run --rm -it --network=host -v $git_curr_dir/:/code iac-runner bash -c "cd /code; ansible-playbook /code/images/download-isos.yml"
