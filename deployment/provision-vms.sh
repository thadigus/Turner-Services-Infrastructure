#!/bin/bash
# An idempotent deployment of Proxmox VMs and their base OS configs.
# The first extra vars file provides the server definitions file that defines hardware and storage for each VM.
# For an example of the server definitions file look at ./server-list-example.yml
# The second extra vars file is the Proxmox plugin based inventory file. This is also used as the inventory to
# generate a dynamic inventory for all VMs in the Proxmox instance. We are using it as an extra vars to expose the
# credentials for the Proxmox API.
# For an example of the Proxmox inventory file look at ../inventories/ansible-inv-example.proxmox.yml

ansible-playbook --extra-vars @./turner-services-sensitive-repo/server-list-rack.yml --extra-vars @./turner-services-sensitive-repo/inventories/ansible-inv-rack.proxmox.yml ./deployment/create-virtual-machines.yml 
