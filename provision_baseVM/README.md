# Proxmox VM Provisioning with Ansible

This project automates the provisioning of a Virtual Machine on Proxmox from a template. It handles the entire lifecycle from cloning the VM to configuring the network, installing essential packages, and setting up user dotfiles.

## Features

*   **Proxmox Integration**: Clones a VM from a template using the Proxmox API.
*   **Smart IP Assignment**: Automatically scans the `10.0.10.x` range (in increments of 10) to suggest the next available static IP.
*   **Network Configuration**: Configures a static IP address using Netplan.
*   **System Setup**: Installs essential packages (git, curl, htop, etc.) and sets the timezone.
*   **Dotfiles Management**: Clones a dotfiles repository and runs local Ansible playbooks for user environment setup.
*   **Modular Design**: Uses Ansible Roles for better organization and maintainability.

## Prerequisites

*   Ansible installed on the control node.
*   Access to a Proxmox VE server.
*   A Proxmox API Token (ID and Secret).
*   A VM Template already created on Proxmox (Cloud-Init enabled recommended).

## Directory Structure

```
.
├── group_vars/
│   └── all.yml             # Global configuration variables
├── inventory.yml           # Ansible inventory file
├── roles/
│   ├── common_setup/       # Installs packages and sets timezone
│   ├── configure_network/  # Sets up static IP and Netplan
│   ├── dotfiles/           # Clones and applies dotfiles
│   └── provision_vm/       # Clones and starts the VM on Proxmox
├── run_provision.sh        # Helper script to run the provisioning
├── site.yml                # Master playbook
└── _legacy/                # Old scripts and playbooks (backup)
```

## Configuration

Key configuration variables are located in `group_vars/all.yml`. You can modify defaults there or override them at runtime.

*   `proxmox_api_url`: URL to your Proxmox API.
*   `proxmox_node`: Name of the Proxmox node.
*   `proxmox_template_vm_id`: ID of the template to clone from.
*   `static_ip`: The desired static IP for the new VM.
*   `proxmox_api_token_id` / `proxmox_api_token_secret`: Credentials for Proxmox API.

**Security Note**: It is highly recommended to move sensitive credentials (API tokens) to an Ansible Vault file.

## Usage

### Using the Helper Script (Recommended)

The `run_provision.sh` script provides an interactive way to set the VM ID, Name, and Template details.

```bash
./run_provision.sh
```

When you run the script it will:

- Ask for VM ID and generate a default VM name if you don't provide one.
- Require you to select one of the three allowed templates (501, 502, 503). The template IP is set automatically.
- Scan `10.0.10.x` in increments of 10 and suggest an available static IP; you can accept or override it.
- Optionally prompt for the sudo/become password which will be passed to Ansible for this run (or you can let Ansible ask interactively with `-K`).

If you prefer automated runs, set `enable_passwordless_sudo: true` in `group_vars/all.yml` for the `provision_user` (not recommended for public or shared systems).

### Using Ansible Directly

You can run the playbook directly using `ansible-playbook`. You must provide the necessary extra variables.

```bash
ansible-playbook -i inventory.yml site.yml \
  --extra-vars "proxmox_vm_id=205 proxmox_vm_name=MyNewVM proxmox_template_vm_id=503 template_vm_ip=10.0.6.30"
```

## Roles Overview

1.  **provision_vm**:
    *   Clones the template.
    *   Configures cores and memory.
    *   Starts the VM.
    *   Waits for SSH to become available on the template IP.

2.  **configure_network**:
    *   Connects to the VM.
    *   Applies Netplan configuration for a static IP.
    *   Restarts networking.

3.  **common_setup**:
    *   Updates apt cache.
    *   Installs tools like `git`, `tmux`, `htop`, `ansible`.
    *   Sets the timezone to `America/Toronto`.

4.  **dotfiles**:
    *   Clones the dotfiles repository.
    *   Runs any Ansible playbooks found within the dotfiles repo.
    *   Changes the default shell to Zsh.
