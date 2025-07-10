This README isn't going to get much. Maybe dynamically updated with the infrastructure in place idk.

Role file structure:

- The ‘defaults’ folder – This contains the default variables that will be used by the role.
- The ‘files’ folder – Contains files that can be deployed by the role.
- The ‘handlers’ folder – Stores handlers that can be used by this role.
- The ‘meta’ folder – Contains files that establish the role dependencies.
- The ‘tasks’ folder – It contains a YAML file that spells out the tasks for the role itself. Usually, this is the main.yml file.
- The ‘templates’ folder – Contains template files that can be modified and allocated to the remote host being provisioned.
- The ‘tests’ folder – Integrates testing with Ansible playbook files.
- The ‘vars’ folder – Contains variables that are going to be used by the role. You can define them in the playbook file, but it’s recommended you define them in this directory.