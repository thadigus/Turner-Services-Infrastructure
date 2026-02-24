# Deployment Directory

This directory contains code necessary for deployment of machines using Ansible and Terraform.

### services/

Workload-specific Ansible playbook directories live at the repository root:

- `services/github-runner-vm/`
- `services/k8s-cluster/primary/`
- `services/k8s-cluster/test/`

### deploy-turnerans_svc.yml

A simple Ansible playbook to deploy the Turner Services Ansible service account to any machine by utilizing the role in `/roles/deploy-ansible` along with a simple ping test to ensure operability. This can be ran by any workstation with valid and privileged credentials to configure any of the machines for Ansible management. A different playbook, but the same role is also used on provision with Packer, so any Packer managed images should already have the service account present and therefore should not require this playbook's use.

```bash
# Sample command to run this playbook against given system.
```

### linux-packer-config.yml

Ansible playbook to be ran against hosts after provisioning process with Packer before they are saved to templates to be deployed with Terraform.

### base-config-pulumi.yml

Runs the OS-appropriate base-config role against all Proxmox VMs tagged
`pulumi`:
- `linux-base-config` for `tag_linux` VMs
- `windows-base-config` for `tag_windows` VMs

```bash
ansible-playbook -i turner-services-sensitive-repo/inventories/ansible-inv-rack.proxmox.yml deployment/base-config-pulumi.yml
```
