# Pulumi Proxmox VM Deployment

This directory contains a Pulumi program that provisions Proxmox VMs from a YAML
server list. It supports template cloning, disk sizing (including resize after
clone), and basic input validation.

## Requirements

- Pulumi CLI
- Python 3.9+
- Proxmox VE API access (password or API token)

## Quick Start

1) Initialize a Pulumi project in this directory:

```
pulumi new -d "Proxmox IaC deployment for Turner Services" -n "ts-proxmox" -s "ts-proxmox" --dir ./deployment/pulumi-proxmox/ --force python
```

2) Create and activate a virtual environment, then install dependencies:

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r ../../requirements.txt
```

3) Configure Proxmox access (choose one auth method):

```
pulumi config set proxmox:endpoint https://<pve-host>:8006
pulumi config set --secret proxmox:apiToken <user>!<tokenid>=<secret>
```

or

```
pulumi config set proxmox:endpoint https://<pve-host>:8006
pulumi config set --secret proxmox:password <password>
```

4) (Optional) point at custom server list and inventory files:

```
pulumi config set serverListPath ../../turner-services-sensitive-repo/server-list-prod.yml
pulumi config set inventoryPath ../../turner-services-sensitive-repo/inventories/ansible-inv-rack.proxmox.yml
```

5) Preview and deploy:

```
pulumi up
```

## Interactive Deploy Script

Use the helper script to choose `test`, `production`, or `both`:

```bash
./run-pulumi-up.sh
```

To run `pulumi up` instead of preview:

```bash
./run-pulumi-up.sh -u
```

To run `pulumi destroy`:

```bash
./run-pulumi-up.sh -d
```

For CI/non-interactive runs:

```bash
./run-pulumi-up.sh --test
./run-pulumi-up.sh --prod
./run-pulumi-up.sh --both
./run-pulumi-up.sh --both -u
./run-pulumi-up.sh --test -d
```

Behavior:

- Accepts target flags: `--test`, `--prod`/`--production`, `--both`
- Prompts for deployment target only if no target flag is provided
- Sets per-stack `serverListPath`
- Sets per-stack `environment` (used for VM tags)
- Runs `pulumi preview` for the selected stack(s) by default
- Runs `pulumi up --yes` when `-u`/`--up` is provided
  - After each successful `up`, runs:
    - `ansible-playbook -i <inventory> ../base-config-pulumi.yml --limit tag_pulumi:&tag_<environment>`
    - `<environment>` is `test` or `production` based on the selected stack
  - After base config, reboots only Linux VMs with meaningful Pulumi VM changes
    (`created`/`updated`/`replaced`) by running:
    - `ansible-playbook -i <inventory> ../reboot-linux-hosts.yml --limit tag_linux:&tag_<environment>:&<changed_vm_names>`
- Runs `pulumi destroy --yes` when `-d`/`--destroy` is provided

Optional stack-name overrides:

- `PULUMI_TEST_STACK=<your-test-stack>`
- `PULUMI_PROD_STACK=<your-prod-stack>`

## Configuration Files

The program looks for these paths by default, in order:

- Server list:
- `../../turner-services-sensitive-repo/server-list-prod.yml`
  - `../server-list.example.yml`
- Inventory (for endpoint, user, and token info):
  - `../../turner-services-sensitive-repo/inventories/ansible-inv-rack.proxmox.yml`
  - `../../inventories/ansible-inv-example.proxmox.yml`

You can override these with Pulumi config values:

- `serverListPath`
- `inventoryPath`
- `environment` (`production` or `test`) for VM tagging
You can also override the server list via env var `TS_SERVER_LIST_PATH`, which
is useful for local/dev runs.

## VM Tags

All VMs created by this Pulumi program are tagged with:

- `pulumi`
- `production` for production stacks
- `test` for test stacks
- `linux` or `windows` based on VM metadata (`vm_type`/`os_type`, template name, or VM name)

Environment is resolved from (in order):

1) `pulumi config set environment production|test`
2) stack name (`pulumi stack`)
3) server-list filename (`server-list-prod.yml` / `server-list-test.yml`)

## Server List Schema (YAML)

Top-level keys:

- `template_node`: Proxmox node where templates live
- `virtual_machines`: list of VM definitions

VM fields (common):

- `name` (required)
- `prox_node` (required) - target Proxmox node
- `storage_location` - target datastore
- `cpu_count` (default 1)
- CPU model is enforced to `x86-64-v3` for deployed VMs
- `ram_amount` (MB, default 512)
- `vlan` (optional)
- `start_on_boot` (default true)
- `vm_state` (present/absent, default present)
- `vm_type` or `os_type` (optional) - use `windows` for Windows tagging; defaults to Linux when unspecified

Template clone fields:

- `template_name` (required for clone)
- `disk_amount` (GB, optional) - resizes the primary disk after clone; must be >= template size
- `disk_interface` (default `scsi0`) - interface to resize
- `storage_location` (optional) - target datastore. If set and you want to keep the template size, still set
  `disk_amount` to the template size to avoid the provider defaulting to 8G during clone moves.

ISO-based (non-template) fields:

- `disk_amount` (GB)

Storage plan fields:

- `storage_plan` list entries with:
  - `lv` (mountpoint, for example `/var`)
  - `expand_by` (relative growth amount, for example `10G`)

### Disk Size Validation

- If `disk_amount` is omitted but a `storage_plan` exists, the VM disk size is
  auto-calculated as `40G + sum(expand_by)` (migration-safe default).
- If a `storage_plan` total exceeds `disk_amount`, the deployment fails fast.

## Notes

- Template disk resize assumes the primary disk interface is `scsi0`. Override
  with `disk_interface` if your template uses `virtio0`, `sata0`, etc.
- The program explicitly clears the default CD-ROM device (`ide3`). Proxmox may
  still show an empty CD-ROM slot; removing the device entirely requires a
  post-provision `qm set <vmid> -delete ide3` on the node.
- Proxmox reports disk speed defaults after creation; the program ignores
  `disks[0].speed` to avoid persistent diffs while still allowing disk size
  changes.
- `storage_plan` is consumed by `roles/linux-base-config` during post-provision
  configuration. The role infers backing VG/PV from each LV mountpoint, grows
  partition -> PV -> LV -> filesystem, then records a marker so each expansion
  runs only once per host/entry.
