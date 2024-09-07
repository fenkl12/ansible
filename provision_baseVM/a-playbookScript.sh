#!/bin/bash

# Variables
proxmox_vm_id=130
proxmox_vm_name=dockerMain
proxmox_template_vm_id=502
template_vm_ip=10.0.6.20
static_ip_to_remove=$template_vm_ip

#remove 10.0.5.55 from ssh as it creates conflicts when cloning from different templates
ssh-keygen -f '/home/fenkil/.ssh/known_hosts' -R '10.0.5.55'

# Prompt for sudo password once
read -s -p "Enter sudo password: " sudo_pass
echo

echo "Starting the script..."

# Provision VM from template
echo "Running playbook: provision_from_template.yml with VM ID: $proxmox_vm_id, VM Name: $proxmox_vm_name, Template VM ID: $proxmox_template_vm_id"
ansible-playbook -i inventory.yml provision_from_template.yml --extra-vars "template_vm_ip=$template_vm_ip proxmox_vm_id=$proxmox_vm_id proxmox_vm_name=$proxmox_vm_name proxmox_template_vm_id=$proxmox_template_vm_id"
sleep 10

# Configure network
echo "Running playbook: config_network.yml to remove static IP: $static_ip_to_remove"
ansible-playbook -i inventory.yml config_network.yml --extra-vars "template_vm_ip=$template_vm_ip static_ip_to_remove=$static_ip_to_remove ansible_become_pass=$sudo_pass"
sleep 5

# Install essential packages
echo "Running playbook: inst_essential_packages.yml"
ansible-playbook -i inventory.yml inst_essential_packages.yml --extra-vars "template_vm_ip=$template_vm_ip ansible_become_pass=$sudo_pass"
sleep 3

# Configure TrueNAS
echo "Running playbook: config_truenas.yml"
ansible-playbook -i inventory.yml config_truenas.yml --extra-vars "template_vm_ip=$template_vm_ip ansible_become_pass=$sudo_pass"
sleep 3

# Round 1 - Clone and pull dotfiles
echo "Running playbook: dotfiles_clone_gitpull.yml"
ansible-playbook -i inventory.yml dotfiles_clone_gitpull.yml --extra-vars "template_vm_ip=$template_vm_ip ansible_become_pass=$sudo_pass"

# Round 2 - Clone and pull dotfiles
echo "Running playbook: dotfiles_clone_gitpull.yml"
ansible-playbook -i inventory.yml dotfiles_clone_gitpull.yml --extra-vars "template_vm_ip=$template_vm_ip ansible_become_pass=$sudo_pass"