# Usage and operations

Install OpenTofu 1.7+, Python 3.11+, Ansible, `make`, `ping`, `ip`, `curl`, and `xorriso`. The provider is pinned for the discovered TrueNAS SCALE 24.04.2.5 host.

Store `TRUENAS_API_KEY=...` in `.secrets/truenas.env` with mode `0600`. Set `VM_SSH_PUBLIC_KEY` if the guest key is not `~/.ssh/id_ed25519.pub` or `~/.ssh/id_rsa.pub`.

Install the pinned Ansible collection dependencies once:

```sh
make dependencies
```

## Register and provision the base

```sh
make new-vm
make provision-base VM=web_IP40
make vm-password VM=web_IP40
```

All new VMs use `fenkil` as the TrueNAS SPICE connection password and the Ubuntu `fenkil` account password for console and SSH login. SSH keys remain enabled.

The generator combines TrueNAS VM names, `_IPXX` suffixes, the fleet registry, neighbors, and ping results. It offers available multiples of ten from `10.0.203.20` through `.240`. Offline devices might not answer, so confirm the address before accepting it.

Each VM has committed non-secret configuration under `deployments/<name>/`. Its ignored OpenTofu state is stored there too and should be backed up securely.

```sh
make list
make suggest NAME=web
make plan VM=web_IP40
make configure-base VM=web_IP40
make check
```

`deploy` and `configure` remain base-only aliases for older command lines.

## Core profiles

Every VM may be assigned one core profile. A profile is the repository-owned desired state for software,
services, configuration, containers, users, and other VM-specific behavior. Create a scaffold and replace
its placeholder task:

```sh
make new-core-profile PROFILE=databases
# Edit ansible/core_profiles/databases/site.yml and vars.yml
make setup-core VM=web_IP40 PROFILE=databases
```

The first core run saves the assignment. Later runs do not need `PROFILE`:

```sh
make setup-core VM=web_IP40
make preview VM=web_IP40
make reconcile VM=web_IP40
```

`setup-core` applies only the assigned profile and requires a successful base configuration.
`reconcile` reapplies the base first and then the assigned core profile. This is the normal entrypoint
for all later guest changes.

To deliberately change a VM's identity, run:

```sh
make change-core-profile VM=web_IP40 PROFILE=media-server
```

This does not remove state installed by the old profile. Rebuild the VM for a strictly clean transition.

## Reproducibility rules

- Do not make persistent changes directly on a managed VM. Declare them in the base or its core profile.
- Keep profile tasks idempotent and rerunnable.
- Removing an installation task does not uninstall its result. Add an explicit `state: absent` task when
  removing a managed package, file, service, user, or container from existing guests.
- Commit Compose files, templates, and other non-secret configuration alongside the profile.
- Keep credentials outside Git and inject them through the existing secrets mechanism or Ansible Vault.
- Repository package versions may advance unless a profile explicitly pins them. The target is the same
  declared services and configuration, rather than a byte-identical disk.

`make preview` performs an OpenTofu plan and Ansible check/diff for both configuration layers. Ansible
check mode is best-effort for modules that do not fully support it. The command never applies infrastructure;
use `make apply` explicitly for reviewed TrueNAS resource changes.

## Shared VM backup storage

The backup dataset, NFS export, and snapshot schedule have their own OpenTofu state and are not owned by
any VM. Preview and create them once:

```sh
make backup-storage-plan
make backup-storage-apply
make backup-storage-check
```

This creates:

- `tank/backups/truenasVM/dataOnly` with protected parent and child datasets.
- A writable NFS export at `/mnt/tank/backups/truenasVM/dataOnly`, restricted to `10.0.0.0/16`.
- Daily snapshots at 02:00 with 30-day retention.

The state under `opentofu/backup-storage/` is ignored and must be backed up securely. The stack has no
destroy target, and its datasets and NFS share use `prevent_destroy`.

`backup-storage-apply` is the explicit one-time creation/reconciliation command. Core-profile commands
never invoke it. Backup-enabled profiles run `backup-storage-check` before assignment or Ansible changes;
if either dataset, the writable NFS export, or the 30-day snapshot task is unavailable, they stop and tell
the operator to run the one-time apply command.

## Docker-main profile

The included `databases` profile installs Docker Engine from Docker's official Ubuntu repository,
installs Compose v2, and deploys Portainer plus PostgreSQL using the pgvector image:

```sh
make setup-core VM=databases_IP40 PROFILE=databases
```

Portainer is exposed on port `9000`; its persistent data and Compose definition live under
`/home/fenkil/pcData/portainer`. PostgreSQL uses `pgvector/pgvector:0.8.5-pg17` and is exposed on port `5432` bound to the VM's
assigned address. Its persistent data, protected environment file, Compose definition, and initialization
schema live under `/home/fenkil/pcData/pgvector`. The default database is `pi_memory`; `init.sql` enables
the `vector` extension when a new data directory is initialized.

The guest hostname defaults to the registered VM name converted to lowercase DNS form. For example,
`databases_IP40` becomes `databases-ip40`. Override it per deployment by adding:

```yaml
docker_main_hostname: databases
```

to `deployments/<vm>/ansible-vars.yml`. Backup directories continue using the stable registered VM name,
so changing the guest hostname does not split backup history.

Backups are disabled by default because a VM attached directly to the TrueNAS physical interface cannot
reach an NFS service on that same host. After configuring a bridge or otherwise confirming guest access
to the TrueNAS NFS address, opt in per deployment by adding:

```yaml
docker_main_backup_enabled: true
```

to `deployments/<vm>/ansible-vars.yml`, run `make backup-storage-check`, and rerun `make setup-core`.
The enabled profile mounts the shared export at `/mnt/tn_truenasVMData` and installs a persistent midnight
systemd timer. A backup verifies the destination is NFS, stops Portainer, mirrors all of
`/home/fenkil/pcData` with deletion propagation, and restarts Portainer even when rsync fails. Run one
immediately with:

```sh
make backup-now VM=databases_IP40
```

Inspect scheduled and manual runs with:

```sh
systemctl status pcdata-backup.timer
journalctl -u pcdata-backup.service
```

Because the mirror propagates deletions, use the TrueNAS snapshots to recover older files.

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

The default ISO is `/mnt/WD1TB/ISOs/ubuntu-24.04-live-server-amd64.iso`. It remains unchanged. On first use, `make provision-base` downloads it, extracts its existing `vmlinuz` and `initrd`, and uploads those reusable boot files beside the ISO. OpenTofu creates the VM stopped; it does not control runtime power state. The provisioning orchestrator then direct-boots the installer with the `autoinstall` kernel argument while the provider-generated CIDATA ISO supplies each VM's answers.

A stopped installer is never treated as proof of success. After Subiquity powers off, provisioning clears the temporary boot arguments, boots from the protected zvol, and requires SSH, a non-overlay root filesystem, and `/etc/truenas-vm-installed` before advancing the deployment from `install` to `bootstrap`. Re-running `make provision-base` resumes a verified checkpoint or safely retries an unverified installer.

Run `make prepare-installer VM=<name>` to prepare or verify the shared boot files separately. This is optional because `make provision-base` invokes it automatically when needed. Use `make vm-status VM=<name>` for a read-only report of OpenTofu state ownership, VM state, boot arguments, devices, zvol presence, installer checkpoint, and installed-guest readiness.

New VMs run these dotfiles playbooks from the cloned repository: Zsh, Neovim, Codex, and MyScripts. They run in order from `ansible_localPc/`; absolute paths and paths containing `..` are rejected.

## Safety

- Existing pools, datasets, shares, interfaces, and VMs remain untouched.
- New zvols use `prevent_destroy`.
- Disk deletion requires the explicit `destroy-disk` command after VM removal.
- Preflight rejects unmanaged duplicate VM names and responding addresses.
- Do not delete a deployment or its state before deliberately retiring its VM.
- Preflight stops after an upgrade away from TrueNAS 24.04 pending compatibility review.
- Reconciliation never applies OpenTofu changes.
- Core profiles cannot run until base configuration has completed successfully.
