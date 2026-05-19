# Turner Services Infrastructure

Home-lab IaC for a Proxmox-backed environment. Everything that runs is described in this repo (or its sensitive submodule) and converges via Ansible / Pulumi / Helmfile, driven by self-hosted GitHub Actions runners.

## Layout

- `images/` — Packer templates for Proxmox VM base images (Ubuntu, RHEL, Windows, Kali) plus the `iac-runner` and `in-cluster-dev` container images.
- `deployment/` — Pulumi (Proxmox VM provisioning) and base-config Ansible playbooks.
- `roles/` — Ansible roles applied after provisioning. See **Role file structure** below.
- `collections/` — Ansible collection requirements.
- `services/` — Per-workload Ansible playbooks (GitHub runners, K8s cluster bootstrap) and the Helmfile-managed K8s app catalog. See [services/README.md](services/README.md).
- `scripts/` — Dispatchers: `run-k8s-app.sh` for Helmfile, etc.
- `.github/workflows/` — CI: image builds, scheduled base config, scheduled K8s app reconciliation, PR diff for K8s changes.
- `turner-services-sensitive-repo/` — submodule with secrets, kubeconfigs, server lists, SSH keys.
- `.devcontainer/` — VSCodium dev container based on the `iac-runner` image.

## Operating model

| Layer | Tool | Trigger |
| --- | --- | --- |
| Proxmox VM provisioning | Pulumi (`deployment/pulumi-proxmox`) | Manual workflow dispatch |
| Base OS config | Ansible (`deployment/base-config-pulumi.yml`) | Daily cron + manual |
| Workload bootstrap (K8s cluster, runners) | Ansible (`services/<name>/site.yml`) | Manual via `services/run-service-playbook.sh` |
| K8s app deploys | Helmfile (`services/k8s-apps/`) | Push to non-`main` → test; push to `main` → prod; daily cron → prod |
| UniFi static DNS | `scripts/unifi-dns-reconcile.py` | Push to `main` + daily cron (drift) + manual dispatch |
| Container images (devcontainer, in-cluster-dev) | Docker build | Sunday 22:00 UTC + manual |
| Packer VM images (Ubuntu, RHEL, Windows, Kali) | Packer | Monday 04:30 UTC + manual |

## UniFi DNS

Static DNS records on UniFi consoles are reconciled from YAML in the sensitive submodule by `scripts/unifi-dns-reconcile.py`. The YAML is the full state — anything in UniFi but not in YAML is deleted on apply.

```
turner-services-sensitive-repo/unifi-dns/
  consoles.yml              # console registry (URL + API key env + API version)
  <console>/<site>.yml      # records for that (console, site) — one file per site
```

Common commands (from repo root, after `scripts/bootstrap-secrets.sh`):

```bash
scripts/unifi-dns-reconcile.sh --list-sites           # discover sites on each console
scripts/unifi-dns-reconcile.sh --export main/default  # dump current UniFi state as YAML
scripts/unifi-dns-reconcile.sh --check                # plan only; no writes
scripts/unifi-dns-reconcile.sh                        # apply
```

CI is `.github/workflows/unifi-dns.yml`. Under `GITHUB_ACTIONS=true` the script emits `::add-mask::` directives for every record name, IP, controller URL, and site identifier so they render as `***` in workflow logs.

## Role file structure

- `defaults/` — default variables for the role
- `files/` — static files the role copies to remote hosts
- `handlers/` — handlers triggered by tasks
- `meta/` — role dependency declarations
- `tasks/` — `main.yml` and any included task files
- `templates/` — Jinja templates rendered onto remote hosts
- `tests/` — playbook-based role tests
- `vars/` — role-scoped variables
