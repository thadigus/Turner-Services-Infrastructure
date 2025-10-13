#!/bin/bash

ansible-playbook --extra-vars @./turner-services-sensitive-repo/server-list-rack.yml --extra-vars @./turner-services-sensitive-repo/inventories/ansible-inv-rack.proxmox.yml ./deployment/create-virtual-machines.yml 
