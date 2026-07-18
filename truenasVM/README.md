# TrueNAS VM Factory

Declarative OpenTofu provisioning and Ansible configuration for reproducible Ubuntu VMs on TrueNAS SCALE.

VM management has two layers:

1. A reusable base installs Ubuntu and the common packages, login configuration, media mount, and dotfiles.
2. One assigned core profile declares the programs, services, and configuration specific to that VM.

Register and provision a base VM, then create or assign its core profile:

```sh
make new-vm
make provision-base VM=<name>
make new-core-profile PROFILE=<profile>
make setup-core VM=<name> PROFILE=<profile>
```

After setup, make all guest changes in Ansible and apply them with `make reconcile VM=<name>`. Use
`make preview VM=<name>` first to view both the OpenTofu plan and Ansible check/diff output. Infrastructure
changes are never applied by reconciliation; run `make apply VM=<name>` explicitly.

See [docs/USAGE.md](docs/USAGE.md) for the full workflow and reproducibility rules.

The included `databases` profile installs Docker Engine and Compose v2, deploys Portainer, and mirrors
the VM's `/home/fenkil/pcData` directory to protected shared TrueNAS storage. Provision that storage once
with `make backup-storage-plan` and `make backup-storage-apply` before assigning the profile.
Later core setup, preview, reconciliation, and manual backup commands perform a read-only availability
check and never recreate or apply the shared storage stack.
