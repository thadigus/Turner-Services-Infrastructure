from __future__ import annotations

import pulumi

from pulumi_proxmox import build_virtual_machines
from pulumi_unifi import build_unifi_resources
from server_config import load_server_list, resolve_paths, resolve_stack_environment


config = pulumi.Config()
server_list_file, inventory_file = resolve_paths(config)
server_list = load_server_list(server_list_file)
stack_environment = resolve_stack_environment(config, server_list_file)

unifi_dependencies = build_unifi_resources(server_list)
build_virtual_machines(server_list, inventory_file, stack_environment, unifi_dependencies)
