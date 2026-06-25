# Proxmox Network Performance Plan

## Current Inventory

Survey date: 2026-06-23

All Proxmox nodes currently use one VLAN-aware bridge, `vmbr0`, with management
on `vmbr0.2` and the default route through `10.0.2.1`. Corosync, management,
VM bridge traffic, NFS storage, and default live migration traffic all share
that logical path today.

Storage endpoints currently in use:

- Synology NFS: `10.0.2.6`
- Proxmox Backup Server: `10.0.3.146`

`/etc/pve/datacenter.cfg` does not currently define a dedicated migration
network.

| Node | Current physical links | 10G available | Current concern |
| --- | --- | --- | --- |
| `prox2` | `eno1` 1G up, `enp3s0f0`/`enp3s0f1` 10G down | Dual-port Intel X540 10GBase-T | 10G NICs are not linked or used |
| `prox3` | `eno1` 1G up, `enp1s0` 10G up, `enp3s0f0`/`enp3s0f1` 1G down | Intel 82599ES SFP+ 10G | 1G and 10G links are mixed in one LACP bond |
| `prox4` | `eno1` 1G up, `enp1s0` 10G up, `enp3s0f0`/`enp3s0f1` 1G down | Intel 82599ES SFP+ 10G | 1G and 10G links are mixed in one LACP bond |
| `prox5` | `eno1`/`eno2` 1G up | None detected | Dual 1G only |
| `prox6` | `eno1`/`eno2` 1G up | None detected | Dual 1G only |

## EdgeSwitch 16 XG Notes

The 10G switch is a Ubiquiti EdgeSwitch 16 XG at `10.0.2.4`. Treat it as
the 10G aggregation switch for storage, migration, and high-throughput VM
traffic.

Recommended switch-side goals:

- Use dedicated VLANs for traffic classes rather than one flat shared path.
- Configure LACP only when the matching host bond uses only same-speed links.
- Keep 1G and 10G links out of the same LACP group.
- Enable jumbo frames only on a dedicated storage/migration VLAN after verifying
  the full path supports the selected MTU end to end.
- Label ports by host and NIC role before making changes.

Important: LACP does not generally mean one flow can use the sum of all member
links. It hashes flows across links. For NFS, PBS, and live migration, a single
large flow may still use only one member link. Use 10G routing and service
endpoint selection for predictable performance.

## Target Design

Use role-specific networks instead of trying to put every NIC into one bond.

| Traffic | Target path | Rationale |
| --- | --- | --- |
| Proxmox management UI/API/SSH | Existing VLAN 2 on stable 1G or 10G bridge | Keep operational access simple and reliable |
| Corosync | Existing management path, or a small dedicated VLAN later | Corosync values low jitter more than high bandwidth |
| NFS datastore traffic | Dedicated 10G storage VLAN/subnet where available | Keeps VM disk IO and backups off management |
| PBS backup traffic | Dedicated 10G storage/backup VLAN/subnet where available | Backup throughput should prefer fastest host-to-storage path |
| Live migration | Dedicated 10G migration VLAN/subnet where available | Avoids migrations saturating management/VM traffic |
| VM guest traffic | Existing `vmbr0` VLAN-aware bridge, with optional 10G-backed uplinks | Guest placement can benefit from 10G without coupling storage and management |

Suggested initial VLAN/subnet model:

| Purpose | Example VLAN | Example subnet | Notes |
| --- | --- | --- | --- |
| Management | 2 | Existing `10.0.2.0/24` | Keep current gateway and node management IPs |
| Storage / backup | TBD | Example `10.0.20.0/24` | Synology, PBS, and 10G-capable Proxmox hosts |
| Live migration | TBD | Example `10.0.21.0/24` | Proxmox hosts only; no default gateway needed |

Final VLAN IDs and subnets should match the broader network plan before
implementation.

## Host-Specific Recommendations

### `prox2`

- Patch at least one Intel X540 10GBase-T port to the EdgeSwitch 16 XG.
- Do not leave `bond0` as single-member LACP if the switch is not configured
  for LACP.
- Preferred target:
  - Keep `eno1` for management fallback.
  - Use one or both X540 ports for storage/migration/VM traffic.
  - If both X540 ports are connected, use a 10G-only LACP bond or split them
    into separate storage and migration interfaces.

### `prox3` and `prox4`

- Remove mixed-speed links from the current LACP bond.
- Preferred target:
  - Use `enp1s0` 10G SFP+ for storage/migration.
  - Keep `eno1` 1G for management fallback, or as active-backup secondary only.
  - Leave disconnected `enp3s0f0`/`enp3s0f1` out of the active bond until
    cabled and assigned a clear purpose.

### `prox5` and `prox6`

- These appear to be dual-1G hosts.
- If LACP is desired, configure matching LAGs on the EdgeSwitch or access
  switch; otherwise use active-backup for simpler failover.
- They can still participate in the storage/migration VLAN at 1G if the switch
  path allows it, but they will remain throughput-limited compared to 10G hosts.

## No-Physical-Changes Plan

This is the best near-term path when cabling cannot be changed but switch and
host configuration can be adjusted.

### Immediate Objective

Make the current links deterministic:

- 10G-capable hosts should prefer their working 10G link.
- Same-speed dual-1G hosts can use real LACP only if the EdgeSwitch ports are
  configured as matching LAGs.
- Mixed 1G/10G LACP should be removed or avoided; it does not provide reliable
  fastest-link preference.

### Switch-Side Work

1. Map live switch ports
   - Identify EdgeSwitch ports for `prox3` `enp1s0`, `prox4` `enp1s0`, and any
     `prox5`/`prox6` 1G uplinks attached to the EdgeSwitch.
   - Record current VLAN tagging, link speed, STP state, and LAG membership.

2. Standardize host-facing VLANs
   - Keep Proxmox host ports as trunks carrying at least VLAN 2 for management
     and VLAN 3 for production VMs.
   - Preserve any additional VM VLANs already used by the environment.

3. Fix LACP expectations
   - Do not create a LAG that mixes 1G and 10G ports.
   - For `prox3` and `prox4`, keep the 10G and 1G switch ports as standalone
     trunk ports unless the host config is changed to a same-speed bond.
   - For `prox5` and `prox6`, either configure proper two-port LACP LAGs on the
     switch to match their current `802.3ad` host bonds, or plan to change the
     host bonds to active-backup.

4. Reliability tuning
   - Enable edge/portfast behavior on Proxmox-facing switch ports where the
     switch supports it.
   - Keep BPDU guard or equivalent loop protection enabled if available.
   - Do not enable jumbo frames until every endpoint on the path, including
     Proxmox, Synology, PBS, and the switch VLAN, is configured and tested.
   - Do not enable flow-control as a blind optimization; measure first because
     pause frames can create head-of-line blocking.

### Host-Side Work Without Cabling

The safest host-side cleanup is to replace broken or mixed-speed LACP with
`active-backup` where we want deterministic primary-link selection.

Recommended near-term host intent:

| Node | Bond mode | Primary | Reason |
| --- | --- | --- | --- |
| `prox2` | `active-backup` or single-link | `eno1` | Only linked interface today; 10G ports are down |
| `prox3` | `active-backup` | `enp1s0` | Prefer working 10G SFP+ link, fall back to 1G `eno1` |
| `prox4` | `active-backup` | `enp1s0` | Prefer working 10G SFP+ link, fall back to 1G `eno1` |
| `prox5` | real LACP or `active-backup` | TBD | Dual 1G only; choose based on switch LAG support |
| `prox6` | real LACP or `active-backup` | TBD | Dual 1G only; choose based on switch LAG support |

For `prox3` and `prox4`, this should improve reliability and keep traffic on
10G during normal operation. For `prox5` and `prox6`, real LACP may improve
aggregate multi-flow throughput but will not make a single flow exceed 1G.


### No-Cabling Decision Matrix

| Node | Switch-only action | Host-side action | Expected result |
| --- | --- | --- | --- |
| `prox2` | Verify existing 1G port is a VLAN trunk; no 10G gain possible while X540 links are down | Keep current linked 1G path or simplify away from single-member LACP | Reliability cleanup only |
| `prox3` | Ensure 1G and 10G ports are standalone trunks, not members of the same LAG | Convert bond to `active-backup` with `enp1s0` as primary and `eno1` as backup | Normal traffic uses 10G with 1G failover |
| `prox4` | Ensure 1G and 10G ports are standalone trunks, not members of the same LAG | Convert bond to `active-backup` with `enp1s0` as primary and `eno1` as backup | Normal traffic uses 10G with 1G failover |
| `prox5` | If both links terminate on the EdgeSwitch, create a two-port LACP LAG carrying the same trunk VLANs | Keep `802.3ad`, or convert to `active-backup` if switch LAG is not possible | LACP can improve aggregate multi-flow 1G throughput; active-backup improves predictability |
| `prox6` | If both links terminate on the EdgeSwitch, create a two-port LACP LAG carrying the same trunk VLANs | Keep `802.3ad`, or convert to `active-backup` if switch LAG is not possible | LACP can improve aggregate multi-flow 1G throughput; active-backup improves predictability |

Switch trunk requirements for current Proxmox config:

- VLAN 2 must remain tagged to the Proxmox host ports because management lives
  on `vmbr0.2`.
- VLAN 3 must remain tagged for production VMs.
- Preserve any other VM VLANs currently carried by the host ports.
- Do not make VLAN 2 untagged/native unless the Proxmox host config changes at
  the same time.

Near-term avoid list:

- Do not configure a switch LAG containing both 1G and 10G links.
- Do not enable jumbo frames on the shared management/VM path yet.
- Do not move corosync to a new network during this cleanup.
- Do not rely on LACP as fastest-link selection; use active-backup primary
  selection or dedicated routing for that.

### Validation

After each change:

- Confirm `cat /proc/net/bonding/bond0` shows the intended active slave or real
  LACP partner information.
- Confirm `ip route get 10.0.2.6` and `ip route get 10.0.3.146` choose the
  expected interface path.
- Watch `rx_bytes` and `tx_bytes` on physical NICs during NFS, PBS, and live
  migration tests.
- Verify Proxmox cluster quorum and that all VMs remain reachable.


## Implemented Changes

### 2026-06-24: `prox2`/`prox3`/`prox4` Active-Backup Cleanup

Changed `bond0` on `prox2`, `prox3`, and `prox4` from unhealthy/mixed
`802.3ad` LACP to deterministic `active-backup` mode. Backups were created on
each node at:

```text
/etc/network/interfaces.pre-active-backup-20260624
```

Current post-change state:

| Node | Bond mode | Primary | Currently active | Backup | Notes |
| --- | --- | --- | --- | --- | --- |
| `prox2` | `active-backup` | `enp3s0f0` | `eno1` 1G | `enp3s0f1`, `eno1` | Both X540 10G ports are still link-down; primary preference is set for future cabling |
| `prox3` | `active-backup` | `enp1s0` 10G | `enp1s0` 10G | `eno1` 1G | Disconnected `enp3s0f0`/`enp3s0f1` removed from bond |
| `prox4` | `active-backup` | `enp1s0` 10G | `enp1s0` 10G | `eno1` 1G | Recovered after isolating the bad 1G path on Cisco `Gi0/7`; disconnected `enp3s0f0`/`enp3s0f1` removed from bond |

`bridge-fd` was set to `2` on the changed bridge configs because the upgraded
ifupdown2 parser rejected the previous `bridge-fd 0` value during syntax check.
`bridge-stp` remains off.

Post-change validation:

- `prox2`, `prox3`, and `prox4` all reported `0` failed systemd units.
- Cluster quorum remained healthy with all 5 votes present.
- VM resources remained visible after the network reloads.

### 2026-06-24: Runtime Bridge Port Recovery

After reloading the Proxmox network stack, several running VM tap devices were
left detached from `vmbr0` and lost their VLAN 3 membership. The guests were
still running, but their virtual NICs were no longer connected to the bridge.

Recovered the affected running interfaces by reattaching them to `vmbr0` and
restoring VLAN 3 as the PVID/untagged VLAN:

- `prox3`: `tap106i0`, `tap108i0`, `fwpr105p0`
- `prox4`: `tap110i0`, `tap112i0`, `tap113i0`

Final validation from `prox5` passed for the Kubernetes control-plane nodes,
workers, production service VIP, homepage load balancer, and PBS.

Controlled 10G failover testing showed:

- `prox3` is healthy on `enp1s0` 10G.
- `prox4` restored most VLAN 3 connectivity on `enp1s0`, but
  `pbs-primary-01` failed during the test, so `prox4` was reverted and
  persisted to `eno1` 1G until the switch path can be investigated.

### 2026-06-24: `prox4` 10G Recovery

`prox4` became unreachable on VLAN 2 while its 10G EdgeSwitch port remained
physically healthy. From other Proxmox nodes, ARP for `10.0.2.14` stayed in
`INCOMPLETE`/`FAILED` state. Temporarily shutting Cisco `Gi0/7`, the connected
but MAC-silent 1G trunk candidate, immediately restored prox4 through its 10G
path.

Recovered state:

- `prox4` `bond0` primary is now `enp1s0`.
- `bond0` active slave remained `enp1s0` after Cisco `Gi0/7` was re-enabled.
- `enp1s0` is linked at 10 Gbps and `eno1` is linked at 1 Gbps as backup.
- Cluster quorum returned to 5/5 nodes.
- Post-recovery pings passed for `10.0.2.14`, `10.0.3.140`,
  `10.0.3.146`, and `10.0.3.5`.

`prox4` local backup before the change:

```text
/etc/network/interfaces.pre-prox4-10g-primary-20260623-2235
```


### 2026-06-24: Backup Path Validation and `prox5`/`prox6` Cleanup

The prox4 outage was caused by a carrier-up path that was not forwarding
traffic until the Cisco port was bounced. The active-backup bonds were using
`miimon=100` only, with `arp_interval=0`, so Linux trusted physical carrier and
did not validate upstream forwarding. After the Cisco `Gi0/7` bounce, the 1G
path tested healthy when forced active.

Validated failover paths:

| Node | Forced active interface | Switch port | Result |
| --- | --- | --- | --- |
| `prox3` | `eno1` 1G | Cisco `Gi0/9` | Passed VLAN 2 management ping and learned VLAN 2/VLAN 3 MACs |
| `prox4` | `eno1` 1G | Cisco `Gi0/7` | Passed VLAN 2 management ping and learned VLAN 2/VLAN 3 MACs |
| `prox5` | `eno1` 1G | Cisco `Gi0/31` | Passed VLAN 2 management ping |
| `prox5` | `eno2` 1G | Cisco `Gi0/33` | Passed VLAN 2 management ping |
| `prox6` | `eno2` 1G | Cisco `Gi0/39` | Passed VLAN 2 management ping and learned VLAN 3 VM MACs |
| `prox6` | `eno1` 1G | Cisco `Gi0/37` | Passed VLAN 2 management ping and learned VLAN 3 VM MACs |

`prox5` and `prox6` were also corrected from mismatched `802.3ad` LACP to
standalone `active-backup`, because the Cisco ports are configured as ordinary
trunks rather than LACP port-channels. Before the change, both hosts reported
LACP partner MAC `00:00:00:00:00:00`, so aggregation was not actually
negotiated.

Current corrected state:

| Node | Bond mode | Primary | Currently active | Backup |
| --- | --- | --- | --- | --- |
| `prox5` | `active-backup` | `eno1` 1G | `eno1` 1G | `eno2` 1G |
| `prox6` | `active-backup` | `eno2` 1G | `eno2` 1G | `eno1` 1G |

Backups before the `prox5`/`prox6` conversion:

```text
prox5: /etc/network/interfaces.pre-active-backup-20260624-025317
prox6: /etc/network/interfaces.pre-active-backup-20260624-025357
```

Final validation passed:

- `ifquery --check bond0 vmbr0 vmbr0.2` passed on `prox2` through `prox6`.
- Cluster quorum remained healthy at 5/5 nodes.
- Pings passed for all Proxmox management IPs, `10.0.3.140`, `10.0.3.146`,
  `10.0.3.121`, `10.0.3.161`, and service VIP `10.0.3.5`.


### 2026-06-24: Switch Hygiene and Bond Standard

Cisco 3560 host-facing trunk cleanup was applied and saved with `write memory`:

| Cisco port | Description | DTP |
| --- | --- | --- |
| `Gi0/7` | `prox4 eno1 1G backup` | `switchport nonegotiate` |
| `Gi0/9` | `prox3 eno1 1G backup` | `switchport nonegotiate` |
| `Gi0/11` | `prox2 eno1 1G active` | `switchport nonegotiate` |
| `Gi0/31` | `prox5 eno1 1G primary` | `switchport nonegotiate` |
| `Gi0/33` | `prox5 eno2 1G backup` | `switchport nonegotiate` |
| `Gi0/37` | `prox6 eno1 1G backup` | `switchport nonegotiate` |
| `Gi0/39` | `prox6 eno2 1G primary` | `switchport nonegotiate` |
| `Gi0/47` | `EdgeSwitch16XG uplink` | `switchport nonegotiate` |

EdgeSwitch descriptions were already present and verified. The EdgeSwitch CLI
uses zero-based interface numbering, so UI port 4 appears as CLI `0/3`:

| EdgeSwitch CLI port | Description | Notes |
| --- | --- | --- |
| `0/1` | `Trunk - Proxmox Host 2` | 10G future path, currently host link-down |
| `0/2` | `Trunk - Proxmox Host 3` | prox3 10G primary |
| `0/3` | `Trunk - Proxmox Host 4` | prox4 10G primary |
| `0/14` | `Trunk - Cisco Catalyst 3560G PoE Port 47` | Cisco uplink |

Standard Proxmox host network pattern from this point forward:

- Use `active-backup` for mixed-speed or standalone-switch-port redundancy.
- Use 10G as primary where available and validated.
- Use 1G as backup only after forced-active validation on VLAN 2 and any guest
  VLANs hosted on that node.
- Do not use `802.3ad` unless the switch ports are explicitly configured as an
  LACP port-channel and the host reports a non-zero partner MAC.
- Keep `bridge-vlan-aware yes`, `bridge-vids 2-4094`, and `bridge-fd 2` on
  these Proxmox bridges.
- Keep Cisco Proxmox-facing ports as static trunks with `switchport nonegotiate`.

## Implementation Phases

1. Switch documentation
   - Map EdgeSwitch 16 XG ports to host NIC names and MAC addresses.
   - Record port mode, native VLAN, tagged VLANs, LAG membership, MTU, and link
     speed.

2. Physical cabling
   - Connect `prox2` X540 ports to suitable EdgeSwitch 10G ports.
   - Confirm `prox3`/`prox4` SFP+ optics/DACs are on the intended ports.
   - Decide whether any disconnected 1G ports should be used at all.

3. Switch config
   - Create storage and migration VLANs.
   - Configure host-facing ports as tagged trunks for only the VLANs needed.
   - Configure 10G-only LAGs only where both host and switch will participate.
   - Avoid LACP groups with mixed 1G and 10G members.

4. Proxmox host config
   - Replace unhealthy mixed-speed LACP bonds with either:
     - dedicated interfaces per traffic role, or
     - same-speed bonds, or
     - active-backup bonds with explicit primary interfaces.
   - Add storage/migration VLAN interfaces with static IPs.
   - Keep existing management IPs stable during the first change window.

5. Storage endpoint routing
   - Add Synology and PBS addresses on the storage VLAN.
   - Update Proxmox NFS/PBS storage definitions to use storage-network IPs.
   - Verify NFS mounts use the expected client/source address.

6. Proxmox migration network
   - Set the datacenter migration network to the dedicated migration subnet.
   - Test live migration between 10G-capable hosts and confirm traffic counters
     move on the 10G links.

7. Performance validation
   - Baseline before and after with `iperf3`, NFS read/write tests, PBS backup
     throughput, and live migration timings.
   - Watch interface counters on physical NICs during each test.
   - Confirm no packet loss, duplex mismatch, MTU mismatch, or unexpected route
     selection.

## Open Questions

- Which EdgeSwitch ports are each Proxmox NIC connected to?
- Which Synology interfaces are connected to 10G, and what are their VLAN/IP
  capabilities?
- Is PBS expected to stay as a VM on Proxmox, and should it have a second NIC
  on the storage VLAN?
- Should management stay 1G-first for recoverability, or should 10G-capable
  hosts use 10G for the management bridge as well?
- Are jumbo frames desired on storage/migration after cabling and VLANs are
  confirmed?

## Change Safety

- Make one host at a time reachable through iDRAC before touching networking.
- Keep existing `10.0.2.x` management addresses online until the new storage
  and migration paths are verified.
- Do not change corosync networking in the same window as bridge/bond changes.
- Prefer `ifreload -a` with console access available; reboot only after the
  runtime network state matches the intended config.
