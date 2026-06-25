# Proxmox Backup Server Autoinstall ISO

This directory prepares a Proxmox Backup Server autoinstall ISO. Pulumi then creates `pbs-primary-01` directly from that ISO; there is no intermediate Packer template.

## Flow

1. `images/download-isos.yml` downloads the official PBS ISO into `NFS-TempStorage`.
2. `prepare-pbs-autoinstall-iso.yml` runs on a reachable Proxmox host, validates a sensitive `answer.toml`, and writes `proxmox-backup-server-autoinstall.iso` back to `NFS-TempStorage`.
3. Pulumi creates `pbs-primary-01` with that ISO attached on `ide2`, a blank `scsi0` disk, and boot order `scsi0`, then `ide2`. The first boot falls through to the ISO; later boots use the installed disk and avoid an install loop.
4. Run Pulumi with `--skip-base-config` for the first install so Ansible does not race the PBS installer.
5. After the VM has booted from disk, run base config and then `services/proxmox-backup-server` to configure datastore retention, GC, and verification jobs.

## Sensitive Answer File

Create this file outside the public tree:

```bash
mkdir -p turner-services-sensitive-repo/proxmox-backup-server
cp images/proxmox-backup-server-autoinstall/answer.toml.EXAMPLE   turner-services-sensitive-repo/proxmox-backup-server/answer.toml
```

Then replace:

- `root-password-hashed` with a real hashed root password.
- `root-ssh-keys` with the public key that should be allowed for first boot.

## Prepare The ISO

```bash
images/build-scripts/pbs-prepare-autoinstall-iso-rack.sh
```

Override the answer file path when testing variants:

```bash
PBS_AUTOINSTALL_ANSWER_FILE=/path/to/answer.toml images/build-scripts/pbs-prepare-autoinstall-iso-rack.sh
```

The prepared ISO is expected at:

```text
/mnt/pve/NFS-TempStorage/template/iso/proxmox-backup-server-autoinstall.iso
```

Pulumi boots it through Proxmox as:

```text
NFS-TempStorage:iso/proxmox-backup-server-autoinstall.iso
```

The first-boot hook installs SSH, qemu guest agent, Python, and LVM utilities so Ansible roles can connect reliably after installation.

## CI Refresh

`.github/workflows/iso-refresh.yml` runs daily on the self-hosted runner. It refreshes the official ISO set and prepares `proxmox-backup-server-autoinstall.iso` when `turner-services-sensitive-repo/proxmox-backup-server/answer.toml` exists.

The official PBS ISO download tracks the latest ISO published at `https://enterprise.proxmox.com/iso/` and pins the downloaded file with the SHA256 value from that index.
