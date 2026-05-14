# Web-based VSCodium (code-server) with the full Turner Services IaC toolchain layered on top.
# Built from the linuxserver code-server base — keeps PUID/PGID handling and s6 init.
FROM lscr.io/linuxserver/code-server:latest

ARG HELMFILE_VERSION=0.171.0
ARG KUBECTL_VERSION=v1.31.0
ARG PULUMI_VERSION=v3.130.0

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg lsb-release \
        git openssh-client sshpass \
        python3 python3-pip python3-venv \
        unzip genisoimage \
        sudo \
        dnsutils iputils-ping \
    && rm -rf /var/lib/apt/lists/*

# kubectl
RUN ARCH="$(dpkg --print-architecture)" \
    && curl -fsSL -o /usr/local/bin/kubectl "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${ARCH}/kubectl" \
    && chmod +x /usr/local/bin/kubectl

# helm
RUN curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

# helmfile
RUN ARCH="$(dpkg --print-architecture)" \
    && curl -fsSL -o /tmp/helmfile.tgz \
        "https://github.com/helmfile/helmfile/releases/download/v${HELMFILE_VERSION}/helmfile_${HELMFILE_VERSION}_linux_${ARCH}.tar.gz" \
    && tar -xzf /tmp/helmfile.tgz -C /usr/local/bin helmfile \
    && chmod +x /usr/local/bin/helmfile \
    && rm /tmp/helmfile.tgz

# helm plugins installed to a shared system location so the runtime user (abc) sees them
ENV HELM_PLUGINS=/usr/local/share/helm/plugins
RUN mkdir -p "${HELM_PLUGINS}" \
    && helm plugin install https://github.com/databus23/helm-diff \
    && chmod -R a+rX /usr/local/share/helm

# packer
RUN curl -fsSL https://apt.releases.hashicorp.com/gpg | gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" \
        > /etc/apt/sources.list.d/hashicorp.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends packer \
    && rm -rf /var/lib/apt/lists/*

# pulumi (system-wide)
RUN curl -fsSL "https://get.pulumi.com/releases/sdk/pulumi-${PULUMI_VERSION}-linux-x64.tar.gz" -o /tmp/pulumi.tgz \
    && tar -xzf /tmp/pulumi.tgz -C /tmp \
    && mv /tmp/pulumi/* /usr/local/bin/ \
    && rm -rf /tmp/pulumi /tmp/pulumi.tgz

# Python deps (ansible, proxmoxer, pulumi plugins) mirror what iac-runner installs
COPY requirements.txt /tmp/requirements.txt
COPY deployment/pulumi-proxmox/requirements.txt /tmp/pulumi-proxmox-requirements.txt
RUN pip3 install --break-system-packages --upgrade setuptools \
    && pip3 install --break-system-packages -r /tmp/requirements.txt \
    && pip3 install --break-system-packages -r /tmp/pulumi-proxmox-requirements.txt

# Ansible collections — installed system-wide so the runtime user finds them
COPY collections/requirements.yml /tmp/ansible-collections.yml
RUN ansible-galaxy collection install -r /tmp/ansible-collections.yml -p /usr/share/ansible/collections

# Default workspace lives on the PVC mounted at /config (linuxserver convention).
# code-server opens /config/workspace as the project root on first launch.
ENV DEFAULT_WORKSPACE=/config/workspace

# Do not set USER — linuxserver's s6 init drops to abc with PUID/PGID at runtime.
