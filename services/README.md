# Services

This directory contains playbooks that configure workload-specific systems after VM provisioning and base configuration.

## Layout

- `github-runner-vm/`: GitHub Actions runner VM workload configuration.
- `k8s-cluster/primary/`: Primary Kubernetes cluster workload configuration.
- `k8s-cluster/test/`: Test Kubernetes cluster workload configuration for safe change validation.

## Host Naming Patterns

These playbooks target inventory hostnames by VM name patterns:

- GitHub Actions runner VMs: `gha-runner-*`
- Primary Kubernetes control-plane nodes: `k8s-control-*`
- Primary Kubernetes worker nodes: `k8s-worker-*`
- Test Kubernetes control-plane nodes: `k8s-test-control-*`
- Test Kubernetes worker nodes: `k8s-test-worker-*`

## Runner Script

Use `services/run-service-playbook.sh` to run service playbooks locally and in CI.

Examples:

```bash
# Interactive menu (no args)
services/run-service-playbook.sh

# Non-interactive by service (CI-friendly)
services/run-service-playbook.sh --service github-runner-vm
services/run-service-playbook.sh --service k8s-cluster/primary
services/run-service-playbook.sh --service k8s-cluster/test

# List available service names
services/run-service-playbook.sh --list
```
