# in-cluster-dev

Web-based VSCodium (code-server) container image with the full Turner Services IaC toolchain (kubectl, helm, helmfile, ansible, pulumi, packer) layered on top of `lscr.io/linuxserver/code-server`.


## Build

CI builds this weekly via `.github/workflows/image-builds.yml` and pushes to:

```
ghcr.io/thadigus/turner-services-infrastructure:in-cluster-dev
```

Local build:

```bash
docker build -t in-cluster-dev:local -f images/in-cluster-dev/Dockerfile .
```

The build context is the **repo root** (not this directory) because the Dockerfile copies `requirements.txt`, `collections/requirements.yml`, and `deployment/pulumi-proxmox/requirements.txt`.

## Runtime

- linuxserver s6 init drops to user `abc` (PUID/PGID env vars override).
- `/config` is the persistent home; mount a PVC there.
- `HELM_PLUGINS=/usr/local/share/helm/plugins` so `helm-diff` is visible without per-user reinstall.
- Authentication is via `PASSWORD` env var (set by Helm release from a bootstrapped secret).
