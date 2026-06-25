# Services

Per-workload IaC. Two flavours live here:

1. **Ansible playbooks** (`*/site.yml`) for one-time-ish workload bootstrap (K8s cluster, GitHub runner VMs). Dispatched by `run-service-playbook.sh`.
2. **K8s app dispatcher** (`../scripts/run-k8s-app.sh`) for ongoing cluster workloads. The private Helmfile catalog lives in the sensitive submodule; this repo keeps only generic helper plumbing. See [k8s-apps/README.md](k8s-apps/README.md).

## Layout

- `github-runner-vm/` — GitHub Actions runner VM configuration.
- `proxmox-backup-server/` — Proxmox Backup Server VM configuration.
- `synology-nfs/` — Synology shared folder and NFS export management.
- `k8s-cluster/production/` — production K8s cluster (3 hybrid control + 2 workers, HA via kube-vip 10.0.3.5).
- `k8s-cluster/test/` — test K8s cluster (1 control + 1 worker, kube-vip 10.0.3.10).
- `k8s-cluster/{production,test}-teardown/` — destructive reset.
- `k8s-cluster/cluster-bootstrap.yml` — shared playbook imported by the per-cluster `site.yml` files.
- `k8s-apps/` — generic raw-manifest helper chart used by the private cluster workload catalog.

## Host naming

| Workload | Hostname pattern |
| --- | --- |
| GitHub runners | `gha-runner-*` |
| Proxmox Backup Server | `pbs-primary-*` |
| Prod K8s control | `k8s-control-*` |
| Prod K8s workers | `k8s-worker-*` |
| Test K8s control | `k8s-test-control-*` |
| Test K8s workers | `k8s-test-worker-*` |

## Ansible dispatcher

```bash
services/run-service-playbook.sh                                # interactive menu
services/run-service-playbook.sh --list
services/run-service-playbook.sh --service github-runner-vm
services/run-service-playbook.sh --service synology-nfs -i turner-services-sensitive-repo/inventories/servers.yml --check -- --diff
services/run-service-playbook.sh --service k8s-cluster/test
services/run-service-playbook.sh --service k8s-cluster/production
services/run-service-playbook.sh --service k8s-cluster/test-teardown
```

## Helmfile dispatcher

```bash
scripts/run-k8s-app.sh bootstrap --env test         # one-time per cluster
scripts/run-k8s-app.sh apply     --env test
scripts/run-k8s-app.sh diff      --env prod
scripts/run-k8s-app.sh apply     --env prod --layer apps
```
