#!/bin/bash

# Prompt for sudo password once
read -s -p "Enter sudo password: " sudo_pass
echo

echo "Starting the script..."

# Provision VM from template

ansible-playbook -i devServer_inventory.yml devServer_config_network.yml --extra-vars "ansible_become_pass=$sudo_pass"
sleep 5

ansible-playbook -i devServer_inventory.yml devServer_baseInstall.yml --extra-vars "ansible_become_pass=$sudo_pass"
sleep 5

ansible-playbook -i devServer_inventory.yml devServer_hostname.yml --extra-vars "ansible_become_pass=$sudo_pass"
sleep 5

ansible-playbook -i devServer_inventory.yml devServer_config_backups.yml --extra-vars "ansible_become_pass=$sudo_pass"
sleep 5
