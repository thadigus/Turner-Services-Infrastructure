from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
import os
import re
from typing import Any, Dict, Iterable, List, Optional

import pulumi
import yaml


@dataclass(frozen=True)
class StoragePlan:
    lv: str
    expand_by: str


@dataclass(frozen=True)
class DnsRecordConfig:
    name: str
    type: str
    value: Optional[str] = None
    enabled: bool = True
    ttl: Optional[int] = None
    priority: Optional[int] = None
    port: Optional[int] = None
    weight: Optional[int] = None


@dataclass(frozen=True)
class UsbDeviceConfig:
    host: Optional[str] = None
    mapping: Optional[str] = None
    usb3: Optional[bool] = None


@dataclass(frozen=True)
class NetworkDeviceConfig:
    bridge: str = "vmbr0"
    model: str = "virtio"
    vlan: Optional[int] = None
    firewall: bool = False
    enabled: bool = True
    disconnected: bool = False
    mac_address: Optional[str] = None
    mtu: Optional[int] = None
    queues: Optional[int] = None
    trunks: Optional[str] = None


@dataclass(frozen=True)
class HAGroupConfig:
    name: str
    nodes: Dict[str, int]
    restricted: bool = True
    no_failback: bool = True
    comment: Optional[str] = None


@dataclass(frozen=True)
class HAResourceConfig:
    resource_id: str
    group: Optional[str] = None
    state: str = "started"
    resource_type: str = "vm"
    max_restart: Optional[int] = None
    max_relocate: Optional[int] = None
    comment: Optional[str] = None
    vm_name: Optional[str] = None


@dataclass(frozen=True)
class VmConfig:
    name: str
    prox_node: str
    storage_location: Optional[str]
    cpu_count: int
    ram_amount: int
    start_on_boot: bool
    vm_state: str
    mac_address: Optional[str] = None
    dhcp_mac_address: Optional[str] = None
    template_name: Optional[str] = None
    iso_file: Optional[str] = None
    cdrom_interface: str = "ide2"
    boot_orders: List[str] = field(default_factory=list)
    vm_type: Optional[str] = None
    vlan: Optional[int] = None
    network_devices: List[NetworkDeviceConfig] = field(default_factory=list)
    ip_address: Optional[str] = None
    dns_records: List[DnsRecordConfig] = field(default_factory=list)
    unifi_network: Optional[str] = None
    disk_amount: Optional[int] = None
    disk_interface: str = "scsi0"
    storage_plan: List[StoragePlan] = field(default_factory=list)
    usb_devices: List[UsbDeviceConfig] = field(default_factory=list)


@dataclass(frozen=True)
class ServerListConfig:
    template_node: Optional[str]
    virtual_machines: List[VmConfig]
    template_vm_ids: Dict[str, int] = field(default_factory=dict)
    ha_groups: List[HAGroupConfig] = field(default_factory=list)
    ha_resources: List[HAResourceConfig] = field(default_factory=list)
    dns_domain: Optional[str] = None
    unifi_networks: Dict[int, str] = field(default_factory=dict)
    dns_records: List[DnsRecordConfig] = field(default_factory=list)


BASE_DIR = Path(__file__).resolve().parent
MAC_RE = re.compile(r"^[0-9a-f]{2}(:[0-9a-f]{2}){5}$")


def load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise ValueError(f"YAML file not found: {path}")
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping at root of {path}")
    return data


def first_existing(paths: Iterable[Path]) -> Optional[Path]:
    for path in paths:
        if path.exists():
            return path
    return None


def get_config_value(config: pulumi.Config, *keys: str) -> Optional[str]:
    for key in keys:
        value = config.get(key)
        if value is not None:
            return value
    return None


def get_config_secret(config: pulumi.Config, *keys: str) -> Optional[pulumi.Output[str]]:
    for key in keys:
        value = config.get_secret(key)
        if value is not None:
            return value
    return None


def parse_size_gb(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        raw = value.strip().lower()
        if raw.startswith(("+", "=")):
            raw = raw[1:].strip()
        if raw in {"", "none", "null"}:
            return None
        number = ""
        suffix = ""
        for char in raw:
            if char.isdigit() or char == ".":
                number += char
            else:
                suffix += char
        if not number:
            raise ValueError(f"Invalid size value: {value}")
        size = float(number)
        suffix = suffix.strip()
        if suffix in {"g", "gb", ""}:
            return int(size)
        if suffix in {"m", "mb"}:
            return max(1, int(size / 1024))
        if suffix in {"t", "tb"}:
            return int(size * 1024)
    raise ValueError(f"Invalid size value: {value}")


def parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def parse_optional_string(value: Any) -> Optional[str]:
    if value is None:
        return None
    parsed = str(value).strip()
    if not parsed or parsed.lower() in {"none", "null"}:
        return None
    return parsed


def parse_vlan(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in {"", "none", "null"}:
        return None
    vlan = int(value)
    if vlan < 1 or vlan > 4094:
        raise ValueError(f"VLAN ID must be between 1 and 4094: {value}")
    return vlan


def normalize_mac_address(value: Any) -> Optional[str]:
    parsed = parse_optional_string(value)
    if parsed is None:
        return None
    normalized = parsed.replace("-", ":").lower()
    if not MAC_RE.match(normalized):
        raise ValueError(f"Invalid MAC address: {value}")
    return normalized


def generate_mac_address(stack: str, vm_name: str, prefix: str = "02:00:00") -> str:
    normalized_prefix = normalize_mac_address(f"{prefix}:00:00:00")
    if normalized_prefix is None:
        raise ValueError(f"Invalid generated MAC prefix: {prefix}")
    prefix_parts = normalized_prefix.split(":")[:3]
    digest = sha256(f"{stack}:{vm_name}".encode("utf-8")).digest()
    return ":".join(prefix_parts + [f"{part:02x}" for part in digest[:3]])


def parse_dns_record(raw: Any, ip_address: Optional[str]) -> DnsRecordConfig:
    if isinstance(raw, str):
        name = parse_optional_string(raw)
        if name is None:
            raise ValueError("DNS record name cannot be empty")
        return DnsRecordConfig(name=name, type="A", value=ip_address)

    if not isinstance(raw, dict):
        raise ValueError(f"DNS record must be a string or mapping: {raw}")

    name = parse_optional_string(raw.get("name") or raw.get("key"))
    if name is None:
        raise ValueError(f"DNS record missing name: {raw}")
    record_type = str(raw.get("type") or raw.get("record_type") or "A").upper()
    value = parse_optional_string(raw.get("value")) or ip_address
    return DnsRecordConfig(
        name=name,
        type=record_type,
        value=value,
        enabled=parse_bool(raw.get("enabled"), True),
        ttl=int(raw["ttl"]) if raw.get("ttl") is not None else None,
        priority=int(raw["priority"]) if raw.get("priority") is not None else None,
        port=int(raw["port"]) if raw.get("port") is not None else None,
        weight=int(raw["weight"]) if raw.get("weight") is not None else None,
    )


def parse_dns_records(raw: Dict[str, Any], ip_address: Optional[str], dns_domain: Optional[str]) -> List[DnsRecordConfig]:
    records: List[DnsRecordConfig] = []

    dns_name = parse_optional_string(raw.get("dns_name") or raw.get("fqdn"))
    if dns_name:
        records.append(DnsRecordConfig(name=dns_name, type="A", value=ip_address))

    dns_names = raw.get("dns_names") or []
    if isinstance(dns_names, str):
        dns_names = [dns_names]
    for entry in dns_names:
        records.append(parse_dns_record(entry, ip_address))

    dns_records = raw.get("dns_records") or raw.get("dns") or []
    if isinstance(dns_records, (str, dict)):
        dns_records = [dns_records]
    for entry in dns_records:
        records.append(parse_dns_record(entry, ip_address))

    auto_dns = raw.get("auto_dns")
    if auto_dns is None:
        auto_dns = raw.get("manage_dns")
    if parse_bool(auto_dns, False):
        if not dns_domain:
            raise ValueError(f"VM '{raw.get('name')}' enables auto_dns but no dns_domain is configured.")
        records.append(
            DnsRecordConfig(
                name=f"{raw.get('name')}.{dns_domain}".strip("."),
                type="A",
                value=ip_address,
            )
        )

    seen: set[tuple[str, str]] = set()
    unique: List[DnsRecordConfig] = []
    for record in records:
        key = (record.name.lower(), record.type.upper())
        if key in seen:
            raise ValueError(f"Duplicate DNS record for VM '{raw.get('name')}': {record.name} {record.type}")
        seen.add(key)
        unique.append(record)
    return unique


def parse_storage_plan(raw: Dict[str, Any]) -> List[StoragePlan]:
    storage_plan_raw = raw.get("storage_plan")
    storage_plan: List[StoragePlan] = []
    if not storage_plan_raw:
        return storage_plan
    for entry in storage_plan_raw:
        if not isinstance(entry, dict):
            continue
        lv = str(entry.get("lv", "")).strip()
        expand_by = str(entry.get("expand_by", "")).strip()
        if not lv and isinstance(entry.get("lv_targets"), dict):
            lv_targets = dict(entry.get("lv_targets") or {})
            for legacy_lv, legacy_size in lv_targets.items():
                storage_plan.append(
                    StoragePlan(
                        lv=str(legacy_lv).strip(),
                        expand_by=str(legacy_size).strip(),
                    )
                )
            continue
        if lv and expand_by:
            storage_plan.append(StoragePlan(lv=lv, expand_by=expand_by))
    return storage_plan


def parse_disk_amount(raw: Dict[str, Any], storage_plan: List[StoragePlan], vm_name: str) -> Optional[int]:
    disk_amount = parse_size_gb(raw.get("disk_amount"))
    planned_total = None
    if storage_plan:
        total = 0
        for plan in storage_plan:
            parsed = parse_size_gb(plan.expand_by)
            if parsed is None:
                continue
            total += parsed
        planned_total = total if total > 0 else None
    if disk_amount is None and planned_total is not None:
        # Use a migration-safe baseline so removing explicit disk_amount from
        # existing 40G deployments does not cause shrink pressure.
        disk_amount = 40 + planned_total
    if disk_amount is not None and planned_total is not None and planned_total > disk_amount:
        raise ValueError(
            f"Storage plan total ({planned_total}G) exceeds disk_amount ({disk_amount}G) for VM '{vm_name}'."
        )
    return disk_amount


def parse_usb_devices(raw: Dict[str, Any]) -> List[UsbDeviceConfig]:
    usb_raw = raw.get("usb_devices") or raw.get("usb") or raw.get("usbs") or []
    if isinstance(usb_raw, (str, dict)):
        usb_raw = [usb_raw]
    devices: List[UsbDeviceConfig] = []
    for entry in usb_raw:
        if isinstance(entry, str):
            host = parse_optional_string(entry)
            if host is not None:
                devices.append(UsbDeviceConfig(host=host))
            continue
        if not isinstance(entry, dict):
            raise ValueError(f"USB device entries must be strings or mappings: {entry}")
        host = parse_optional_string(entry.get("host") or entry.get("id") or entry.get("vendor_product"))
        mapping = parse_optional_string(entry.get("mapping"))
        usb3 = entry.get("usb3")
        if not host and not mapping:
            raise ValueError(f"USB device entry must include host/id/vendor_product or mapping: {entry}")
        devices.append(
            UsbDeviceConfig(
                host=host,
                mapping=mapping,
                usb3=parse_bool(usb3, False) if usb3 is not None else None,
            )
        )
    return devices


def parse_optional_int(value: Any, field_name: str) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in {"", "none", "null"}:
        return None
    parsed = int(value)
    if parsed < 1:
        raise ValueError(f"{field_name} must be greater than zero: {value}")
    return parsed


def parse_network_device(
    raw: Any,
    default_vlan: Optional[int],
    default_mac_address: Optional[str],
) -> NetworkDeviceConfig:
    if isinstance(raw, str):
        bridge = parse_optional_string(raw)
        if bridge is None:
            raise ValueError("Network bridge cannot be empty")
        return NetworkDeviceConfig(
            bridge=bridge,
            vlan=default_vlan,
            mac_address=default_mac_address,
        )

    if not isinstance(raw, dict):
        raise ValueError(f"Network device entries must be strings or mappings: {raw}")

    bridge = parse_optional_string(raw.get("bridge") or raw.get("vmbr")) or "vmbr0"
    model = parse_optional_string(raw.get("model") or raw.get("type")) or "virtio"
    vlan_value = raw.get("vlan_id") if "vlan_id" in raw else raw.get("vlan", default_vlan)
    mac_value = raw.get("mac_address") if "mac_address" in raw else raw.get("mac", default_mac_address)

    return NetworkDeviceConfig(
        bridge=bridge,
        model=model,
        vlan=parse_vlan(vlan_value),
        firewall=parse_bool(raw.get("firewall"), False),
        enabled=parse_bool(raw.get("enabled"), True),
        disconnected=parse_bool(raw.get("disconnected"), False),
        mac_address=normalize_mac_address(mac_value),
        mtu=parse_optional_int(raw.get("mtu"), "Network MTU"),
        queues=parse_optional_int(raw.get("queues"), "Network queues"),
        trunks=parse_optional_string(raw.get("trunks")),
    )


def parse_network_devices(
    raw: Dict[str, Any],
    default_vlan: Optional[int],
    default_mac_address: Optional[str],
) -> List[NetworkDeviceConfig]:
    if "network_devices" in raw:
        devices_raw = raw.get("network_devices")
    elif "nics" in raw:
        devices_raw = raw.get("nics")
    elif "nic" in raw:
        devices_raw = raw.get("nic")
    else:
        devices_raw = None

    if devices_raw is None:
        return [
            NetworkDeviceConfig(
                vlan=default_vlan,
                mac_address=default_mac_address,
            )
        ]

    if isinstance(devices_raw, (str, dict)):
        devices_raw = [devices_raw]
    if not isinstance(devices_raw, list):
        raise ValueError(f"network_devices must be a list, string, or mapping: {devices_raw}")
    if not devices_raw:
        raise ValueError("network_devices cannot be empty")

    devices: List[NetworkDeviceConfig] = []
    for index, entry in enumerate(devices_raw):
        devices.append(
            parse_network_device(
                entry,
                default_vlan,
                default_mac_address if index == 0 else None,
            )
        )
    return devices


def parse_unifi_networks(raw: Any) -> Dict[int, str]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("'unifi_networks' must be a mapping of VLAN ID to UniFi network name or ID")
    networks: Dict[int, str] = {}
    for vlan, network in raw.items():
        parsed = parse_optional_string(network)
        if parsed is not None:
            networks[int(vlan)] = parsed
    return networks


def parse_template_vm_ids(raw: Any) -> Dict[str, int]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("'template_vm_ids' must be a mapping of template name to VM ID")
    template_ids: Dict[str, int] = {}
    for name, vm_id in raw.items():
        parsed_name = parse_optional_string(name)
        if parsed_name is None:
            raise ValueError("template_vm_ids contains an empty template name")
        parsed_id = int(vm_id)
        if parsed_id < 1:
            raise ValueError(f"template VM ID for {parsed_name!r} must be greater than zero: {vm_id}")
        template_ids[parsed_name] = parsed_id
    return template_ids


def parse_ha_nodes(raw: Any, group_name: str) -> Dict[str, int]:
    if isinstance(raw, dict):
        nodes: Dict[str, int] = {}
        for node, priority in raw.items():
            node_name = parse_optional_string(node)
            if node_name is None:
                raise ValueError(f"HA group {group_name!r} contains an empty node name")
            parsed_priority = int(priority)
            if parsed_priority < 0:
                raise ValueError(f"HA group {group_name!r} priority for {node_name!r} must be non-negative")
            nodes[node_name] = parsed_priority
        if not nodes:
            raise ValueError(f"HA group {group_name!r} must include at least one node")
        return nodes

    if isinstance(raw, list):
        nodes: Dict[str, int] = {}
        for index, entry in enumerate(raw):
            if isinstance(entry, str):
                node_name = parse_optional_string(entry)
                priority = len(raw) - index
            elif isinstance(entry, dict):
                node_name = parse_optional_string(entry.get("name") or entry.get("node"))
                priority = int(entry.get("priority", len(raw) - index))
            else:
                raise ValueError(f"HA group {group_name!r} node entries must be strings or mappings: {entry}")
            if node_name is None:
                raise ValueError(f"HA group {group_name!r} contains an empty node name")
            nodes[node_name] = priority
        if not nodes:
            raise ValueError(f"HA group {group_name!r} must include at least one node")
        return nodes

    raise ValueError(f"HA group {group_name!r} nodes must be a mapping or list")


def parse_ha_groups(raw: Any) -> List[HAGroupConfig]:
    if raw is None:
        return []
    groups_raw = raw
    if isinstance(groups_raw, dict):
        groups_raw = [dict(value, name=key) if isinstance(value, dict) else {"name": key, "nodes": value} for key, value in groups_raw.items()]
    if not isinstance(groups_raw, list):
        raise ValueError("'ha_groups' must be a list or mapping")

    groups: List[HAGroupConfig] = []
    seen: set[str] = set()
    for entry in groups_raw:
        if not isinstance(entry, dict):
            raise ValueError(f"HA group entries must be mappings: {entry}")
        name = parse_optional_string(entry.get("name") or entry.get("group"))
        if name is None:
            raise ValueError(f"HA group missing name: {entry}")
        if name in seen:
            raise ValueError(f"Duplicate HA group name: {name}")
        seen.add(name)
        groups.append(
            HAGroupConfig(
                name=name,
                nodes=parse_ha_nodes(entry.get("nodes"), name),
                restricted=parse_bool(entry.get("restricted"), True),
                no_failback=parse_bool(entry.get("no_failback", entry.get("nofailback")), True),
                comment=parse_optional_string(entry.get("comment")),
            )
        )
    return groups


def normalize_ha_resource_id(value: Any, resource_type: str) -> str:
    parsed = parse_optional_string(value)
    if parsed is None:
        raise ValueError("HA resource missing resource_id/vm_id")
    if ":" in parsed:
        return parsed
    return f"{resource_type}:{parsed}"


def parse_ha_resources(raw: Any) -> List[HAResourceConfig]:
    if raw is None:
        return []
    resources_raw = raw
    if isinstance(resources_raw, dict):
        resources_raw = [dict(value, resource_id=key) if isinstance(value, dict) else {"resource_id": key, "group": value} for key, value in resources_raw.items()]
    if not isinstance(resources_raw, list):
        raise ValueError("'ha_resources' must be a list or mapping")

    resources: List[HAResourceConfig] = []
    seen: set[str] = set()
    for entry in resources_raw:
        if not isinstance(entry, dict):
            raise ValueError(f"HA resource entries must be mappings: {entry}")
        resource_type = parse_optional_string(entry.get("type") or entry.get("resource_type")) or "vm"
        resource_id_value = entry.get("resource_id") or entry.get("sid") or entry.get("vm_id") or entry.get("vmid")
        resource_id = normalize_ha_resource_id(resource_id_value, resource_type)
        if resource_id in seen:
            raise ValueError(f"Duplicate HA resource: {resource_id}")
        seen.add(resource_id)
        resources.append(
            HAResourceConfig(
                resource_id=resource_id,
                group=parse_optional_string(entry.get("group")),
                state=parse_optional_string(entry.get("state")) or "started",
                resource_type=resource_type,
                max_restart=parse_optional_int(entry.get("max_restart"), "HA max_restart"),
                max_relocate=parse_optional_int(entry.get("max_relocate"), "HA max_relocate"),
                comment=parse_optional_string(entry.get("comment")),
                vm_name=parse_optional_string(entry.get("vm_name") or entry.get("name")),
            )
        )
    return resources


def parse_vm(raw: Dict[str, Any], stack: str, dns_domain: Optional[str], unifi_networks: Dict[int, str]) -> VmConfig:
    name = str(raw.get("name", "")).strip()
    prox_node = str(raw.get("prox_node", "")).strip()
    if not name or not prox_node:
        raise ValueError("Each VM must include non-empty 'name' and 'prox_node'")

    storage_plan = parse_storage_plan(raw)
    disk_amount = parse_disk_amount(raw, storage_plan, name)
    vlan = parse_vlan(raw.get("vlan"))
    ip_address = parse_optional_string(raw.get("ip_address") or raw.get("fixed_ip"))
    explicit_mac_address = normalize_mac_address(raw.get("mac_address"))
    dhcp_mac_address = normalize_mac_address(raw.get("dhcp_mac_address") or raw.get("reservation_mac_address"))
    mac_address = explicit_mac_address or (generate_mac_address(stack, name) if ip_address and dhcp_mac_address is None else None)
    dns_records = parse_dns_records(raw, ip_address, dns_domain)
    unifi_network = parse_optional_string(
        raw.get("unifi_network_id") or raw.get("unifi_network") or raw.get("network_id")
    )
    if unifi_network is None and vlan is not None:
        unifi_network = unifi_networks.get(vlan)

    network_devices = parse_network_devices(raw, vlan, mac_address)

    return VmConfig(
        name=name,
        prox_node=prox_node,
        storage_location=parse_optional_string(raw.get("storage_location")),
        cpu_count=int(raw.get("cpu_count", 1)),
        ram_amount=int(raw.get("ram_amount", 512)),
        start_on_boot=parse_bool(raw.get("start_on_boot"), True),
        vm_state=str(raw.get("vm_state", "present")).lower(),
        template_name=parse_optional_string(raw.get("template_name")),
        iso_file=parse_optional_string(raw.get("iso_file") or raw.get("boot_iso") or raw.get("iso_path")),
        cdrom_interface=str(raw.get("cdrom_interface", "ide2")).strip() or "ide2",
        boot_orders=[str(item).strip() for item in (raw.get("boot_orders") or raw.get("boot_order") or [])] if isinstance((raw.get("boot_orders") or raw.get("boot_order") or []), list) else [str(raw.get("boot_orders") or raw.get("boot_order")).strip()],
        vm_type=parse_optional_string(raw.get("vm_type") or raw.get("os_type")),
        vlan=vlan,
        network_devices=network_devices,
        mac_address=mac_address,
        dhcp_mac_address=dhcp_mac_address,
        ip_address=ip_address,
        dns_records=dns_records,
        unifi_network=unifi_network,
        disk_amount=disk_amount,
        disk_interface=str(raw.get("disk_interface", "scsi0")).strip() or "scsi0",
        storage_plan=storage_plan,
        usb_devices=parse_usb_devices(raw),
    )


def validate_server_list(config: ServerListConfig) -> None:
    macs: Dict[str, str] = {}
    ips: Dict[str, str] = {}
    for vm in config.virtual_machines:
        for mac_address in {vm.mac_address, vm.dhcp_mac_address}:
            if mac_address is None:
                continue
            if mac_address in macs:
                raise ValueError(f"Duplicate MAC address {mac_address} on {vm.name} and {macs[mac_address]}")
            macs[mac_address] = vm.name
        if vm.ip_address:
            if vm.ip_address in ips:
                raise ValueError(f"Duplicate IP address {vm.ip_address} on {vm.name} and {ips[vm.ip_address]}")
            ips[vm.ip_address] = vm.name
        if vm.template_name and vm.iso_file:
            raise ValueError(f"VM '{vm.name}' cannot set both template_name and iso_file.")
        if vm.iso_file and vm.disk_amount is None:
            raise ValueError(f"VM '{vm.name}' sets iso_file but has no disk_amount for the installer target disk.")
        if not vm.network_devices:
            raise ValueError(f"VM '{vm.name}' must have at least one network device.")
        for device in vm.network_devices:
            if not device.bridge:
                raise ValueError(f"VM '{vm.name}' has a network device with no bridge.")
            if not device.model:
                raise ValueError(f"VM '{vm.name}' has a network device with no model.")
        for record in vm.dns_records:
            if record.type in {"A", "AAAA"} and not record.value:
                raise ValueError(f"DNS record {record.name} for VM '{vm.name}' needs an IP/value.")
    for record in config.dns_records:
        if record.type in {"A", "AAAA"} and not record.value:
            raise ValueError(f"Top-level DNS record {record.name} needs a value.")

    group_names = {group.name for group in config.ha_groups}
    for resource in config.ha_resources:
        if resource.group and resource.group not in group_names:
            raise ValueError(f"HA resource {resource.resource_id!r} references unknown group {resource.group!r}")
        if resource.resource_type != "vm":
            raise ValueError(f"Unsupported HA resource type for {resource.resource_id!r}: {resource.resource_type}")


def load_server_list(path: Path, stack: Optional[str] = None) -> ServerListConfig:
    data = load_yaml(path)
    vms_raw = data.get("virtual_machines") or []
    if not isinstance(vms_raw, list):
        raise ValueError("'virtual_machines' must be a list")

    stack_name = stack or pulumi.get_stack()
    dns_domain = parse_optional_string(data.get("dns_domain") or data.get("domain"))
    unifi_networks = parse_unifi_networks(data.get("unifi_networks"))
    template_vm_ids = parse_template_vm_ids(data.get("template_vm_ids") or data.get("template_ids"))
    ha_raw = data.get("ha") if isinstance(data.get("ha"), dict) else {}
    ha_groups = parse_ha_groups(data.get("ha_groups") or ha_raw.get("groups"))
    ha_resources = parse_ha_resources(data.get("ha_resources") or ha_raw.get("resources"))
    dns_records = parse_dns_records(data, None, dns_domain)
    vms = [parse_vm(vm, stack_name, dns_domain, unifi_networks) for vm in vms_raw]
    parsed = ServerListConfig(
        template_node=parse_optional_string(data.get("template_node")),
        virtual_machines=vms,
        template_vm_ids=template_vm_ids,
        ha_groups=ha_groups,
        ha_resources=ha_resources,
        dns_domain=dns_domain,
        unifi_networks=unifi_networks,
        dns_records=dns_records,
    )
    validate_server_list(parsed)
    return parsed


def resolve_paths(config: pulumi.Config) -> tuple[Path, Optional[Path]]:
    server_list_path = config.get("serverListPath") or os.getenv("TS_SERVER_LIST_PATH")
    inventory_path = config.get("inventoryPath")

    if server_list_path:
        resolved_server_list = (BASE_DIR / server_list_path).resolve()
    else:
        resolved_server_list = first_existing(
            [
                BASE_DIR / "../../turner-services-sensitive-repo/server-list-prod.yml",
                BASE_DIR / "../server-list.example.yml",
            ]
        )

    if resolved_server_list is None:
        raise ValueError("No server list file found. Set serverListPath in Pulumi config.")

    resolved_inventory = None
    if inventory_path:
        resolved_inventory = (BASE_DIR / inventory_path).resolve()
    else:
        resolved_inventory = first_existing(
            [
                BASE_DIR / "../../turner-services-sensitive-repo/inventories/ansible-inv-rack.proxmox.yml",
                BASE_DIR / "../../inventories/ansible-inv-example.proxmox.yml",
            ]
        )

    if resolved_inventory is None:
        pulumi.log.warn("No inventory file found; Proxmox credentials must be set via Pulumi config.")

    return resolved_server_list, resolved_inventory


def resolve_stack_environment(config: pulumi.Config, server_list_file: Path) -> str:
    env_hint = get_config_value(config, "environment", "stackEnvironment")
    candidates = [
        (env_hint or "").strip().lower(),
        pulumi.get_stack().strip().lower(),
        server_list_file.stem.strip().lower(),
    ]

    for value in candidates:
        if any(token in value for token in ("prod", "production")):
            return "production"
        if any(token in value for token in ("test", "testing")):
            return "test"

    raise ValueError(
        "Unable to determine stack environment for VM tags. "
        "Use a stack/server list name containing 'prod' or 'test', "
        "or set Pulumi config key 'environment' to 'production' or 'test'."
    )
