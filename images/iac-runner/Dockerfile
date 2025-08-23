FROM registry.access.redhat.com/ubi9/ubi:latest
ARG UID=1000
ARG GID=1000
WORKDIR /workspace

# Installing Python Git and Ansible
RUN dnf update -y
RUN dnf install git yum-utils -y
RUN subscription-manager repos --enable codeready-builder-for-rhel-9-$(arch)-rpms | true
RUN dnf install https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm -y
RUN dnf install openssh-clients sshpass python3 python3-pip genisoimage sudo -y 

# Install WinRM Python Module and Proxmox Python Module
RUN pip3 install --upgrade setuptools
RUN pip3 install ansible
RUN pip3 install pywinrm proxmoxer

# Install OPNsense Collection 
RUN ansible-galaxy collection install ansibleguy.opnsense

# Install Packer
RUN dnf config-manager --add-repo https://rpm.releases.hashicorp.com/RHEL/hashicorp.repo
RUN dnf -y install packer
CMD ["/bin/bash"]

# Create the turneradmin user as an administrator
RUN groupadd -g ${GID} turneradmin
RUN useradd -s /bin/bash -m -u ${UID} -g turneradmin turneradmin
RUN chown turneradmin:turneradmin /workspace
RUN echo "turneradmin ALL=(ALL) NOPASSWD:ALL" | sudo tee /etc/sudoers.d/username
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
RUN git config --global --add safe.directory /workspace

# Launch whatever shell we end up picking...
CMD /bin/bash
