from __future__ import annotations

from pathlib import Path
import os
import re
from typing import Dict, List, Optional

import pulumi
import pulumiverse_unifi as unifi

from server_config import (
    BASE_DIR,
    DnsRecordConfig,
    ServerListConfig,
    VmConfig,
    first_existing,
    get_config_secret,
    get_config_value,
    load_yaml,
)


RESOURCE_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def clean_resource_name(value: str) -> str:
    return RESOURCE_NAME_RE.sub("-", value).strip("-").lower()


def needs_unifi(vm: VmConfig) -> bool:
    return vm.vm_state == "present" and (bool(vm.ip_address) or bool(vm.dns_records))


def resolve_unifi_console_path(config: pulumi.Config) -> Optional[Path]:
    configured = config.get("consolesPath")
    if configured:
        return (BASE_DIR / configured).resolve()
    return first_existing(
        [
            BASE_DIR / "../../turner-services-sensitive-repo/unifi-consoles.yml",
        ]
    )


def load_console_config(path: Optional[Path], console_name: str) -> dict:
    if not path or not path.exists():
        return {}
    doc = load_yaml(path)
    consoles = doc.get("consoles") or {}
    console = consoles.get(console_name)
    if console is None:
        configured = ", ".join(sorted(consoles))
        raise ValueError(f"Unknown UniFi console {console_name!r}; configured: {configured}")
    return dict(console)


def build_provider(required: bool) -> Optional[unifi.Provider]:
    root_config = pulumi.Config()
    if root_config.get_bool("unifiEnabled") is False:
        if required:
            raise ValueError("UniFi resources are required by the server list, but unifiEnabled is false.")
        return None

    config = pulumi.Config("unifi")
    console_name = config.get("console") or root_config.get("unifiConsole") or "main"
    console = load_console_config(resolve_unifi_console_path(config), console_name)

    api_url = get_config_value(config, "apiUrl", "api_url", "url") or console.get("url")
    site = get_config_value(config, "site") or console.get("site") or "default"
    allow_insecure = config.get_bool("allowInsecure")
    if allow_insecure is None:
        allow_insecure = True

    api_key = get_config_secret(config, "apiKey", "api_key")
    if api_key is None:
        api_key_env = console.get("api_key_env")
        if api_key_env:
            env_api_key = os.getenv(str(api_key_env))
            if env_api_key:
                api_key = pulumi.Output.secret(env_api_key)

    username = get_config_value(config, "username", "user")
    password = get_config_secret(config, "password")

    if not api_url or (api_key is None and not (username and password is not None)):
        if required:
            raise ValueError(
                "Missing UniFi credentials. Set unifi:apiUrl plus unifi:apiKey, "
                "or provide a consoles.yml entry with url/api_key_env and export that env var."
            )
        return None

    return unifi.Provider(
        "unifi-provider",
        api_url=api_url,
        api_key=api_key,
        username=username,
        password=password,
        site=site,
        allow_insecure=allow_insecure,
    )


def resolve_network_id(
    provider: unifi.Provider,
    site: Optional[str],
    network_name_or_id: Optional[str],
) -> Optional[str]:
    if not network_name_or_id:
        return None
    if len(network_name_or_id) == 24 and all(c in "0123456789abcdefABCDEF" for c in network_name_or_id):
        return network_name_or_id
    result = unifi.get_network(
        name=network_name_or_id,
        site=site,
        opts=pulumi.InvokeOptions(provider=provider),
    )
    return result.id


def build_dns_record(
    owner_name: str,
    record: DnsRecordConfig,
    provider: unifi.Provider,
    default_value: Optional[str] = None,
) -> unifi.dns.Record:
    args = {
        "name": record.name,
        "type": record.type,
        "value": record.value or default_value,
        "enabled": record.enabled,
    }
    for key in ("ttl", "priority", "port", "weight"):
        value = getattr(record, key)
        if value is not None:
            args[key] = value
    resource_name = clean_resource_name(f"{owner_name}-{record.name}-{record.type}")
    return unifi.dns.Record(
        resource_name,
        opts=pulumi.ResourceOptions(provider=provider),
        **args,
    )


def build_dhcp_reservation(
    vm: VmConfig,
    provider: unifi.Provider,
) -> Optional[unifi.iam.User]:
    if not vm.ip_address:
        return None

    site = pulumi.Config("unifi").get("site")
    network_id = resolve_network_id(provider, site, vm.unifi_network)
    reservation_mac = vm.dhcp_mac_address or vm.mac_address
    if not reservation_mac:
        raise ValueError(f"VM {vm.name!r} needs a MAC address for its UniFi DHCP reservation.")

    args = {
        "mac": reservation_mac,
        "name": vm.name,
        "fixed_ip": vm.ip_address,
        "allow_existing": True,
        "skip_forget_on_destroy": True,
    }
    if network_id:
        args["network_id"] = network_id

    return unifi.iam.User(
        clean_resource_name(f"{vm.name}-dhcp"),
        opts=pulumi.ResourceOptions(provider=provider),
        **args,
    )


def build_unifi_resources(server_list: ServerListConfig) -> Dict[str, List[pulumi.Resource]]:
    required = bool(server_list.dns_records) or any(needs_unifi(vm) for vm in server_list.virtual_machines)
    provider = build_provider(required)
    resources_by_vm: Dict[str, List[pulumi.Resource]] = {}
    if provider is None:
        return resources_by_vm

    for record in server_list.dns_records:
        build_dns_record("static-dns", record, provider)

    for vm in server_list.virtual_machines:
        if not needs_unifi(vm):
            continue
        resources: List[pulumi.Resource] = []
        reservation = build_dhcp_reservation(vm, provider)
        if reservation is not None:
            resources.append(reservation)
        for record in vm.dns_records:
            resources.append(build_dns_record(vm.name, record, provider, vm.ip_address))
        resources_by_vm[vm.name] = resources

    return resources_by_vm
