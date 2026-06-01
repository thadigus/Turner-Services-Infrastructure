# K8s App Helper

The public tree intentionally keeps only the generic helper chart used by the private Helmfile catalog. The actual release list, environment values, image tags, hostnames, storage mappings, backup notes, and app-specific restore helpers live under `turner-services-sensitive-repo/k8s-apps/`.

```text
services/k8s-apps/raw/                 # generic chart that emits raw Kubernetes manifests
turner-services-sensitive-repo/k8s-apps/ # private Helmfile catalog and per-environment values
```

## Commands

```bash
scripts/run-k8s-app.sh bootstrap --env test
scripts/run-k8s-app.sh diff      --env test
scripts/run-k8s-app.sh apply     --env prod --layer apps
```

`TS_K8S_APPS_DIR` can override the private catalog path when testing another checkout.

## Adding Workloads

Add or update workload-specific Helmfile releases, values, docs, and restore helpers in the sensitive catalog. Keep this public directory limited to reusable chart plumbing and non-sensitive operational notes.

## CI

The public workflow is `.github/workflows/environment-converge.yml`. It checks out the sensitive submodule, prepares credentials through the sensitive CI hook, and runs `scripts/run-k8s-app.sh` against the private catalog.
