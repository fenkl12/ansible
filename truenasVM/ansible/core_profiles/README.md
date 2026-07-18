# Core profiles

Each directory below this one defines the complete VM-specific desired state for one kind of VM.
Create a profile with `make new-core-profile PROFILE=<name>` and replace the generated scaffold task.

Profiles must contain `site.yml`, `vars.yml`, and `profile.json`. The manifest declares
`requires_backup_storage` as `true` or `false`; newly scaffolded profiles default to `false`.
Profiles may add `files/`, `templates/`, or roles as needed.
Do not add static inventories, VM provisioning, or network-address changes here; the factory supplies the
deployment inventory and OpenTofu owns TrueNAS infrastructure.

Keep tasks idempotent. When removing software or configuration, declare `state: absent` explicitly so a
reconciliation removes it from existing guests as well as omitting it from clean rebuilds.

## Included profiles

- `databases`: installs Docker Engine and Compose v2, deploys Portainer, assigns a configurable hostname,
  and configures consistent nightly pcData backups. Its manifest requires healthy shared backup storage
  before profile assignment or execution.
