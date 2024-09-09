#!/bin/bash

# Prompt for sudo password once
read -s -p "Enter sudo password: " sudo_pass
echo

echo "Starting the script..."

# Provision VM from template

ansible-playbook -i monitorSer_inventory.yml monitorSer_config_network.yml --extra-vars "ansible_become_pass=$sudo_pass"
sleep 5

ansible-playbook -i monitorSer_inventory.yml monitorSer_config_healthChecksIO.yml --extra-vars "ansible_become_pass=$sudo_pass"
sleep 5

ansible-playbook -i monitorSer_inventory.yml monitorSer_uptimeKumaInstall.yml --extra-vars "ansible_become_pass=$sudo_pass"
sleep 5

ansible-playbook -i monitorSer_inventory.yml monitorSer_hostname.yml --extra-vars "ansible_become_pass=$sudo_pass"
sleep 5

ansible-playbook -i monitorSer_inventory.yml monitorSer_config_backups.yml --extra-vars "ansible_become_pass=$sudo_pass"
sleep 5
