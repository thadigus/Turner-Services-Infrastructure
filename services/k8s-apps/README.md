# services/k8s-apps

Helmfile-managed workloads for `ts-main-test` and `ts-main-prod`.

```
helmfile.yaml             # all releases
environments/             # per-cluster values (hostnames, LB range, PVC sizes)
values/                   # per-release values files
raw/                      # local chart for emitting plain manifests
```

Releases are labeled `layer=platform` or `layer=apps` — use `--layer` to scope.

## Prerequisites

- `turner-services-sensitive-repo/k8s-vars.yml`: `k8s_kube_test_vip_address` set (required for kube-vip on test).
- `turner-services-sensitive-repo/cloudflare-dns01-token.txt`: Cloudflare token, scope `Zone:Zone:Read` + `Zone:DNS:Edit` on `turnerservices.cloud`.
- `turner-services-sensitive-repo/code-server-password.txt`: code-server login password.
- `TS_UNIFI_API_KEY`: required for prod homepage rendering; test falls back to a placeholder when unset.

## Commands

```bash
scripts/run-k8s-app.sh bootstrap --env test          # namespaces + storage + secrets
scripts/run-k8s-app.sh sync      --env test          # first install (no pre-diff)
scripts/run-k8s-app.sh diff      --env test          # preview drift
scripts/run-k8s-app.sh apply     --env test          # idempotent converge

# Scope to one layer:
scripts/run-k8s-app.sh apply --env test --layer platform
scripts/run-k8s-app.sh apply --env test --layer apps
```

## DNS

Internal hostnames are served by UniFi. Static vanity records for prod ingress-backed services are managed by the Pulumi UniFi stack in `turner-services-sensitive-repo/server-list-prod.yml` and should point at the prod ingress-nginx LoadBalancer IP:

```
kubectl --context ts-main-prod -n platform get svc ingress-nginx-controller
```

Cloudflare zone is only used for ACME `_acme-challenge.*` TXT records.

## Adding an app

1. New file in `values/<name>.yaml.gotmpl` — a `resources:` list of plain manifests.
2. New release in `helmfile.yaml` with `chart: ./raw`, `labels: { layer: apps }`.
3. Per-env values in `environments/{test,prod}.yaml.gotmpl`.
4. `apply --env test`, add/update Pulumi UniFi DNS records when a prod vanity hostname is needed, validate, then `apply --env prod`.

## CI

Single workflow: `.github/workflows/k8s-apps.yml`.

| Trigger | Target |
| --- | --- |
| Push to non-`main` branch (touching `services/k8s-apps/**` or `scripts/run-k8s-app.sh`) | apply to test |
| Push to `main` | apply to prod |
| Daily cron 14:00 UTC | apply to prod (drift correction) |
| Manual `workflow_dispatch` | env of your choice + optional bootstrap |

Concurrency is serialised on a single `k8s-apps` group, so test and prod runs never overlap.
