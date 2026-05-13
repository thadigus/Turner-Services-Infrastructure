# Services

Playbooks that configure workload-specific systems after VM provisioning and base configuration.

## Layout

- `github-runner-vm/` — GitHub Actions runner VM workload configuration.
- `k8s-cluster/production/` — production Kubernetes cluster bootstrap (3 hybrid control + 2 workers, HA via kube-vip).
- `k8s-cluster/test/` — test Kubernetes cluster bootstrap (single control + worker).
- `k8s-cluster/production-teardown/`, `k8s-cluster/test-teardown/` — destructive reset of the named cluster.

## Host Naming Patterns

Playbooks target inventory hostnames by VM-name glob:

- GitHub Actions runner VMs: `gha-runner-*`
- Production Kubernetes control-plane: `k8s-control-*`
- Production Kubernetes workers: `k8s-worker-*`
- Test Kubernetes control-plane: `k8s-test-control-*`
- Test Kubernetes workers: `k8s-test-worker-*`

## Runner Script

```bash
services/run-service-playbook.sh                                # interactive menu
services/run-service-playbook.sh --list                         # list services
services/run-service-playbook.sh --service github-runner-vm
services/run-service-playbook.sh --service k8s-cluster/production
services/run-service-playbook.sh --service k8s-cluster/test
services/run-service-playbook.sh --service k8s-cluster/production-teardown
services/run-service-playbook.sh --service k8s-cluster/test-teardown
```
