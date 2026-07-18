SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

VM ?=
PROFILE ?=
TOFU ?= .tools/tofu
ANSIBLE_PLAYBOOK ?= ansible-playbook
ANSIBLE_GALAXY ?= ansible-galaxy
DEPLOYMENT_DIR = deployments/$(VM)
TFVARS = ../$(DEPLOYMENT_DIR)/deployment.auto.tfvars.json
STATE = ../$(DEPLOYMENT_DIR)/terraform.tfstate
BACKUP_TOFU_DIR = opentofu/backup-storage

.PHONY: help dependencies new-vm new-core-profile change-core-profile list suggest init plan apply backup-storage-init backup-storage-plan backup-storage-apply backup-storage-check core-storage-preflight inventory configure-base configure provision-base deploy setup-core backup-now preview reconcile check destroy destroy-disk remove-deployment vm-password require-vm require-profile

help:
	@echo "make dependencies        Install required Ansible collections"
	@echo "make new-vm              Interactively register a VM"
	@echo "make new-core-profile PROFILE=<name>  Scaffold a declarative core profile"
	@echo "make suggest NAME=web    Show available name/IP suggestions"
	@echo "make list                List registered deployments"
	@echo "make provision-base VM=<name>  Provision and configure the reusable base"
	@echo "make setup-core VM=<name> [PROFILE=<name>]  Apply the assigned core profile"
	@echo "make preview VM=<name>   Preview infrastructure, base, and core drift"
	@echo "make reconcile VM=<name> Reapply base and assigned core desired state"
	@echo "make plan VM=<name>      Preview infrastructure changes"
	@echo "make apply VM=<name>     Explicitly apply infrastructure changes"
	@echo "make backup-storage-plan Preview shared backup dataset/share changes"
	@echo "make backup-storage-apply Apply shared backup dataset/share changes"
	@echo "make backup-storage-check Verify shared backup storage without changes"
	@echo "make backup-now VM=<name> Run the VM's pcData backup immediately"
	@echo "make change-core-profile VM=<name> PROFILE=<name>  Reassign core identity"
	@echo "make deploy/configure    Backward-compatible base-only aliases"
	@echo "make check               Run local validation"
	@echo "make destroy VM=<name>   Destroy VM definition (disk is protected)"
	@echo "make destroy-disk VM=<name> Delete a retired VM's protected disk"
	@echo "make remove-deployment VM=<name> Remove files after VM and disk retirement"
	@echo "make vm-password VM=<name> Show the VM console and SSH login password"

dependencies:
	@$(ANSIBLE_GALAXY) collection install -r ansible/requirements.yml

new-vm:
	@python3 scripts/vm_factory.py create

new-core-profile: require-profile
	@python3 scripts/core_profiles.py create --profile "$(PROFILE)"

change-core-profile: require-vm require-profile
	@requires="$$(python3 scripts/core_profiles.py requires-backup --profile "$(PROFILE)")" || exit $$?; \
		if [ "$$requires" = "true" ]; then \
			python3 scripts/truenas_ops.py backup-storage-check; \
		fi
	@python3 scripts/core_profiles.py change --vm "$(VM)" --profile "$(PROFILE)"

suggest:
	@python3 scripts/vm_factory.py suggest $(if $(NAME),--name "$(NAME)",)

list:
	@python3 scripts/vm_factory.py list

init:
	@command -v $(TOFU) >/dev/null || { echo "OpenTofu is required: https://opentofu.org/docs/intro/install/"; exit 1; }
	@$(TOFU) -chdir=opentofu init

plan: require-vm preflight init
	@TF_VAR_truenas_api_key="$$(python3 scripts/truenas_ops.py secret)" TF_VAR_display_password="$$(python3 scripts/console_password.py $(VM))" TF_VAR_login_password_hash="$$(python3 scripts/login_password.py $(VM) --hash)" $(TOFU) -chdir=opentofu plan -state="$(STATE)" -var-file="$(TFVARS)"

apply: require-vm preflight init
	@TF_VAR_truenas_api_key="$$(python3 scripts/truenas_ops.py secret)" TF_VAR_display_password="$$(python3 scripts/console_password.py $(VM))" TF_VAR_login_password_hash="$$(python3 scripts/login_password.py $(VM) --hash)" $(TOFU) -chdir=opentofu apply -state="$(STATE)" -var-file="$(TFVARS)"
	@python3 scripts/console_password.py "$(VM)" >/dev/null
	@python3 scripts/ensure_console.py "$(VM)"
	@python3 scripts/truenas_ops.py verify --vm "$(VM)"

backup-storage-init:
	@command -v $(TOFU) >/dev/null || { echo "OpenTofu is required: https://opentofu.org/docs/intro/install/"; exit 1; }
	@$(TOFU) -chdir=$(BACKUP_TOFU_DIR) init

backup-storage-plan: backup-storage-init
	@TF_VAR_truenas_api_key="$$(python3 scripts/truenas_ops.py secret)" $(TOFU) -chdir=$(BACKUP_TOFU_DIR) plan

backup-storage-apply: backup-storage-init
	@TF_VAR_truenas_api_key="$$(python3 scripts/truenas_ops.py secret)" $(TOFU) -chdir=$(BACKUP_TOFU_DIR) apply

backup-storage-check:
	@python3 scripts/truenas_ops.py backup-storage-check

core-storage-preflight: require-vm
	@profile="$$(python3 scripts/core_profiles.py select --vm "$(VM)" $(if $(PROFILE),--profile "$(PROFILE)",))" || exit $$?; \
		requires="$$(python3 scripts/core_profiles.py requires-backup --profile "$$profile")" || exit $$?; \
		if [ "$$requires" = "true" ]; then \
			python3 scripts/truenas_ops.py backup-storage-check; \
		fi

inventory: require-vm
	@python3 scripts/vm_factory.py inventory --vm "$(VM)"
	@ssh-keyscan -T 5 -H "$$(python3 -c 'import json; print(json.load(open("deployments/$(VM)/deployment.auto.tfvars.json"))["ip_address"])')" > "build/$(VM)/known_hosts" 2>/dev/null || true

configure-base: require-vm inventory
	@ANSIBLE_CONFIG=ansible/ansible.cfg $(ANSIBLE_PLAYBOOK) --ssh-common-args "-o UserKnownHostsFile=build/$(VM)/known_hosts -o StrictHostKeyChecking=yes" -i "build/$(VM)/inventory.yml" ansible/site.yml \
		-e "@deployments/$(VM)/ansible-vars.yml" \
		-e "vm_login_password_hash=$$(python3 scripts/login_password.py $(VM) --hash)"
	@python3 scripts/core_profiles.py mark-base --vm "$(VM)"

configure: configure-base

provision-base: apply
	@python3 scripts/truenas_ops.py wait --vm "$(VM)"
	@$(MAKE) --no-print-directory inventory VM="$(VM)"
	@if python3 -c 'import json; raise SystemExit(0 if json.load(open("deployments/$(VM)/deployment.auto.tfvars.json")).get("provisioning_phase", "install") == "install" else 1)'; then \
		python3 scripts/set_phase.py "$(VM)" bootstrap; \
		$(MAKE) --no-print-directory apply VM="$(VM)"; \
		python3 scripts/restart_vm.py "$(VM)"; \
		python3 scripts/truenas_ops.py wait --vm "$(VM)"; \
	fi
	@$(MAKE) --no-print-directory configure-base VM="$(VM)"

deploy: provision-base

setup-core: require-vm
	@python3 scripts/core_profiles.py require-base --vm "$(VM)"
	@if [ "$(STORAGE_PREFLIGHT_DONE)" != "1" ]; then \
		$(MAKE) --no-print-directory core-storage-preflight VM="$(VM)" $(if $(PROFILE),PROFILE="$(PROFILE)",); \
	fi
	@$(MAKE) --no-print-directory inventory VM="$(VM)"
	@profile="$$(python3 scripts/core_profiles.py resolve --vm "$(VM)" $(if $(PROFILE),--profile "$(PROFILE)",))"; \
		ANSIBLE_CONFIG=ansible/ansible.cfg $(ANSIBLE_PLAYBOOK) \
		--ssh-common-args "-o UserKnownHostsFile=build/$(VM)/known_hosts -o StrictHostKeyChecking=yes" \
		-i "build/$(VM)/inventory.yml" "ansible/core_profiles/$$profile/site.yml" \
		-e "@deployments/$(VM)/ansible-vars.yml"

backup-now: require-vm
	@python3 scripts/core_profiles.py require-base --vm "$(VM)"
	@$(MAKE) --no-print-directory core-storage-preflight VM="$(VM)"
	@$(MAKE) --no-print-directory inventory VM="$(VM)"
	@ANSIBLE_CONFIG=ansible/ansible.cfg $(ANSIBLE_PLAYBOOK) \
		--ssh-common-args "-o UserKnownHostsFile=build/$(VM)/known_hosts -o StrictHostKeyChecking=yes" \
		-i "build/$(VM)/inventory.yml" ansible/backup-now.yml

preview: require-vm
	@$(MAKE) --no-print-directory core-storage-preflight VM="$(VM)"
	@profile="$$(python3 scripts/core_profiles.py select --vm "$(VM)")" || exit $$?; \
		$(MAKE) --no-print-directory plan VM="$(VM)" && \
		$(MAKE) --no-print-directory inventory VM="$(VM)" && \
		ANSIBLE_CONFIG=ansible/ansible.cfg $(ANSIBLE_PLAYBOOK) --check --diff \
		--ssh-common-args "-o UserKnownHostsFile=build/$(VM)/known_hosts -o StrictHostKeyChecking=yes" \
		-i "build/$(VM)/inventory.yml" ansible/site.yml \
		-e "@deployments/$(VM)/ansible-vars.yml" \
		-e "vm_login_password_hash=$$(python3 scripts/login_password.py $(VM) --hash)" && \
		ANSIBLE_CONFIG=ansible/ansible.cfg $(ANSIBLE_PLAYBOOK) --check --diff \
		--ssh-common-args "-o UserKnownHostsFile=build/$(VM)/known_hosts -o StrictHostKeyChecking=yes" \
		-i "build/$(VM)/inventory.yml" "ansible/core_profiles/$$profile/site.yml" \
		-e "@deployments/$(VM)/ansible-vars.yml"

reconcile: require-vm
	@$(MAKE) --no-print-directory core-storage-preflight VM="$(VM)"
	@$(MAKE) --no-print-directory configure-base VM="$(VM)"
	@$(MAKE) --no-print-directory setup-core VM="$(VM)" STORAGE_PREFLIGHT_DONE=1

check:
	@python3 -m unittest discover -s tests -v
	@python3 -m py_compile scripts/vm_factory.py
	@python3 -m py_compile scripts/core_profiles.py
	@python3 -m py_compile ansible/filter_plugins/truenas_names.py
	@$(ANSIBLE_PLAYBOOK) --syntax-check -i ansible/inventory.test.yml ansible/site.yml
	@$(ANSIBLE_PLAYBOOK) --syntax-check -i ansible/inventory.test.yml ansible/backup-now.yml
	@set -e; for playbook in ansible/core_profiles/*/site.yml; do \
		test -e "$$playbook" || continue; \
		$(ANSIBLE_PLAYBOOK) --syntax-check -i ansible/inventory.test.yml "$$playbook"; \
	done
	@if command -v $(TOFU) >/dev/null; then \
		$(TOFU) -chdir=opentofu fmt -check -recursive && \
		$(TOFU) -chdir=opentofu validate && \
		$(TOFU) -chdir=$(BACKUP_TOFU_DIR) init -backend=false >/dev/null && \
		$(TOFU) -chdir=$(BACKUP_TOFU_DIR) validate; \
	else echo "SKIP: tofu is not installed"; fi

destroy: require-vm preflight init
	@echo "The VM disk has prevent_destroy protection. This target removes only what OpenTofu can safely destroy."
	@TF_VAR_truenas_api_key="$$(python3 scripts/truenas_ops.py secret)" TF_VAR_display_password="$$(python3 scripts/console_password.py $(VM))" TF_VAR_login_password_hash="$$(python3 scripts/login_password.py $(VM) --hash)" $(TOFU) -chdir=opentofu destroy -target=truenas_vm.this -state="$(STATE)" -var-file="$(TFVARS)"

destroy-disk: require-vm
	@command -v $(TOFU) >/dev/null || { echo "OpenTofu is required to remove the retired disk from state"; exit 1; }
	@python3 scripts/truenas_ops.py retire-disk --vm "$(VM)"
	@$(TOFU) -chdir=opentofu state rm -state="$(STATE)" truenas_dataset.vm_disk

remove-deployment: require-vm
	@python3 scripts/vm_factory.py remove --vm "$(VM)"

vm-password: require-vm
	@python3 scripts/login_password.py "$(VM)"

preflight: require-vm
	@python3 scripts/truenas_ops.py preflight --vm "$(VM)"

require-vm:
	@test -n "$(VM)" || { echo "Set VM=<deployment-name>"; exit 2; }
	@test -f "$(DEPLOYMENT_DIR)/deployment.auto.tfvars.json" || { echo "Unknown deployment: $(VM)"; exit 2; }

require-profile:
	@test -n "$(PROFILE)" || { echo "Set PROFILE=<core-profile-name>"; exit 2; }
