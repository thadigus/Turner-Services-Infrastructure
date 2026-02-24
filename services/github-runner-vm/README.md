# GitHub Runner VM Config

This playbook directory is for configuring the GitHub Actions runner VM(s).

## Default host selector

The `site.yml` playbook currently targets VM names matching `gha-runner-*`.

## Security Default

The runner container is configured to run unprivileged:

- Systemd service runs as a dedicated non-root host user (default: `gha-runner`)
- Container runs as non-root user using `--user <uid>:<gid>` for the service account
- `RUN_AS_ROOT=false` is set in the container environment
- Runner is started with supplemental host Docker group access so non-root jobs can use `/var/run/docker.sock`

## Image Build

This playbook builds a local runner image on each target host instead of using
a public prebuilt image. During `docker build`, the Dockerfile:

- queries `https://api.github.com/repos/actions/runner/releases/latest`
- resolves the latest runner release tag
- downloads that runner tarball
- runs `./bin/installdependencies.sh`
- installs Docker CLI for `docker build/login/push` workflows
- installs latest Docker Buildx plugin for `docker buildx build --push`

Default image tag used by the playbook: `local/github-actions-runner:latest`.

This supports CI jobs that:

- build and push container images (Docker Hub, GHCR, etc.)
- run `container:` jobs
- launch your existing dependency-heavy Packer container workflows via Docker

For `container:` jobs, runner data is mounted at the same absolute path on host
and in the runner container (`/opt/github-runner/data`). This is required when
the runner uses the host Docker socket so job-container bind mounts (including
`/__e` for action runtimes like Node) resolve correctly.

## Nightly Maintenance

The playbook adds (without overwriting existing crontabs) two root cron entries:

- `02:15` nightly: rebuild runner image from latest upstream release metadata, then restart `github-actions-runner.service`
- `02:45` nightly: `docker system prune -af --volumes` and `docker builder prune -af`

Logs are written to:

- `/var/log/gha-runner-rebuild.log`
- `/var/log/gha-runner-prune.log`

## Storage Preparation

Before image build, the playbook attempts to grow `/var` if:

- `/var` is on an LVM logical volume, and
- the volume group has free extents

It then grows the filesystem (`xfs` or `ext*`) accordingly.  
Set `GHA_RUNNER_EXPAND_VAR_LV=false` to disable this behavior.

## Run

```bash
ansible-playbook \
  -i turner-services-sensitive-repo/inventories/ansible-inv-rack.proxmox.yml \
  services/github-runner-vm/site.yml
```

## Required Input

The playbook needs a repository URL and (for first-time registration) a runner
registration token. It reads them from environment variables first and prompts
if they are missing:

- `GHA_RUNNER_REPOSITORY_URL` (example: `https://github.com/org/repo`)
- `GHA_RUNNER_TOKEN`

Example non-interactive run (CI-friendly):

```bash
GHA_RUNNER_REPOSITORY_URL=https://github.com/org/repo \
GHA_RUNNER_TOKEN=xxxxxxxx \
./services/run-service-playbook.sh --service github-runner-vm
```

## Optional Input

- `GHA_RUNNER_IMAGE` (default: `local/github-actions-runner:latest`)
- `GHA_RUNNER_EXPAND_VAR_LV` (default: `true`)
- `GHA_RUNNER_LABELS` (default: `self-hosted,linux,docker`)
- `GHA_RUNNER_GROUP` (default: `Default`)
- `GHA_RUNNER_WORKDIR` (default: `_work`)
- `GHA_RUNNER_NAME_PREFIX` (prepended to the VM hostname for runner name)
- `GHA_RUNNER_SERVICE_USER` (default: `gha-runner`)
- `GHA_RUNNER_SERVICE_GROUP` (default: `gha-runner`)
- `GHA_RUNNER_UID` (optional: only set when you want to pin a specific UID)
- `GHA_RUNNER_GID` (optional: only set when you want to pin a specific GID)
- `GHA_RUNNER_CONTAINER_USER` (optional override; default auto-resolves to service account `<uid>:<gid>`)
