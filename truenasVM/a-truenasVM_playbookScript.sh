#!/bin/bash

# Prompt for sudo password once
read -s -p "Enter sudo password: " sudo_pass
echo

echo "Starting the script..."

# Provision VM from template

# ansible-playbook -i inventory.yml config_network.yml --extra-vars "ansible_become_pass=$sudo_pass"
# sleep 5

# ansible-playbook -i inventory.yml inst_essential_packages.yml --extra-vars "ansible_become_pass=$sudo_pass"
# sleep 5

# ansible-playbook -i inventory.yml dotfiles_clone_gitpull.yml --extra-vars "ansible_become_pass=$sudo_pass"
# sleep 5

ansible-playbook -i inventory.yml dotfiles_clone_gitpull.yml --extra-vars "ansible_become_pass=$sudo_pass"
sleep 5


