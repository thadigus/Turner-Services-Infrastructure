#!/bin/bash
export PKR_VAR_build_passwd_local=$(openssl passwd -6 "$(openssl rand -base64 64)");
export git_curr_dir=$(git rev-parse --show-toplevel)
/usr/bin/packer init -var "ansible_provisioner_playbook_path=deployment/linux-packer-config.yml" -var-file=$git_curr_dir/turner-services-sensitive-repo/provisioning-base-install-sensitive-rack.auto.pkrvars.hcl $git_curr_dir/images/ubuntu-image-build-packer-on-proxmox/.
/usr/bin/packer validate -var "ansible_provisioner_playbook_path=deployment/linux-packer-config.yml" -var-file=$git_curr_dir/turner-services-sensitive-repo/provisioning-base-install-sensitive-rack.auto.pkrvars.hcl $git_curr_dir/images/ubuntu-image-build-packer-on-proxmox/.
/usr/bin/packer build -force -var "ansible_provisioner_playbook_path=deployment/linux-packer-config.yml" -var-file=$git_curr_dir/turner-services-sensitive-repo/provisioning-base-install-sensitive-rack.auto.pkrvars.hcl $git_curr_dir/images/ubuntu-image-build-packer-on-proxmox/.
