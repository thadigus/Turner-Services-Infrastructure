from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os
from typing import Any, Dict, Iterable, List, Optional

import pulumi
import pulumi_proxmoxve as proxmox
import yaml


@dataclass(frozen=True)
class StoragePlan:
    device: str
    vg: str
    lv_targets: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class VmConfig:
    name: str
    prox_node: str
    storage_location: Optional[str]
    cpu_count: int
    ram_amount: int
    start_on_boot: bool
    vm_state: str
    template_name: Optional[str] = None
    vlan: Optional[int] = None
    disk_amount: Optional[int] = None
    disk_interface: str = "scsi0"
    storage_plan: List[StoragePlan] = field(default_factory=list)


@dataclass(frozen=True)
class ServerListConfig:
    template_node: Optional[str]
    virtual_machines: List[VmConfig]


BASE_DIR = Path(__file__).resolve().parent


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise ValueError(f"YAML file not found: {path}")
    with path.open("r", encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected mapping at root of {path}")
    return data


def _parse_size_gb(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        raw = value.strip().lower()
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


def _parse_vm(raw: Dict[str, Any]) -> VmConfig:
    name = str(raw.get("name", "")).strip()
    prox_node = str(raw.get("prox_node", "")).strip()
    if not name or not prox_node:
        raise ValueError("Each VM must include non-empty 'name' and 'prox_node'")

    storage_plan_raw = raw.get("storage_plan")
    storage_plan: List[StoragePlan] = []
    if storage_plan_raw:
        for entry in storage_plan_raw:
            if not isinstance(entry, dict):
                continue
            storage_plan.append(
                StoragePlan(
                    device=str(entry.get("device", "")),
                    vg=str(entry.get("vg", "")),
                    lv_targets=dict(entry.get("lv_targets") or {}),
                )
            )

    disk_amount = _parse_size_gb(raw.get("disk_amount"))
    planned_total = None
    if storage_plan:
        total = 0
        for plan in storage_plan:
            for size in plan.lv_targets.values():
                parsed = _parse_size_gb(size)
                if parsed is None:
                    continue
                total += parsed
        planned_total = total if total > 0 else None
    if disk_amount is None and planned_total is not None:
        disk_amount = planned_total
    if disk_amount is not None and planned_total is not None and planned_total > disk_amount:
        raise ValueError(
            f"Storage plan total ({planned_total}G) exceeds disk_amount ({disk_amount}G) for VM '{name}'."
        )

    start_on_boot = raw.get("start_on_boot")
    if start_on_boot is None:
        start_on_boot_value = True
    elif isinstance(start_on_boot, bool):
        start_on_boot_value = start_on_boot
    elif isinstance(start_on_boot, str):
        start_on_boot_value = start_on_boot.strip().lower() in {"1", "true", "yes", "y"}
    else:
        start_on_boot_value = bool(start_on_boot)

    vlan_raw = raw.get("vlan")
    if vlan_raw is None or (isinstance(vlan_raw, str) and vlan_raw.strip().lower() in {"", "none", "null"}):
        vlan_value = None
    else:
        vlan_value = int(vlan_raw)

    return VmConfig(
        name=name,
        prox_node=prox_node,
        storage_location=raw.get("storage_location"),
        cpu_count=int(raw.get("cpu_count", 1)),
        ram_amount=int(raw.get("ram_amount", 512)),
        start_on_boot=start_on_boot_value,
        vm_state=str(raw.get("vm_state", "present")).lower(),
        template_name=raw.get("template_name"),
        vlan=vlan_value,
        disk_amount=disk_amount,
        disk_interface=str(raw.get("disk_interface", "scsi0")).strip() or "scsi0",
        storage_plan=storage_plan,
    )


def load_server_list(path: Path) -> ServerListConfig:
    data = _load_yaml(path)
    vms_raw = data.get("virtual_machines") or []
    if not isinstance(vms_raw, list):
        raise ValueError("'virtual_machines' must be a list")

    vms = [_parse_vm(vm) for vm in vms_raw]
    return ServerListConfig(
        template_node=data.get("template_node"),
        virtual_machines=vms,
    )


def _first_existing(paths: Iterable[Path]) -> Optional[Path]:
    for path in paths:
        if path.exists():
            return path
    return None


def _get_config_value(config: pulumi.Config, *keys: str) -> Optional[str]:
    for key in keys:
        value = config.get(key)
        if value is not None:
            return value
    return None


def _get_config_secret(config: pulumi.Config, *keys: str) -> Optional[pulumi.Output[str]]:
    for key in keys:
        value = config.get_secret(key)
        if value is not None:
            return value
    return None


def _build_provider(inventory_path: Optional[Path]) -> proxmox.Provider:
    config = pulumi.Config("proxmox")

    endpoint = _get_config_value(config, "endpoint", "url")
    username = _get_config_value(config, "username", "user")
    password = _get_config_secret(config, "password")
    api_token = _get_config_secret(config, "apiToken", "api_token")
    insecure = config.get_bool("insecure")

    if inventory_path and inventory_path.exists():
        pulumi.log.info(f"Using inventory file: {inventory_path}")
        inventory = _load_yaml(inventory_path)
        endpoint = endpoint or inventory.get("url")
        username = username or inventory.get("user")
        if insecure is None and "validate_certs" in inventory:
            insecure = not bool(inventory.get("validate_certs"))

        if api_token is None and inventory.get("token_id") and inventory.get("token_secret"):
            token_id = str(inventory.get("token_id"))
            token_secret = str(inventory.get("token_secret"))
            token_user = username or str(inventory.get("user", ""))
            api_token = pulumi.Output.secret(f"{token_user}!{token_id}={token_secret}")

    if not endpoint:
        source = f"inventory file {inventory_path}" if inventory_path else "Pulumi config"
        raise ValueError(f"Missing Proxmox endpoint. Set proxmox:endpoint or ensure {source} has url.")

    if api_token is None and password is None:
        source = f"inventory file {inventory_path}" if inventory_path else "Pulumi config"
        raise ValueError(
            "Missing Proxmox credentials. Set proxmox:apiToken or proxmox:password, "
            f"or ensure {source} has token_id/token_secret."
        )

    return proxmox.Provider(
        "proxmox-provider",
        endpoint=endpoint,
        username=username,
        password=password,
        api_token=api_token,
        insecure=insecure if insecure is not None else False,
    )


_template_cache: Dict[str, int] = {}


def _resolve_template_vm_id(
    template_name: str,
    template_node: Optional[str],
    provider: proxmox.Provider,
) -> int:
    if template_name in _template_cache:
        return _template_cache[template_name]

    filters = [
        proxmox.vm.GetVirtualMachinesFilterArgs(name="name", values=[template_name]),
        proxmox.vm.GetVirtualMachinesFilterArgs(name="template", values=["true"]),
    ]
    if template_node:
        filters.append(
            proxmox.vm.GetVirtualMachinesFilterArgs(
                name="node_name",
                values=[template_node],
            )
        )

    result = proxmox.vm.get_virtual_machines(
        filters=filters,
        opts=pulumi.InvokeOptions(provider=provider),
    )
    if not result.vms:
        raise ValueError(f"No template VM found for '{template_name}'.")

    vm_id = result.vms[0].vm_id
    _template_cache[template_name] = vm_id
    return vm_id


def _build_disks(vm: VmConfig) -> Optional[List[proxmox.vm.VirtualMachineDiskArgs]]:
    if vm.disk_amount is None:
        return None
    disk = proxmox.vm.VirtualMachineDiskArgs(
        interface=vm.disk_interface,
        size=vm.disk_amount,
        datastore_id=vm.storage_location,
    )
    return [disk]


def _build_vm_resource(
    vm: VmConfig,
    template_node: Optional[str],
    provider: proxmox.Provider,
) -> Optional[proxmox.vm.VirtualMachine]:
    if vm.vm_state != "present":
        return None

    vm_args: Dict[str, Any] = {
        "name": vm.name,
        "node_name": vm.prox_node,
        "cpu": {"cores": vm.cpu_count},
        "memory": {"dedicated": vm.ram_amount},
        "on_boot": vm.start_on_boot,
        "started": True,
        "network_devices": [
            {
                "bridge": "vmbr0",
                **({"vlan_id": vm.vlan} if vm.vlan is not None else {}),
            }
        ],
    }
    # Explicitly disable the default CD-ROM device that Proxmox may add.
    vm_args["cdrom"] = {"interface": "ide3", "file_id": "none"}

    if vm.template_name:
        if vm.storage_location and not vm.storage_plan and vm.disk_amount is None:
            raise ValueError(
                f"VM '{vm.name}' clones to a different datastore but has no disk_amount. "
                "The provider defaults to 8G during clone moves, which fails if the template is larger. "
                "Set disk_amount to the template size (or larger), or omit storage_location to keep the "
                "template datastore."
            )
        clone_args: Dict[str, Any] = {
            "vm_id": _resolve_template_vm_id(vm.template_name, template_node, provider),
        }
        if template_node:
            clone_args["node_name"] = template_node
        if vm.storage_location:
            clone_args["datastore_id"] = vm.storage_location
        vm_args["clone"] = clone_args

        if vm.disk_amount is not None:
            resized_disks = _build_disks(vm)
            if resized_disks:
                vm_args["disks"] = resized_disks
    else:
        disks = _build_disks(vm)
        if disks:
            vm_args["disks"] = disks

    opts = pulumi.ResourceOptions(
        provider=provider,
        ignore_changes=["disks[0].speed"],
    )
    return proxmox.vm.VirtualMachine(vm.name, opts=opts, **vm_args)


def _resolve_paths(config: pulumi.Config) -> tuple[Path, Optional[Path]]:
    server_list_path = os.getenv("TS_SERVER_LIST_PATH") or config.get("serverListPath")
    inventory_path = config.get("inventoryPath")

    if server_list_path:
        resolved_server_list = (BASE_DIR / server_list_path).resolve()
    else:
        resolved_server_list = _first_existing(
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
        resolved_inventory = _first_existing(
            [
                BASE_DIR
                / "../../turner-services-sensitive-repo/inventories/ansible-inv-rack.proxmox.yml",
                BASE_DIR / "../../inventories/ansible-inv-example.proxmox.yml",
            ]
        )

    if resolved_inventory is None:
        pulumi.log.warn("No inventory file found; Proxmox credentials must be set via Pulumi config.")

    return resolved_server_list, resolved_inventory


config = pulumi.Config()
server_list_file, inventory_file = _resolve_paths(config)
server_list = load_server_list(server_list_file)

proxmox_provider = _build_provider(inventory_file)

for vm in server_list.virtual_machines:
    _build_vm_resource(vm, server_list.template_node, proxmox_provider)
