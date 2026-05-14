FROM registry.access.redhat.com/ubi9/ubi:latest
WORKDIR /workspaces
COPY ./collections/requirements.yml /tmp/requirements.yml
COPY ./requirements.txt /tmp/requirements.txt
COPY ./deployment/pulumi-proxmox/requirements.txt /tmp/pulumi-proxmox-requirements.txt

# Installing Python Git and Ansible
RUN dnf update -y
RUN dnf install git yum-utils -y
RUN subscription-manager repos --enable codeready-builder-for-rhel-9-$(arch)-rpms | true
RUN dnf install https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm -y
RUN dnf install openssh-clients sshpass python3 python3-pip genisoimage sudo -y 

# Install WinRM Python Module and Proxmox Python Module
RUN pip3 install --upgrade setuptools
RUN pip3 install -r /tmp/requirements.txt
RUN pip3 install -r /tmp/pulumi-proxmox-requirements.txt

# Install Packer
RUN dnf config-manager --add-repo https://rpm.releases.hashicorp.com/RHEL/hashicorp.repo
RUN dnf -y install packer

# Install Docker CLI + buildx (talks to host daemon via mounted socket)
RUN dnf config-manager --add-repo https://download.docker.com/linux/rhel/docker-ce.repo
RUN dnf install -y docker-ce-cli docker-buildx-plugin

# Install K8S Tools
COPY .devcontainer/kubernetes.repo /etc/yum.repos.d/kubernetes.repo
RUN dnf install -y kubectl

# Proton Pass CLI. Container can't reach the kernel keyring, so use the fs provider.
RUN dnf install -y jq
ENV PROTON_PASS_KEY_PROVIDER=fs
RUN curl -fsSL https://proton.me/download/pass-cli/install.sh | PROTON_PASS_CLI_INSTALL_DIR=/usr/local/bin bash \
    && pass-cli --version
COPY images/iac-runner/profile.d/ts-secrets-check.sh /etc/profile.d/ts-secrets-check.sh
RUN chmod 0644 /etc/profile.d/ts-secrets-check.sh

# Install Helm + Helmfile + helm-diff plugin (system-wide so root and turneradmin both see it).
ARG HELMFILE_VERSION=0.171.0
ENV HELM_PLUGINS=/usr/local/share/helm/plugins
RUN curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash \
    && curl -fsSL -o /tmp/helmfile.tgz \
        "https://github.com/helmfile/helmfile/releases/download/v${HELMFILE_VERSION}/helmfile_${HELMFILE_VERSION}_linux_$(uname -m | sed 's/x86_64/amd64/;s/aarch64/arm64/').tar.gz" \
    && tar -xzf /tmp/helmfile.tgz -C /usr/local/bin helmfile \
    && chmod +x /usr/local/bin/helmfile \
    && rm /tmp/helmfile.tgz \
    && mkdir -p "${HELM_PLUGINS}" \
    && helm plugin install https://github.com/databus23/helm-diff \
    && chmod -R a+rX /usr/local/share/helm

# Create the turneradmin user as an administrator
RUN groupadd turneradmin
RUN useradd -s /bin/bash -m -g turneradmin turneradmin
RUN chown turneradmin:turneradmin /workspaces
RUN echo "turneradmin ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/turneradmin
# Prepare home and ~/.ssh
RUN mkdir -p /home/turneradmin/.ssh \
&& chown -R turneradmin:turneradmin /home/turneradmin \
&& chmod 700 /home/turneradmin/.ssh

# Point to where we will bind-mount the host's SSH agent socket
ENV SSH_AUTH_SOCK=/ssh-agent
RUN printf 'Host *\n  StrictHostKeyChecking accept-new\n' > /etc/ssh/ssh_config

# Create .ssh directory and config file for turneradmin
RUN mkdir -p /home/turneradmin/.ssh \
&& printf "Host *\n  ForwardAgent yes" > /home/turneradmin/.ssh/config \
&& chown -R turneradmin:turneradmin /home/turneradmin/.ssh \
&& chmod 700 /home/turneradmin/.ssh \
&& chmod 600 /home/turneradmin/.ssh/config

# Use a non-root user for better security
USER turneradmin

# Configure Git
RUN git config --global --add safe.directory /workspaces

# Install Pulumi
RUN curl -fsSL https://get.pulumi.com | sh

CMD ["/bin/bash"]
