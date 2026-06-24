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

### proxmox-host-config.yml

Configures Proxmox VE host-level settings that are outside VM provisioning. It
enforces home-lab apt repository policy by disabling enterprise repositories
and enabling `pve-no-subscription`. It also configures Proxmox node
Wake-on-LAN metadata and keeps WoL enabled on selected physical NICs.

For Optiplex hosts (`prox2`-`prox4`), Proxmox can wake powered-off nodes from
the web UI/API once `wakeonlan` is configured. The 1 GbE NIC is used for wake
packets; production traffic can still prefer the 10 GbE bond member after boot.
For Dell hosts (`prox5`/`prox6`), iDRAC Redfish endpoints are recorded in
inventory for out-of-band power automation.

```bash
ansible-playbook -i turner-services-sensitive-repo/inventories/network.yml deployment/proxmox-host-config.yml --limit prox2,prox3,prox4,prox6
```

