# Kubernetes Cluster Config

Cluster-specific Ansible playbooks for the production and test clusters. Both invoke a shared bootstrap playbook (`cluster-bootstrap.yml`) that handles kubeadm + containerd setup, control-plane init/join, CNI install, and baseline security controls.

## Layout

- `production/` — primary cluster (3 hybrid control + 2 workers, HA via kube-vip).
- `test/` — test cluster (1 control + 1 worker, single-master, no VIP).
- `production-teardown/`, `test-teardown/` — clean-slate teardown wrappers around `teardown.yml`.
- `cluster-bootstrap.yml` — the shared bootstrap playbook.
- `teardown.yml` — destructive reset (kubeadm reset + state wipe + iptables flush).

## Production Topology

- 3 control-plane nodes (`k8s-control-01..03`) registered with `nodeRegistration.taints: []` — they run workloads alongside the control plane (hybrid scheduling).
- 2 dedicated worker nodes (`k8s-worker-01..02`).
- `kube-vip` static pods on every control node provide ARP-mode VIP failover for the API server. VIP is set via `k8s_kube_prod_vip_address` in `turner-services-sensitive-repo/k8s-vars.yml`; `controlPlaneEndpoint` is the DNS name `k8s-control-prod.turnerservices.cloud` that resolves to that VIP.
- `kube-vip` image is pinned via `K8S_KUBE_VIP_VERSION` (default `v0.8.7`).

## Idempotency

The bootstrap playbook is fully idempotent. A successful run followed by an immediate replay produces zero `changed` results on cluster state. Specifically:

- `kubeadm init` only runs when `/etc/kubernetes/admin.conf` does not exist on the first control host. If it exists but the apiserver is not Ready, the play fails loudly rather than auto-resetting — recover via `teardown.yml`, then retry.
- `kubeadm join` (control or worker) only runs when `/etc/kubernetes/kubelet.conf` is absent or the node is not yet `Ready` in `kubectl get nodes`.
- Token and certificate-key regeneration always run but use `changed_when: false`.
- Calico apply, namespace creation, PSA labels all use idempotent operations.

## Dynamic Scaling

**Add a node.** Edit `turner-services-sensitive-repo/server-list-{prod,test}.yml`, provision the VM, then replay the bootstrap:

```bash
services/run-service-playbook.sh --service k8s-cluster/production
```

The new node will be prepared, kube-vip placed (if control), and joined. Existing nodes are no-ops. `serial: 1` on the control-plane play keeps etcd member additions sequential.

**Remove a node.** Drain and delete first, then remove from the YAML and replay:

```bash
kubectl drain <node> --ignore-daemonsets --delete-emptydir-data
kubectl delete node <node>
# For control nodes only, after the node is gone:
#   kubectl -n kube-system exec etcd-<other-control> -- \
#     etcdctl --endpoints=https://127.0.0.1:2379 \
#     --cert=/etc/kubernetes/pki/etcd/server.crt \
#     --key=/etc/kubernetes/pki/etcd/server.key \
#     --cacert=/etc/kubernetes/pki/etcd/ca.crt \
#     member remove <member-id>
```

Then remove the VM entry from the server list and replay. The playbook does NOT auto-delete K8s `Node` objects based on inventory diff — a typo in the inventory must not nuke a production node.

## Teardown

```bash
services/run-service-playbook.sh --service k8s-cluster/production-teardown
services/run-service-playbook.sh --service k8s-cluster/test-teardown
```

This is the only path that performs destructive operations (`kubeadm reset`, state wipe, iptables flush). The bootstrap playbook never does.

## Security

- `default` and `workloads` namespaces carry Pod Security Admission `restricted` enforce/audit/warn labels.
- API server runs with `Node,RBAC` authorization and the `NodeRestriction` + `PodSecurity` admission plugins.
- Controller-manager and scheduler have profiling disabled.
- Kubelet runs with `protectKernelDefaults`, `serverTLSBootstrap`, `rotateCertificates`, and `readOnlyPort: 0`.
- UFW restricts cluster-traffic ports (`6443`, `2379-2380`, `10250`, `10256`, `30000:32767`) to the cluster subnet `10.0.3.0/24`.

## Required Variables

Defined in `turner-services-sensitive-repo/k8s-vars.yml`:

| Variable | Description |
|---|---|
| `k8s_kube_prod_control_endpoint` | DNS:port for the prod apiserver behind the VIP. |
| `k8s_kube_prod_vip_address` | kube-vip ARP VIP for the prod control plane. |
| `k8s_kube_prod_pod_subnet` | Pod CIDR (prod). |
| `k8s_kube_prod_service_subnet` | Service CIDR (prod). |
| `k8s_kube_test_control_endpoint` | DNS:port for the test apiserver (no VIP — points at the single control node). |
| `k8s_kube_test_pod_subnet` | Pod CIDR (test). |
| `k8s_kube_test_service_subnet` | Service CIDR (test). |

Optional environment variables:

| Var | Default | Purpose |
|---|---|---|
| `K8S_CHANNEL_VERSION` | `1.35` | apt repo channel for kubelet/kubeadm/kubectl. |
| `K8S_PAUSE_IMAGE` | `registry.k8s.io/pause:3.10` | containerd sandbox image. |
| `K8S_KUBE_VIP_VERSION` | `v0.8.7` | kube-vip image tag pinned on control nodes. |

### Recovery bootstrap overrides

When the sorted first control-plane host is unavailable or intentionally being rebuilt,
run the bootstrap playbook with an explicit healthy source control node and join endpoint:

```bash
services/run-service-playbook.sh --service k8s-cluster/production \
  --limit k8s-control-02:k8s-control-03 -- \
  -e k8s_bootstrap_primary_control_host=k8s-control-03 \
  -e k8s_bootstrap_join_endpoint=10.0.3.121:6443
```

`k8s_bootstrap_primary_control_host` controls where token/cert material and verification commands run.
`k8s_bootstrap_join_endpoint` lets new members join through a known-good API server when the kube-vip endpoint is not yet available.
