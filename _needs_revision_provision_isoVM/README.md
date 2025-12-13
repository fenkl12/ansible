# Provision VM from ISO

This playbook creates a new VM in Proxmox from an ISO, waits for you to manually install the OS, and then automatically provisions it with the standard configuration (Network, Packages, Dotfiles, Docker).

## Prerequisites

- **Proxmox Credentials**: Ensure `proxmox_api_token_id` and `proxmox_api_token_secret` are set (in `inventory.yml` or passed as extra vars).
- **ISO Image**: The ISO defined in `inventory.yml` must exist on your Proxmox storage.

## Usage

1. **Configure `inventory.yml`**:
   - Set `new_vm_id`, `new_vm_name`, `vm_memory`, `vm_cores`.
   - Set `static_ip` to the IP you intend to give the VM.
   - Set `iso_image` to the filename of your ISO.

2. **Run the playbook**:
   ```bash
   ansible-playbook site.yml
   ```

3. **Manual Step**:
   - The playbook will create the VM and start it.
   - It will then **PAUSE** and ask you to install the OS.
   - Open the Proxmox Console for the new VM.
   - Install the OS. **Important**: Configure the static IP to match what you set in `inventory.yml` and ensure SSH is installed/enabled.
   - Once installation is complete and the VM has rebooted, press **Enter** in the Ansible terminal.

4. **Automatic Provisioning**:
   - Ansible will connect to the new VM.
   - It will run the standard roles: `configure_network`, `common_setup`, and `dotfiles`.

