SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

VM ?=
TOFU ?= .tools/tofu
ANSIBLE_PLAYBOOK ?= ansible-playbook
DEPLOYMENT_DIR = deployments/$(VM)
TFVARS = ../$(DEPLOYMENT_DIR)/deployment.auto.tfvars.json
STATE = ../$(DEPLOYMENT_DIR)/terraform.tfstate

.PHONY: help new-vm list suggest init plan apply inventory configure deploy check destroy destroy-disk remove-deployment vm-password

help:
	@echo "make new-vm              Interactively register a VM"
	@echo "make suggest NAME=web    Show available name/IP suggestions"
	@echo "make list                List registered deployments"
	@echo "make deploy VM=<name>    Provision and configure a VM"
	@echo "make plan VM=<name>      Preview infrastructure changes"
	@echo "make configure VM=<name> Run Ansible only"
	@echo "make check               Run local validation"
	@echo "make destroy VM=<name>   Destroy VM definition (disk is protected)"
	@echo "make destroy-disk VM=<name> Delete a retired VM's protected disk"
	@echo "make remove-deployment VM=<name> Remove files after VM and disk retirement"
	@echo "make vm-password VM=<name> Show the VM console and SSH login password"

new-vm:
	@python3 scripts/vm_factory.py create

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

inventory: require-vm
	@python3 scripts/vm_factory.py inventory --vm "$(VM)"
	@ssh-keyscan -T 5 -H "$$(python3 -c 'import json; print(json.load(open("deployments/$(VM)/deployment.auto.tfvars.json"))["ip_address"])')" > "build/$(VM)/known_hosts" 2>/dev/null || true

configure: require-vm inventory
	@ANSIBLE_CONFIG=ansible/ansible.cfg $(ANSIBLE_PLAYBOOK) --ssh-common-args "-o UserKnownHostsFile=build/$(VM)/known_hosts -o StrictHostKeyChecking=yes" -i "build/$(VM)/inventory.yml" ansible/site.yml \
		-e "@deployments/$(VM)/ansible-vars.yml" \
		-e "vm_login_password_hash=$$(python3 scripts/login_password.py $(VM) --hash)"

deploy: apply
	@python3 scripts/truenas_ops.py wait --vm "$(VM)"
	@$(MAKE) --no-print-directory inventory VM="$(VM)"
	@if python3 -c 'import json; raise SystemExit(0 if json.load(open("deployments/$(VM)/deployment.auto.tfvars.json")).get("provisioning_phase", "install") == "install" else 1)'; then \
		python3 scripts/set_phase.py "$(VM)" bootstrap; \
		$(MAKE) --no-print-directory apply VM="$(VM)"; \
		python3 scripts/restart_vm.py "$(VM)"; \
		python3 scripts/truenas_ops.py wait --vm "$(VM)"; \
	fi
	@$(MAKE) --no-print-directory configure VM="$(VM)"

check:
	@python3 -m unittest discover -s tests -v
	@python3 -m py_compile scripts/vm_factory.py
	@$(ANSIBLE_PLAYBOOK) --syntax-check -i ansible/inventory.test.yml ansible/site.yml
	@if command -v $(TOFU) >/dev/null; then $(TOFU) -chdir=opentofu fmt -check -recursive && $(TOFU) -chdir=opentofu validate; else echo "SKIP: tofu is not installed"; fi

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

