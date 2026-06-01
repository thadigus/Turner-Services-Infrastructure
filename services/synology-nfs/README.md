# Synology NFS

Manage Synology shared folders and DSM-native NFS permissions from declarative YAML.

Desired state lives in:

```bash
turner-services-sensitive-repo/nas/shares-prod.yml
```

Preview drift with Ansible check mode:

```bash
services/run-service-playbook.sh \
  --service synology-nfs \
  --inventory turner-services-sensitive-repo/inventories/servers.yml \
  --check -- --diff
```

Apply changes:

```bash
services/run-service-playbook.sh \
  --service synology-nfs \
  --inventory turner-services-sensitive-repo/inventories/servers.yml
```

Each share declares the NAS host that owns it with `hosts`. The owning NAS creates the shared folder and manages NFS permissions through DSM's native `SYNO.Core.FileServ.NFS.SharePrivilege` API, so permissions remain visible in the DSM UI. Shares can also declare `hyper_backup.replicate_to` and `hyper_backup.schedule` to record the intended daily peer backup relationship.

Current share definitions are intentionally kept in the sensitive manifest rather than duplicated in public docs.

Hyper Backup desired state is recorded as metadata in the manifest. This role does not yet create or modify Hyper Backup tasks.
