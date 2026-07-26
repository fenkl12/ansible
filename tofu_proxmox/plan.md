# Ubuntu ISO–Based Proxmox Provisioning with Packer and OpenTofu

## Summary

Build a new provisioning system in `tofu_proxmox` with two layers:

1. Packer performs one unattended Ubuntu 24.04 Server installation from `SAN2TB:iso/ubuntu-24.04-live-server-amd64.iso` and converts VMID `900` into a reusable Proxmox template.
2. OpenTofu clones that template into the eight core VMs, configures hardware and cloud-init, then hands the resulting fleet to consolidated Ansible base/profile roles.

A `make deploy` workflow will run infrastructure and guest configuration as explicit sequential stages. Packer’s Proxmox ISO builder supports this ISO-to-template flow, while the maintained `bpg/proxmox` provider supports cloning and cloud-init customization.

- [Packer Proxmox ISO builder](https://developer.hashicorp.com/packer/integrations/hashicorp/proxmox/latest/components/builder/iso)
- [bpg Proxmox clone guide](https://bpg.sh/docs/guides/clone-vm/)

## Implementation Changes

### ISO template factory

- Pin Packer and its Proxmox plugin; validate that VMID `900`, staging IP `10.0.5.55`, and the ISO exist before building.
- Boot the ISO through Packer’s console automation with `autoinstall ds=nocloud-net`, serving user-data and meta-data from Packer’s temporary HTTP server.
- Install Ubuntu using:
  - Host `10.0.5.55/16`, gateway `10.0.0.1`, bridge `vmbr0`.
  - User `fenkil`, SSH-key-only login, passwordless sudo.
  - `cloud-init`, `qemu-guest-agent`, Python, and base SSH packages.
- Before templating, clean cloud-init state, machine ID, SSH host keys, temporary installer data, and package caches so every clone initializes independently.
- Configure VirtIO networking, SCSI disk, QEMU guest agent, boot-from-disk, and removal of the installer ISO.

### OpenTofu fleet

- Pin OpenTofu-compatible `bpg/proxmox` and supporting providers; use `proxmox_virtual_environment_vm` because the newer cloned-VM resource is experimental and cannot manage clone cloud-init initialization.
- Define one validated `map(object(...))` fleet variable containing VMID, name, profile, address, CPU, memory, disk, and optional tags.
- Use defaults of 2 vCPU, 4096 MB RAM, and 40 GB disk while allowing per-VM overrides.
- Seed the initial fleet as:

| VMID | Name | Address | Profile |
|---:|---|---|---|
| 901 | ansibleTower | 10.0.10.10/16 | ansible |
| 902 | docker_central | 10.0.10.20/16 | docker-central |
| 903 | docker_main | 10.0.10.30/16 | docker-main |
| 904 | mediaServer | 10.0.10.40/16 | media |
| 905 | monitoringServer | 10.0.10.50/16 | monitoring |
| 906 | perServer | 10.0.10.60/16 | personal-server |
| 907 | devServer | 10.0.10.70/16 | development |
| 908 | playVM | 10.0.30.20/16 | play |

- Clone full disks onto `SAN2TB`, attach `vmbr0`, and supply hostname, static address, gateway, DNS, SSH key, and user through Proxmox cloud-init.
- Add validation for unique VMIDs, names, and IPs; valid CIDRs; allowed profiles; positive resource sizes; and VMIDs distinct from template VMID `900`.
- Protect managed VMs with `prevent_destroy`; replacement requires an intentional lifecycle change.
- Output a nonsensitive host/profile map. Render the ignored Ansible inventory from `tofu output -json`, rather than storing generated inventory in source control.

### Ansible integration and cleanup

- Replace the temporary-IP workflow, duplicated Netplan files, hostname playbooks, forced reboots, sleeps, and static inventories. Cloud-init owns first-boot networking and hostname.
- Consolidate reusable roles for common packages, dotfiles, Docker/Compose, NFS/backup, media services, monitoring, Samba, and container deployment; select roles through each host’s profile.
- Preserve intended profile behavior while making tasks idempotent:
  - Use repository keyrings and current Docker Compose plugin packages instead of deprecated `apt_key` and pinned downloaded binaries.
  - Explicitly list dotfiles playbooks instead of running every discovered YAML file with ignored failures.
  - Configure and verify NFS/autofs before creating backup jobs.
  - Replace destructive Uptime Kuma reinstall steps with declarative container management.
  - Keep container deployment profile-specific and report failures instead of broadly ignoring them.
- Move Proxmox tokens, login material, Samba credentials, and monitoring URLs out of tracked YAML into environment variables or Ansible Vault. Rotate the credentials currently embedded in repository files.
- Keep the old provision/setup directories as migration references initially; mark them deprecated rather than deleting them during the first implementation.

## Public Workflow and Interfaces

- `make check`: validate prerequisites, credentials, ISO availability, VMID/IP conflicts, formatting, and configuration.
- `make template`: build or deliberately rebuild Proxmox template VMID `900`.
- `make plan`: run the OpenTofu fleet plan without applying it.
- `make apply`: create/update infrastructure only.
- `make configure`: render inventory, wait for cloud-init and SSH, then run base and assigned profile roles.
- `make deploy`: run `check`, `apply`, and `configure` in order.
- `make reconcile VM=<name>`: rerun Ansible for one existing VM without changing infrastructure.
- Provider credentials come from environment variables; SSH public/private key paths and nonsecret infrastructure settings use documented tfvars/Packer variables.
- Local state and generated artifacts are ignored by Git. Remote state is deferred because no backend currently exists.

## Test Plan

- Run Packer formatting/validation and verify its generated autoinstall YAML parses correctly.
- Run `tofu fmt -check`, `tofu validate`, and a plan covering all eight `for_each` instances.
- Test variable failures for duplicate VMIDs/IPs, malformed CIDRs, template-ID reuse, unknown profiles, and invalid resource sizes.
- Run Ansible syntax checks and check mode for every profile; verify generated inventory groups and host variables.
- Provision one disposable clone first and confirm unattended installation/template cloning, static networking, hostname, SSH-key login, sudo, cloud-init completion, and QEMU guest-agent reporting.
- Run configuration twice and require the second Ansible run to be idempotent except for explicitly documented container updates.
- Before fleet deployment, fail safely if VMID `900–908` exists or any target/staging IP responds; never overwrite or import an existing VM automatically.
- Accept the implementation when `make deploy` can create the selected fleet without console interaction and a subsequent `make plan` reports no infrastructure drift.

## Assumptions

- Proxmox remains at `https://10.0.5.100:8006`, node name `proxmox`, storage `SAN2TB`, and bridge `vmbr0`.
- Ubuntu 24.04 Server ISO is already present at the existing Proxmox datastore path.
- The machine running Packer is reachable from the staging VM’s network while its temporary HTTP seed server is active.
- VMIDs `900–908`, staging IP `10.0.5.55`, and the eight target addresses will be verified as unused. Existing VMs remain unmanaged and are not replaced.
- All initial VMs use the default resource size unless an override is deliberately added to the fleet map.
