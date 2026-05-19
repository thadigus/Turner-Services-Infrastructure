from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import pulumi
import pulumi_proxmoxve as proxmox

import os

from server_config import (
    ServerListConfig,
    VmConfig,
    get_config_secret,
    get_config_value,
    load_yaml,
)


_template_cache: Dict[tuple[str, Optional[str]], int] = {}


def build_provider(inventory_path: Optional[Path]) -> proxmox.Provider:
    config = pulumi.Config("proxmox")

    endpoint = get_config_value(config, "endpoint", "url")
    username = os.environ.get("PROXMOX_VE_USERNAME")
    password = os.environ.get("PROXMOX_VE_API_TOKEN")
    api_token = str(username) + "=" + str(password) if username and password else None
    insecure = config.get_bool("insecure")

    if inventory_path and inventory_path.exists():
        pulumi.log.info(f"Using inventory file: {inventory_path}")
        inventory = load_yaml(inventory_path)
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
        insecure=insecure,
    )


def resolve_template_vm_id(
    template_name: str,
    template_node: Optional[str],
    provider: proxmox.Provider,
) -> int:
    cache_key = (template_name, template_node)
    if cache_key in _template_cache:
        return _template_cache[cache_key]

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
    _template_cache[cache_key] = vm_id
    return vm_id


def build_disks(vm: VmConfig) -> Optional[List[proxmox.vm.VirtualMachineDiskArgs]]:
    if vm.disk_amount is None:
        return None
    disk = proxmox.vm.VirtualMachineDiskArgs(
        interface=vm.disk_interface,
        size=vm.disk_amount,
        datastore_id=vm.storage_location,
    )
    return [disk]


def infer_vm_platform_tag(vm: VmConfig) -> str:
    selector = " ".join(
        [
            str(vm.vm_type or ""),
            str(vm.template_name or ""),
            vm.name,
        ]
    ).lower()
    if "windows" in selector or "win" in selector:
        return "windows"
    return "linux"


def build_vm_tags(stack_environment: str, vm: VmConfig) -> List[str]:
    return sorted(["pulumi", stack_environment.lower(), infer_vm_platform_tag(vm)])


def build_vm_resource(
    vm: VmConfig,
    template_node: Optional[str],
    provider: proxmox.Provider,
    vm_tags: List[str],
    depends_on: Optional[List[pulumi.Resource]] = None,
) -> Optional[proxmox.vm.VirtualMachine]:
    if vm.vm_state != "present":
        return None

    vm_args: Dict[str, Any] = {
        "name": vm.name,
        "node_name": vm.prox_node,
        "cpu": {"cores": vm.cpu_count, "type": "x86-64-v3"},
        "memory": {"dedicated": vm.ram_amount},
        "agent": {
            "enabled": True,
            "trim": True,
            "type": "virtio",
            "timeout": "30s",
        },
        "on_boot": vm.start_on_boot,
        "started": True,
        "tags": vm_tags,
        "network_devices": [
            {
                "bridge": "vmbr0",
                **({"vlan_id": vm.vlan} if vm.vlan is not None else {}),
                **({"mac_address": vm.mac_address} if vm.mac_address else {}),
            }
        ],
    }
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
            "vm_id": resolve_template_vm_id(vm.template_name, template_node, provider),
        }
        if template_node:
            clone_args["node_name"] = template_node
        if vm.storage_location:
            clone_args["datastore_id"] = vm.storage_location
        vm_args["clone"] = clone_args

        if vm.disk_amount is not None:
            resized_disks = build_disks(vm)
            if resized_disks:
                vm_args["disks"] = resized_disks
    else:
        disks = build_disks(vm)
        if disks:
            vm_args["disks"] = disks

    opts = pulumi.ResourceOptions(
        provider=provider,
        ignore_changes=["disks[0].speed"],
        depends_on=depends_on,
    )
    return proxmox.vm.VirtualMachine(vm.name, opts=opts, **vm_args)


def build_virtual_machines(
    server_list: ServerListConfig,
    inventory_file: Optional[Path],
    stack_environment: str,
    unifi_dependencies: Dict[str, List[pulumi.Resource]],
) -> None:
    provider = build_provider(inventory_file)
    for vm in server_list.virtual_machines:
        vm_tags = build_vm_tags(stack_environment, vm)
        build_vm_resource(
            vm,
            server_list.template_node,
            provider,
            vm_tags,
            depends_on=unifi_dependencies.get(vm.name),
        )
