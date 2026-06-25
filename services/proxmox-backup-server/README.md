# Proxmox Backup Server

This service configures the PBS VM created by `deployment/pulumi-proxmox`.

Prerequisite: prepare `NFS-TempStorage:iso/proxmox-backup-server-autoinstall.iso` with `images/build-scripts/pbs-prepare-autoinstall-iso-rack.sh`, then let Pulumi create the VM directly from that ISO.

## Deploy

1. Build the VM:

```bash
images/download-isos.sh
images/build-scripts/pbs-prepare-autoinstall-iso-rack.sh
cd deployment/pulumi-proxmox
./run-pulumi-up.sh --prod -u --skip-base-config
```

2. After the PBS installer finishes and the VM boots from disk, apply base config to the new host:

```bash
ansible-playbook -i turner-services-sensitive-repo/inventories/ansible-inv-rack.proxmox.yml deployment/base-config-pulumi.yml --limit 'pbs-primary-01'
```

3. Apply the PBS service role:

```bash
services/run-service-playbook.sh --service proxmox-backup-server
```

The default endpoint is `https://pbs.turnerservices.cloud:8007`.

## HA Model

Proxmox Backup Server does not provide an active-active clustered datastore
model. The supported resilient pattern is independent PBS nodes with datastore
sync jobs. For Turner Services, keep `pbs-primary-01` as the write target and
add a future `pbs-secondary-01` on separate storage or hardware as a pull-sync
replica.

Recommended next step for HA:

- Add `pbs-secondary-01` on a different Proxmox node and datastore.
- Configure a restricted API token on `pbs-primary-01`.
- Configure a remote and pull sync job on `pbs-secondary-01`.
- Point Proxmox VE backup storage at `pbs-primary-01`; promote the secondary
  manually during a primary outage.
