from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import pulumi
import pulumi_proxmoxve as proxmox
from pulumi_proxmoxve.hardware import mapping as hardware_mapping

from .ha_policy import ProxmoxHANodeAffinityPolicy

import os

from server_config import (
    HAGroupConfig,
    HAResourceConfig,
    ServerListConfig,
    VmConfig,
    get_config_secret,
    get_config_value,
    load_yaml,
)


_template_cache: Dict[tuple[str, Optional[str]], int] = {}


def clean_resource_name(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "-" for char in value).strip("-")


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


def resolve_proxmox_api_connection(inventory_path: Optional[Path]) -> tuple[str, bool]:
    config = pulumi.Config("proxmox")
    endpoint = get_config_value(config, "endpoint", "url")
    insecure = config.get_bool("insecure")

    if inventory_path and inventory_path.exists():
        inventory = load_yaml(inventory_path)
        endpoint = endpoint or inventory.get("url")
        if insecure is None and "validate_certs" in inventory:
            insecure = not bool(inventory.get("validate_certs"))

    if not endpoint:
        source = f"inventory file {inventory_path}" if inventory_path else "Pulumi config"
        raise ValueError(f"Missing Proxmox endpoint. Set proxmox:endpoint or ensure {source} has url.")

    return str(endpoint), bool(insecure) if insecure is not None else True


def resolve_template_vm_id(
    template_name: str,
    template_node: Optional[str],
    provider: proxmox.Provider,
    template_vm_ids: Optional[Dict[str, int]] = None,
) -> int:
    if template_vm_ids and template_name in template_vm_ids:
        return template_vm_ids[template_name]

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


def build_usb_mappings(
    server_list: ServerListConfig,
    provider: proxmox.Provider,
) -> Dict[str, pulumi.Resource]:
    mappings: Dict[str, pulumi.Resource] = {}
    for vm in server_list.virtual_machines:
        for device in vm.usb_devices:
            if not device.mapping or not device.host or device.mapping in mappings:
                continue
            mappings[device.mapping] = hardware_mapping.Usb(
                clean_resource_name(f"usb-{device.mapping}"),
                name=device.mapping,
                comment=f"{vm.name} USB passthrough",
                maps=[
                    hardware_mapping.UsbMapArgs(
                        id=device.host,
                        node=vm.prox_node,
                    )
                ],
                opts=pulumi.ResourceOptions(provider=provider),
            )
    return mappings


def build_usbs(vm: VmConfig) -> Optional[List[proxmox.vm.VirtualMachineUsbArgs]]:
    if not vm.usb_devices:
        return None
    usbs: List[proxmox.vm.VirtualMachineUsbArgs] = []
    for device in vm.usb_devices:
        usbs.append(
            proxmox.vm.VirtualMachineUsbArgs(
                host=None if device.mapping else device.host,
                mapping=device.mapping,
                usb3=device.usb3,
            )
        )
    return usbs


def build_network_devices(vm: VmConfig) -> List[proxmox.vm.VirtualMachineNetworkDeviceArgs]:
    devices: List[proxmox.vm.VirtualMachineNetworkDeviceArgs] = []
    for device in vm.network_devices:
        devices.append(
            proxmox.vm.VirtualMachineNetworkDeviceArgs(
                bridge=device.bridge,
                model=device.model,
                vlan_id=device.vlan,
                firewall=device.firewall,
                enabled=device.enabled,
                disconnected=device.disconnected,
                mac_address=device.mac_address,
                mtu=device.mtu,
                queues=device.queues,
                trunks=device.trunks,
            )
        )
    return devices


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
    template_vm_ids: Optional[Dict[str, int]] = None,
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
        "network_devices": build_network_devices(vm),
    }
    if vm.iso_file:
        vm_args["cdrom"] = {
            "interface": vm.cdrom_interface,
            "file_id": vm.iso_file,
        }
        vm_args["boot_orders"] = vm.boot_orders or [vm.disk_interface, vm.cdrom_interface]
    else:
        vm_args["cdrom"] = {"interface": "ide3", "file_id": "none"}

    usbs = build_usbs(vm)
    if usbs:
        vm_args["usbs"] = usbs

    if vm.template_name:
        if vm.storage_location and not vm.storage_plan and vm.disk_amount is None:
            raise ValueError(
                f"VM '{vm.name}' clones to a different datastore but has no disk_amount. "
                "The provider defaults to 8G during clone moves, which fails if the template is larger. "
                "Set disk_amount to the template size (or larger), or omit storage_location to keep the "
                "template datastore."
            )
        clone_args: Dict[str, Any] = {
            "vm_id": resolve_template_vm_id(vm.template_name, template_node, provider, template_vm_ids),
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
        ignore_changes=[
            "disks[0].speed",
            "ipv4Addresses",
            "ipv6Addresses",
            "networkInterfaceNames",
            "started",
        ],
        depends_on=depends_on,
    )
    return proxmox.vm.VirtualMachine(vm.name, opts=opts, **vm_args)



def build_ha_groups(ha_groups: List[HAGroupConfig]) -> Dict[str, HAGroupConfig]:
    return {group.name: group for group in ha_groups}


def build_ha_resources(
    ha_resources: List[HAResourceConfig],
    ha_groups: Dict[str, HAGroupConfig],
    vm_resources: Dict[str, proxmox.vm.VirtualMachine],
    endpoint: str,
    insecure: bool,
) -> None:
    for resource in ha_resources:
        if not resource.group or resource.group not in ha_groups:
            raise ValueError(f"HA resource {resource.resource_id!r} must reference a node-affinity group")

        group = ha_groups[resource.group]
        dependencies: List[pulumi.Resource] = []
        if resource.vm_name and resource.vm_name in vm_resources:
            dependencies.append(vm_resources[resource.vm_name])

        ProxmoxHANodeAffinityPolicy(
            clean_resource_name(f"ha-policy-{resource.resource_id}"),
            endpoint=endpoint,
            insecure=insecure,
            resource_id=resource.resource_id,
            resource_type=resource.resource_type,
            state=resource.state,
            max_restart=resource.max_restart,
            max_relocate=resource.max_relocate,
            comment=resource.comment,
            rule_name=group.name,
            nodes=group.nodes,
            strict=group.restricted,
            failback=not group.no_failback,
            opts=pulumi.ResourceOptions(depends_on=dependencies or None),
        )

def build_virtual_machines(
    server_list: ServerListConfig,
    inventory_file: Optional[Path],
    stack_environment: str,
    unifi_dependencies: Dict[str, List[pulumi.Resource]],
) -> None:
    provider = build_provider(inventory_file)
    usb_mappings = build_usb_mappings(server_list, provider)
    vm_resources: Dict[str, proxmox.vm.VirtualMachine] = {}
    for vm in server_list.virtual_machines:
        vm_tags = build_vm_tags(stack_environment, vm)
        dependencies = list(unifi_dependencies.get(vm.name) or [])
        dependencies.extend(
            usb_mappings[device.mapping]
            for device in vm.usb_devices
            if device.mapping in usb_mappings
        )
        vm_resource = build_vm_resource(
            vm,
            server_list.template_node,
            provider,
            vm_tags,
            template_vm_ids=server_list.template_vm_ids,
            depends_on=dependencies or None,
        )
        if vm_resource is not None:
            vm_resources[vm.name] = vm_resource

    endpoint, insecure = resolve_proxmox_api_connection(inventory_file)
    ha_groups = build_ha_groups(server_list.ha_groups)
    build_ha_resources(server_list.ha_resources, ha_groups, vm_resources, endpoint, insecure)
