#!/bin/bash
export PKR_VAR_build_passwd=$(tr -dc A-Za-z0-9 < /dev/urandom | head -c 13; echo);
export git_curr_dir=$(git rev-parse --show-toplevel)
/usr/bin/packer init -var "ansible_provisioner_playbook_path=deployment/windows-packer-config.yml" -var-file=$git_curr_dir/turner-services-sensitive-repo/provisioning-base-install-sensitive-rack.auto.pkrvars.hcl $git_curr_dir/images/windows-image-build-packer-on-proxmox/.
/usr/bin/packer validate -var "ansible_provisioner_playbook_path=deployment/windows-packer-config.yml" -var-file=$git_curr_dir/turner-services-sensitive-repo/provisioning-base-install-sensitive-rack.auto.pkrvars.hcl $git_curr_dir/images/windows-image-build-packer-on-proxmox/.
/usr/bin/packer build -force -var "ansible_provisioner_playbook_path=deployment/windows-packer-config.yml" -var-file=$git_curr_dir/turner-services-sensitive-repo/provisioning-base-install-sensitive-rack.auto.pkrvars.hcl $git_curr_dir/images/windows-image-build-packer-on-proxmox/.
