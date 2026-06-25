# Pulumi Proxmox + UniFi VM Deployment

This directory contains one Pulumi stack that provisions UniFi network identity
first, then Proxmox VMs from the same YAML server list. UniFi can manage DHCP
reservations and static DNS records for a VM before Proxmox creates it with the
same MAC address.

## Requirements

- Pulumi CLI
- Python 3.9+
- Proxmox VE API access (password or API token)
- UniFi Network API access for managed DNS/DHCP reservations

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

4) Configure UniFi access. By default, the program reads
`../../turner-services-sensitive-repo/unifi-consoles.yml` and the API key
environment variable named there, usually `TS_UNIFI_API_KEY`.

You can also configure it directly:

```
pulumi config set unifi:apiUrl https://<unifi-host>
pulumi config set unifi:site default
pulumi config set --secret unifi:apiKey <api-key>
```

5) (Optional) point at custom server list and inventory files:

```
pulumi config set serverListPath ../../turner-services-sensitive-repo/server-list-prod.yml
pulumi config set inventoryPath ../../turner-services-sensitive-repo/inventories/ansible-inv-rack.proxmox.yml
```

6) Preview and deploy:

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
- `unifiEnabled` (`true` by default; set `false` only when no VM in the server list requests UniFi resources)
- `unifi:apiUrl`, `unifi:apiKey`, `unifi:site`, `unifi:console`, `unifi:consolesPath`, `unifi:allowInsecure`

You can also set `TS_SERVER_LIST_PATH` for local/dev runs when `serverListPath`
is not configured on the selected stack. Stack config takes precedence so prod
cannot accidentally inherit a shell override.

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
- `template_vm_ids` or `template_ids`: optional map of template name to VM ID; use this to avoid live template discovery during previews
- `dns_domain`: optional default domain used when a VM sets `auto_dns: true`
- `unifi_networks`: optional map of VLAN ID to UniFi network name or ID for DHCP reservations
- `dns_records`: optional top-level UniFi static DNS records not tied to a VM
- `virtual_machines`: list of VM definitions

VM fields (common):

- `name` (required)
- `prox_node` (required) - target Proxmox node
- `storage_location` - target datastore
- `cpu_count` (default 1)
- CPU model is enforced to `x86-64-v3` for deployed VMs
- `ram_amount` (MB, default 512)
- `vlan` (optional) - VLAN tag for the default Proxmox NIC. Existing VMs use this shorthand.
- `network_devices` (optional) - explicit Proxmox NIC list. Defaults to one enabled `virtio` NIC on `vmbr0`, with `vlan` and `mac_address` inherited from the VM when set.
- `mac_address` (optional) - sets the first Proxmox NIC MAC. If omitted on a VM with `ip_address` and no `dhcp_mac_address`, Pulumi deterministically creates one from the stack and VM name.
- `dhcp_mac_address` or `reservation_mac_address` (optional) - MAC used only for the UniFi DHCP reservation; useful for existing VMs where Pulumi should not touch the NIC.
- `ip_address` or `fixed_ip` (optional) - enables a UniFi DHCP reservation for this VM
- `dns_name`, `dns_names`, or `dns_records` (optional) - creates UniFi static DNS records
- `auto_dns` (optional) - creates `<name>.<dns_domain>` as an A record pointing at `ip_address`
- `unifi_network` / `unifi_network_id` / `network_id` (optional) - UniFi network name or ID for the reservation; otherwise `unifi_networks[vlan]` is used when present
- `start_on_boot` (default true)
- `vm_state` (present/absent, default present)
- `vm_type` or `os_type` (optional) - use `windows` for Windows tagging; defaults to Linux when unspecified

Network device fields:

- `bridge` (default `vmbr0`) - Proxmox bridge to attach the VM NIC to
- `model` (default `virtio`) - Proxmox NIC model
- `vlan` or `vlan_id` (optional) - VLAN tag on the VM NIC; inherits VM-level `vlan` when omitted
- `mac_address` or `mac` (optional) - NIC MAC; the first NIC inherits VM-level `mac_address` when omitted
- `firewall` (default `false`) - enable the Proxmox firewall interface pair for this NIC only when needed
- `enabled` (default `true`)
- `disconnected` (default `false`)
- `mtu`, `queues`, `trunks` (optional) - advanced Proxmox NIC settings

Template clone fields:

- `template_name` (required for clone)
- `disk_amount` (GB, optional) - resizes the primary disk after clone; must be >= template size
- `disk_interface` (default `scsi0`) - interface to resize
- `storage_location` (optional) - target datastore. If set and you want to keep the template size, still set
  `disk_amount` to the template size to avoid the provider defaulting to 8G during clone moves.

ISO-based (non-template) fields:

- `disk_amount` (GB)

ISO installer fields:

- `iso_file`, `boot_iso`, or `iso_path` - Proxmox ISO file ID, for example `NFS-TempStorage:iso/proxmox-backup-server-autoinstall.iso`
- `cdrom_interface` (default `ide2`) - CD-ROM interface for the installer ISO
- `boot_orders` or `boot_order` - ordered boot devices. For unattended installers, prefer disk first then CD-ROM, for example `[scsi0, ide2]`, so first boot falls through to the ISO and later boots use the installed disk.

Storage plan fields:

- `storage_plan` list entries with:
  - `lv` (mountpoint, for example `/var`)
  - `expand_by` (relative growth amount, for example `10G`)

UniFi example:

```yaml
template_node: prox4
template_vm_ids:
  ubuntu-base-image: 998
dns_domain: turnerservices.cloud
unifi_networks:
  3: Servers

dns_records:
  - name: app-alias.turnerservices.cloud
    type: A
    value: 10.0.x.xx

virtual_machines:
  - name: app-01
    template_name: ubuntu-base-image
    prox_node: prox3
    storage_location: NFS-ProdVolRepl
    cpu_count: 2
    ram_amount: 4096
    vlan: 3
    network_devices:
      - bridge: vmbr0
        model: virtio
        vlan: 3
        firewall: false
    ip_address: 10.0.x.xx
    auto_dns: true
    dns_records:
      - name: app.turnerservices.cloud
        type: A
    storage_plan:
      - lv: /var
        expand_by: 20G
```

For that VM Pulumi creates `unifi:iam/user:User` first, using `dhcp_mac_address`
when present or the VM NIC MAC otherwise, then creates any `unifi:dns/record:Record`
entries. New VMs can use `mac_address` to set the Proxmox NIC; existing VMs can
use `dhcp_mac_address` to reserve their current MAC without changing the VM.

### Disk Size Validation

- If `disk_amount` is omitted but a `storage_plan` exists, the VM disk size is
  auto-calculated as `40G + sum(expand_by)` (migration-safe default).
- If a `storage_plan` total exceeds `disk_amount`, the deployment fails fast.

## Proxmox HA

The server list can declare Proxmox HA placement groups and resources. The
current Proxmox API has migrated from legacy HA groups to HA rules, so Pulumi
uses a small dynamic resource to create each VM HA resource plus a strict
`node-affinity` rule. Placement is still preserved in Pulumi state instead of
being hand-configured in the UI.

Example:

```yaml
ha_groups:
  - name: ha-example-vm
    nodes:
      prox4: 100
      prox3: 80
      prox6: 60
    restricted: true
    no_failback: true
    comment: Example strict node-affinity policy

ha_resources:
  - resource_id: vm:112
    vm_name: k8s-control-01
    group: ha-example-vm
    state: started
    max_restart: 1
    max_relocate: 2
    comment: HA restart on shared storage
```

Use one placement group per service when you want to preserve preferred
placement and spread. `restricted: true` is rendered as a strict node-affinity
rule, preventing HA from starting a VM on nodes outside the listed active
compute set. `no_failback: true` is rendered as `failback 0` on the HA resource,
avoiding automatic churn when a more-preferred node comes back online; rebalance
intentionally with `ha-manager crm-command migrate` during maintenance windows.

Only add VMs backed entirely by shared storage. VMs with local disks, host-only
USB dependencies, or active Proxmox locks should be excluded until those
constraints are resolved.

Recommended rack policy:

- Keep `prox3`, `prox4`, and `prox6` as the active compute HA set.
- Keep `prox2` online as the low-power quorum/helper node.
- Keep `prox5` powered down unless extra capacity or maintenance staging is
  needed.
- Do not use `802.3ad` unless the switch ports are explicitly configured as an
  LACP port-channel.

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
