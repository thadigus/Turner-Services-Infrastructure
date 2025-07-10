FROM registry.access.redhat.com/ubi9/ubi:latest

# Installing Python Git and Ansible
RUN dnf update -y
RUN dnf install git yum-utils -y
RUN subscription-manager repos --enable codeready-builder-for-rhel-9-$(arch)-rpms | true
RUN dnf install https://dl.fedoraproject.org/pub/epel/epel-release-latest-9.noarch.rpm -y
RUN dnf install openssh-clients sshpass python3 python3-pip genisoimage -y 
RUN pip3 install --upgrade setuptools
RUN pip3 install ansible

# Install OPNsense Collection 
RUN ansible-galaxy collection install ansibleguy.opnsense
# Install WinRM Python Module and Proxmox Python Module
RUN pip3 install pywinrm proxmoxer

# Configure Git
RUN git config --global --add safe.directory /code

# Install Packer
RUN dnf config-manager --add-repo https://rpm.releases.hashicorp.com/RHEL/hashicorp.repo
RUN dnf -y install packer
CMD ["/bin/bash"]
