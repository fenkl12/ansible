# Usage and operations

Install OpenTofu 1.7+, Python 3.11+, Ansible, `make`, `ping`, and `ip`. The provider is pinned for the discovered TrueNAS SCALE 24.04.2.5 host.

Store `TRUENAS_API_KEY=...` in `.secrets/truenas.env` with mode `0600`. Set `VM_SSH_PUBLIC_KEY` if the guest key is not `~/.ssh/id_ed25519.pub` or `~/.ssh/id_rsa.pub`.

## Register and deploy

```sh
make new-vm
make deploy VM=web_IP40
```

The generator combines TrueNAS VM names, `_IPXX` suffixes, the fleet registry, neighbors, and ping results. It offers available multiples of ten from `10.0.203.20` through `.240`. Offline devices might not answer, so confirm the address before accepting it.

Each VM has committed non-secret configuration under `deployments/<name>/`. Its ignored OpenTofu state is stored there too and should be backed up securely.

```sh
make list
make suggest NAME=web
make plan VM=web_IP40
make configure VM=web_IP40
make check
```

## Ubuntu installation

The default ISO is `/mnt/WD1TB/ISOs/ubuntu-24.04-live-server-amd64.iso`. It must exist and support Subiquity autoinstall. OpenTofu creates a blank protected zvol and a cloud-init/autoinstall seed ISO. If an ordinary installer ignores the seed, complete that VM's first install through the TrueNAS display and rerun `make deploy`.

The generator accepts one relative playbook path inside the cloned dotfiles repository. Leave it blank to skip it. Absolute paths and paths containing `..` are rejected.

## Safety

- Existing pools, datasets, shares, interfaces, and VMs remain untouched.
- New zvols use `prevent_destroy`.
- Preflight rejects unmanaged duplicate VM names and responding addresses.
- Do not delete a deployment or its state before deliberately retiring its VM.
- Preflight stops after an upgrade away from TrueNAS 24.04 pending compatibility review.

