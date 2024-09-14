#!/bin/bash

# Prompt for sudo password once
read -s -p "Enter sudo password: " sudo_pass
echo

echo "Starting the script..."

# Provision VM from template

ansible-playbook -i perServer_inventory.yml perServer_config_network.yml --extra-vars "ansible_become_pass=$sudo_pass"
sleep 5

ansible-playbook -i perServer_inventory.yml perServer_baseInstall.yml --extra-vars "ansible_become_pass=$sudo_pass"
sleep 5

ansible-playbook -i perServer_inventory.yml perServer_hostname.yml --extra-vars "ansible_become_pass=$sudo_pass"
sleep 5

ansible-playbook -i perServer_inventory.yml perServer_sambaConfig.yml --extra-vars "ansible_become_pass=$sudo_pass"
sleep 5

ansible-playbook -i perServer_inventory.yml perServer_deploy_containers.yml --extra-vars "ansible_become_pass=$sudo_pass"
sleep 5

