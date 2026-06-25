#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y openssh-server qemu-guest-agent sudo python3 python3-apt cloud-guest-utils lvm2
systemctl enable --now ssh
systemctl enable --now qemu-guest-agent
mkdir -p /var/lib/turner
printf 'pbs first boot completed at %s
' "$(date -Is)" > /var/lib/turner/pbs-first-boot-complete
