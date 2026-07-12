# Usage and operations

Install OpenTofu 1.7+, Python 3.11+, Ansible, `make`, `ping`, and `ip`. The provider is pinned for the discovered TrueNAS SCALE 24.04.2.5 host.

Store `TRUENAS_API_KEY=...` in `.secrets/truenas.env` with mode `0600`. Set `VM_SSH_PUBLIC_KEY` if the guest key is not `~/.ssh/id_ed25519.pub` or `~/.ssh/id_rsa.pub`.

## Register and deploy

```sh
make new-vm
make deploy VM=web_IP40
make vm-password VM=web_IP40
```

All new VMs use `fenkil` as the TrueNAS SPICE connection password and the Ubuntu `fenkil` account password for console and SSH login. SSH keys remain enabled.

The generator combines TrueNAS VM names, `_IPXX` suffixes, the fleet registry, neighbors, and ping results. It offers available multiples of ten from `10.0.203.20` through `.240`. Offline devices might not answer, so confirm the address before accepting it.

Each VM has committed non-secret configuration under `deployments/<name>/`. Its ignored OpenTofu state is stored there too and should be backed up securely.

```sh
make list
make suggest NAME=web
make plan VM=web_IP40
make configure VM=web_IP40
make check
```

## Retire a VM

`make destroy VM=web_IP40` removes the VM definition while preserving its disk. To permanently delete that protected zvol after the VM is gone, run:

```sh
make destroy-disk VM=web_IP40
```

The disk command refuses to run while the VM still exists. It deletes only the deployment's expected zvol, then removes that disk resource from the deployment's OpenTofu state. This is permanent.

After both steps complete, remove the deployment configuration, ignored state/backups, generated build files, legacy per-VM password files, and fleet registry entry:

```sh
make remove-deployment VM=web_IP40
```

This command refuses cleanup while either the VM or expected zvol exists. It never removes shared templates.

## Ubuntu installation

The default ISO is `/mnt/WD1TB/ISOs/ubuntu-24.04-live-server-amd64.iso`. It must exist and support Subiquity autoinstall. OpenTofu creates a blank protected zvol and a cloud-init/autoinstall seed ISO. If an ordinary installer ignores the seed, complete that VM's first install through the TrueNAS display and rerun `make deploy`.

New VMs run these dotfiles playbooks from the cloned repository: Zsh, Neovim, Codex, and MyScripts. They run in order from `ansible_localPc/`; absolute paths and paths containing `..` are rejected.

## Safety

- Existing pools, datasets, shares, interfaces, and VMs remain untouched.
- New zvols use `prevent_destroy`.
- Disk deletion requires the explicit `destroy-disk` command after VM removal.
- Preflight rejects unmanaged duplicate VM names and responding addresses.
- Do not delete a deployment or its state before deliberately retiring its VM.
- Preflight stops after an upgrade away from TrueNAS 24.04 pending compatibility review.

