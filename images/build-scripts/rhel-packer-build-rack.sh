#!/bin/bash
git config --global --add safe.directory $PWD
export git_curr_dir=$(git rev-parse --show-toplevel)

if [ -z "${TS_PROXMOX_PACKER_APIKEY:-}" ]; then
  if [ -f "$git_curr_dir/.secrets/env.sh" ]; then
    . "$git_curr_dir/.secrets/env.sh"
  else
    echo "Error: TS_* env vars unset and $git_curr_dir/.secrets/env.sh missing." >&2
    echo "Run scripts/bootstrap-secrets.sh (after pass-cli login)." >&2
    exit 1
  fi
fi
export PKR_VAR_service_passwd="${TS_WIN_TURNERANS_SVC_PASSWD}"
export PKR_VAR_proxmox_user="${TS_PROXMOX_PACKER_USER}"
export PKR_VAR_proxmox_apikey="${TS_PROXMOX_PACKER_APIKEY}"
export PKR_VAR_ssh_private_key_file="${TS_TURNERANS_SVC_SSH_PRIVKEY}"

/usr/bin/packer init -var "ansible_provisioner_playbook_path=deployment/linux-packer-config.yml" -var-file=$git_curr_dir/turner-services-sensitive-repo/provisioning-base-install-sensitive-rack.auto.pkrvars.hcl $git_curr_dir/images/rhel-image-build-packer-on-proxmox/.
/usr/bin/packer validate -var "ansible_provisioner_playbook_path=deployment/linux-packer-config.yml" -var-file=$git_curr_dir/turner-services-sensitive-repo/provisioning-base-install-sensitive-rack.auto.pkrvars.hcl $git_curr_dir/images/rhel-image-build-packer-on-proxmox/.
/usr/bin/packer build -force -var "ansible_provisioner_playbook_path=deployment/linux-packer-config.yml" -var-file=$git_curr_dir/turner-services-sensitive-repo/provisioning-base-install-sensitive-rack.auto.pkrvars.hcl $git_curr_dir/images/rhel-image-build-packer-on-proxmox/.
