#!/bin/bash
export git_curr_dir=$(git rev-parse --show-toplevel)
/usr/bin/packer init -var "ansible_provisioner_playbook_path=deployment/linux-packer-config.yml" -var-file=$git_curr_dir/turner-services-sensitive-repo/provisioning-base-install-sensitive-office.auto.pkrvars.hcl $git_curr_dir/images/rhel-image-build-packer-on-proxmox/.
/usr/bin/packer validate -var "ansible_provisioner_playbook_path=deployment/linux-packer-config.yml" -var-file=$git_curr_dir/turner-services-sensitive-repo/provisioning-base-install-sensitive-office.auto.pkrvars.hcl $git_curr_dir/images/rhel-image-build-packer-on-proxmox/.
/usr/bin/packer build -force -var "ansible_provisioner_playbook_path=deployment/linux-packer-config.yml" -var-file=$git_curr_dir/turner-services-sensitive-repo/provisioning-base-install-sensitive-office.auto.pkrvars.hcl $git_curr_dir/images/rhel-image-build-packer-on-proxmox/.
