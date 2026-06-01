# Turner Services Infrastructure

Home-lab IaC for a Proxmox-backed environment. Everything that runs is described in this repo (or its sensitive submodule) and converges via Ansible / Pulumi / Helmfile, driven by self-hosted GitHub Actions runners.

## Layout

- `images/` — Packer templates for Proxmox VM base images (Ubuntu, RHEL, Windows, Kali) plus the `iac-runner` and `in-cluster-dev` container images.
- `deployment/` — Pulumi (Proxmox VM provisioning) and base-config Ansible playbooks.
- `roles/` — Ansible roles applied after provisioning. See **Role file structure** below.
- `collections/` — Ansible collection requirements.
- `services/` — Ansible playbooks, cluster bootstrap helpers, and generic deployment plumbing. Private workload catalogs live in the sensitive submodule. See [services/README.md](services/README.md).
- `scripts/` — Dispatchers: `run-k8s-app.sh` for Helmfile, etc.
- `.github/workflows/` — CI for image builds, base configuration, and environment convergence.
- `turner-services-sensitive-repo/` — submodule with secrets, kubeconfigs, server lists, SSH keys.
- `.devcontainer/` — VSCodium dev container based on the `iac-runner` image.

## Operating model

| Layer | Tool | Trigger |
| --- | --- | --- |
| VM network identity + Proxmox provisioning | Pulumi (`deployment/pulumi-proxmox`) | Manual workflow dispatch |
| Base OS config | Ansible (`deployment/base-config-pulumi.yml`) | Daily cron + manual |
| Workload bootstrap (K8s cluster, runners) | Ansible (`services/<name>/site.yml`) | Manual via `services/run-service-playbook.sh` |
| Cluster workload convergence | Helmfile private catalog | Push/manual/scheduled convergence |
| Container images (devcontainer, in-cluster-dev) | Docker build | Sunday 22:00 UTC + manual |
| Packer VM images (Ubuntu, RHEL, Windows, Kali) | Packer | Monday 04:30 UTC + manual |

## UniFi DNS and DHCP

VM-owned DNS and DHCP reservations are managed by the Pulumi stack in `deployment/pulumi-proxmox`. The server list defines the VM, VLAN, optional IP reservation, and optional DNS records; Pulumi creates UniFi resources before creating the Proxmox VM with the same MAC address. UniFi console connection details live in `turner-services-sensitive-repo/unifi-consoles.yml`.

## Role file structure

- `defaults/` — default variables for the role
- `files/` — static files the role copies to remote hosts
- `handlers/` — handlers triggered by tasks
- `meta/` — role dependency declarations
- `tasks/` — `main.yml` and any included task files
- `templates/` — Jinja templates rendered onto remote hosts
- `tests/` — playbook-based role tests
- `vars/` — role-scoped variables
