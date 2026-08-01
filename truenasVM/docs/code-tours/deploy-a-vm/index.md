# Deploy a VM

This beginner-first guide explains how to register, review, provision, configure,
and verify one Ubuntu VM with this repository.

Scope: the normal first-time deployment path driven by the root `Makefile`.
Intended reader: an operator who is new to this repository.

## What the process does

The workflow records the VM you want, creates it on TrueNAS, installs Ubuntu,
applies the reusable base configuration, and optionally gives the VM a core
software profile.

```mermaid
flowchart LR
    A[Prepare tools] --> B[Register VM]
    B --> C[Review plan]
    C --> D[Provision Ubuntu]
    D --> E[Apply core profile]
    E --> F[Verify and maintain]
```

## Things to know first

1. Run all commands from the repository root.
2. Replace `web_IP40` below with the exact name selected by `make new-vm`.
3. `make plan` is a preview; `make provision-base` makes real TrueNAS changes.
4. `deployments/<vm>/` holds lasting VM configuration and infrastructure state.
5. `build/<vm>/` holds generated inventory, SSH host information, and progress markers.

## Step-by-step process

### 1. Open the repository

```bash
cd /home/fenkil/pcData/ansible/truenasVM
```

### 2. Prepare the required tools

Install the software listed in `docs/USAGE.md`, then install the pinned Ansible
collections:

```bash
make dependencies
make check
```

The Makefile uses `.tools/tofu` by default. If OpenTofu is available as the system
command `tofu`, add `TOFU=tofu` to commands that invoke it, for example:

```bash
make plan VM=web_IP40 TOFU=tofu
```

### 3. Configure local access

The TrueNAS API credential belongs in `.secrets/truenas.env`:

```text
TRUENAS_API_KEY='your-api-key'
```

Protect the file with `chmod 600 .secrets/truenas.env`. Never commit it.

The VM factory also needs an SSH public key. It checks these locations by default:

```text
~/.ssh/id_ed25519.pub
~/.ssh/id_rsa.pub
```

To use another public key, set its path before registering the VM:

```bash
export VM_SSH_PUBLIC_KEY=/path/to/your/key.pub
```

### 4. Register the VM

```bash
make new-vm
```

Enter a short base name such as `web`. The program checks TrueNAS, the fleet
registry, network neighbors, and ping results, then offers candidate names and IP
addresses. A possible selection is `web_IP40` at `10.0.203.40`.

Registration creates:

```text
deployments/web_IP40/deployment.auto.tfvars.json
deployments/web_IP40/ansible-vars.yml
```

It also adds the VM to `fleet.json`.

### 5. Review the lasting configuration

```bash
sed -n '1,200p' deployments/web_IP40/deployment.auto.tfvars.json
sed -n '1,200p' deployments/web_IP40/ansible-vars.yml
```

Confirm the VM name, IP address, CPU count, memory, disk size, storage pool, and
network attachment. Make intentional configuration edits before provisioning.

### 6. Preview the infrastructure changes

```bash
make plan VM=web_IP40
```

If using the system OpenTofu binary:

```bash
make plan VM=web_IP40 TOFU=tofu
```

Verify that the plan creates the expected VM and protected disk and does not modify
unrelated resources. Stop here if anything is unexpected.

### 7. Provision the Ubuntu base

```bash
make provision-base VM=web_IP40
```

This command performs the following guided trace:

1. Checks for conflicting VM names, IP addresses, and storage.
2. Prepares reusable Ubuntu installer boot files.
3. Creates the TrueNAS VM and protected disk.
4. Runs the unattended Ubuntu installation.
5. Detaches the temporary installer and changes the phase to `bootstrap`.
6. Boots the installed guest and waits for SSH and installation evidence.
7. Generates the Ansible inventory and SSH `known_hosts` file under `build/web_IP40/`.
8. Applies the reusable base Ansible configuration.
9. Writes completion markers under `build/web_IP40/`.

The command automatically approves its OpenTofu apply after the explicit plan in
the previous step. If using system OpenTofu, run:

```bash
make provision-base VM=web_IP40 TOFU=tofu
```

`make deploy VM=web_IP40` is a backward-compatible alias for this base-only stage.
It does not apply a core profile.

### 8. Verify the base VM

```bash
make vm-status VM=web_IP40
make list
make vm-password VM=web_IP40
```

The VM should exist, its protected disk should exist, installer boot arguments
should be absent, and `make list` should report `base-ready`.

Test the guest connection using the chosen address:

```bash
ssh fenkil@10.0.203.40
```

### 9. Optionally assign a core profile

A core profile gives the VM its main software and purpose. To use the included
database profile:

```bash
make setup-core VM=web_IP40 PROFILE=databases
```

The first successful assignment is recorded in `fleet.json`. Later runs resolve the
saved profile automatically:

```bash
make setup-core VM=web_IP40
```

Stop after Step 8 if only a base Ubuntu VM is required.

### 10. Preview and reconcile later changes

```bash
make preview VM=web_IP40
make reconcile VM=web_IP40
```

`preview` reports infrastructure, base, and core drift without applying
infrastructure changes. `reconcile` reapplies the base and assigned core profile;
it does not apply an OpenTofu infrastructure change.

## Concrete example

For a database VM selected as `databases_IP40`, the main happy path is:

```bash
make new-vm
make plan VM=databases_IP40
make provision-base VM=databases_IP40
make vm-status VM=databases_IP40
make setup-core VM=databases_IP40 PROFILE=databases
make preview VM=databases_IP40
```

Afterward, the lasting definition is under `deployments/databases_IP40/`, while
generated connection files and completion markers are under `build/databases_IP40/`.

## Safe practice exercise

Run the read-only listing and status commands for an existing deployment:

```bash
make list
make vm-status VM=<existing-deployment-name>
```

Before opening the files, predict which values will come from `deployments/<vm>/`
and which progress markers will come from `build/<vm>/`. Do not run `provision-base`,
`apply`, or a destruction command for this exercise.

## Verification checklist

- `make plan VM=<name>` showed only the intended infrastructure changes.
- `make provision-base VM=<name>` completed successfully.
- `make vm-status VM=<name>` reports an installed, ready guest.
- `make list` reports `base-ready`.
- `build/<name>/inventory.yml` exists.
- SSH reaches the expected IP and host.
- If assigned, `make setup-core VM=<name>` completed successfully.
- `make preview VM=<name>` reports only understood drift.

## Source evidence

- `Makefile`: `new-vm`, `plan`, `provision-base`, `inventory`, `configure-base`,
  `setup-core`, `preview`, `reconcile`, and `vm-status` targets.
- `scripts/vm_factory.py`: `register()`, `cmd_inventory()`, `cmd_list()`, and
  deployment validation.
- `scripts/installer_boot.py`: installer preparation, installation, and completion
  marker handling.
- `scripts/truenas_ops.py`: preflight, readiness checks, verification, and status.
- `scripts/core_profiles.py`: base completion markers and core-profile assignment.
- `docs/USAGE.md`: prerequisites, operational rules, installation lifecycle, and
  safety guidance.
- `.gitignore`: generated build files and OpenTofu state exclusions.

## Verified assumptions and unresolved details

Verified from the current repository:

- `provision-base` is the complete base installation path.
- `deploy` is a base-only alias.
- OpenTofu variables and per-VM state live under `deployments/<vm>/`.
- Ansible inventory, SSH host keys, and completion markers live under `build/<vm>/`.
- Core-profile setup requires a successfully configured base.

Environment-dependent details that must be checked locally:

- Whether the default `.tools/tofu` executable or `TOFU=tofu` should be used.
- Whether the selected VM name and IP remain available at deployment time.
- Whether the configured TrueNAS version, storage pool, interface, ISO, credentials,
  and network path match the repository defaults.

This generated guide can drift as the Makefile and scripts change. Recheck the cited
sources before using it after substantial repository updates.
