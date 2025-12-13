# Proxmox LXC Provisioning (Tower 10.0.10.10)

Provision and configure Ubuntu LXC containers on Proxmox (10.0.5.100) from the tower VM.

## Prerequisites
- Ubuntu tower at 10.0.10.10 with Python 3.10+.
- Proxmox API token id: `root@pam!tony`; token secret in env `PROXMOX_TOKEN_SECRET`.
- Proxmox node name (default `pve`) and template (default `local:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst`).
- `ansible` and `sshpass` installed on the tower (for password auth):
  ```sh
  sudo apt-get update && sudo apt-get install -y ansible sshpass
  ```
- Python deps (use venv):
  ```sh
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  ```
- Optional `.env` (never commit):
  ```
  PROXMOX_TOKEN_SECRET=yourSecretHere
  PROXMOX_NODE=pve
  PROXMOX_OS_TEMPLATE=local:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst
  ```
- Ensure tower has `ansible_localPc/site.yml` for zsh/oh-my-zsh playbooks (default path `/home/fenkil/ansible_localPc`). The dotfiles repo already contains the desired `.zshrc`/oh-my-zsh configuration; the local playbook only needs to install zsh/oh-my-zsh packages and should avoid overwriting the cloned dotfiles.
- The tower SSH public key is read automatically from `/home/fenkil/.ssh/id_rsa.pub` (no prompt). Update `DEFAULT_TOWER_PUBKEY` in `provision_lxc.py` if you want a different key.

## Usage
1. Activate venv and export token (or use `.env`):
   ```sh
   source .venv/bin/activate
   export PROXMOX_TOKEN_SECRET=yourSecretHere
   ```
2. Run the provisioner:
   ```sh
   python3 provision_lxc.py [--insecure] [--storage SAN2TB] [--node pve] [--ansible-local-dir /home/fenkil/ansible_localPc]
   ```
3. Answer prompts:
   - Hostname (required)
   - Memory MB (default 1096) and cores (default 1)
  - Tower SSH public key is auto-read from `/home/fenkil/.ssh/id_rsa.pub` (edit `DEFAULT_TOWER_PUBKEY` to change)
4. Script workflow:
   - Finds next CTID ≥ 710 and next IP in 10.0.70.x stepping by 10.
   - Creates and starts LXC with static IP (gw 10.0.70.1, bridge vmbr0) on storage `SAN2TB` unless overridden.
   - Waits for SSH, runs `ansible/site.yml`, then runs `ansible_localPc/site.yml` (zsh/oh-my-zsh).

## What the playbook does (idempotent)
- Creates user `fenkil` (password `fenkil`) with sudo, SSH directory, optional authorized_keys.
- Installs packages: git, curl, wget, htop, stow, tmux, ansible, cron, gcc, rsync, openssh-server, autofs, nfs-common.
- Ensures SSH password auth enabled and service running.
- Creates `/home/fenkil/pcData`.
- Clones dotfiles repo `http://10.0.10.20:7000/fenkil/dotfiles.git` into `/home/fenkil/dotfiles` (branch `main`, force/update).
- Configures autofs (`/mnt /etc/auto.nfs --timeout=60`) with mounts:
  - `/mnt/tn_media` -> `10.0.203.171:/mnt/tank/media`
  - `/mnt/tn_proxmoxVMData` -> `10.0.203.171:/mnt/tank/backups/proxmoxMaster/dataOnly`
- Sets up autofs mounts only (no automated backups): `/home/fenkil/pcData` exists for manual use.

## Troubleshooting
- **API auth failures**: check `PROXMOX_TOKEN_SECRET`, token permissions, and node/template names. Use `--insecure` if Proxmox uses self-signed certs.
- **SSH connectivity**: ensure container reachable on 22; the playbook restarts sshd and enables password auth for `fenkil`. Verify from tower: `ssh fenkil@<ip>` (password `fenkil`).
- **autofs mounts**: on container run `systemctl status autofs` and `ls /mnt/tn_media`; check `/etc/auto.master` and `/etc/auto.nfs` entries.
