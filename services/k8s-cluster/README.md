# Kubernetes Cluster Config

This directory contains cluster-specific Ansible playbooks:

- `primary/`: production or primary cluster configuration.
- `test/`: test cluster configuration used to validate changes before promotion.

Both use a shared bootstrap playbook:

- `cluster-bootstrap.yml`: kubeadm + containerd setup, cluster init/join, CNI install, and baseline security controls.

## Security Notes

- Workload namespaces are enforced with Pod Security Admission `restricted` labels.
- Kubernetes node daemons (`kubelet`, `containerd`) and core control-plane components still require root-level host privileges by Kubernetes design.
- Production playbook is configured for `kube-vip` (no external LB required), but you must provide `K8S_KUBEVIP_ADDRESS`.
