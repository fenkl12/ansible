#!/bin/bash

# Script to deploy a single Docker container using Ansible
# Usage: ./deploy_single_container.sh <container_name>

# Check if container name is provided
if [ $# -eq 0 ]; then
    echo "Usage: $0 <container_name>"
    echo ""
    echo "Available containers:"
    ls -1 containers/ 2>/dev/null || echo "No containers directory found"
    exit 1
fi

CONTAINER_NAME="$1"

# Check if container directory exists
if [ ! -d "containers/$CONTAINER_NAME" ]; then
    echo "Error: Container directory 'containers/$CONTAINER_NAME' does not exist"
    echo ""
    echo "Available containers are:"
    ls -1 containers/ 2>/dev/null || echo "No containers directory found"
    exit 1
fi

# Prompt for sudo password
read -s -p "Enter sudo password: " sudo_pass
echo

echo "Deploying container: $CONTAINER_NAME"
echo "=========================="

# Run the Ansible playbook with the same syntax as the main script
ansible-playbook -i docker_inventory.yml docker_deploy_single_container.yml --extra-vars "ansible_become_pass=$sudo_pass container_name=$CONTAINER_NAME"

# Check the exit status
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ Container '$CONTAINER_NAME' deployed successfully!"
else
    echo ""
    echo "❌ Failed to deploy container '$CONTAINER_NAME'"
    exit 1
fi