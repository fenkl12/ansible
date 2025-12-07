#!/bin/bash

# Default values
DEFAULT_VM_ID=801

# Read inputs
read -p "Enter VM ID [$DEFAULT_VM_ID]: " VM_ID
VM_ID=${VM_ID:-$DEFAULT_VM_ID}

# Dynamic default name based on ID
DEFAULT_VM_NAME="vm-${VM_ID}"

read -p "Enter VM Name [$DEFAULT_VM_NAME]: " VM_NAME
VM_NAME=${VM_NAME:-$DEFAULT_VM_NAME}

echo "------------------------------------------------"
echo "Select Source Template:"
echo "  1) Template ID 501 (IP: 10.0.6.10)"
echo "  2) Template ID 502 (IP: 10.0.6.20)"
echo "  3) Template ID 503 (IP: 10.0.6.30)"
echo "------------------------------------------------"
read -p "Enter choice [1-3] (Default: 1): " TEMPLATE_CHOICE
TEMPLATE_CHOICE=${TEMPLATE_CHOICE:-1}

case $TEMPLATE_CHOICE in
    1)
        TEMPLATE_ID=501
        TEMPLATE_IP="10.0.6.10"
        ;;
    2)
        TEMPLATE_ID=502
        TEMPLATE_IP="10.0.6.20"
        ;;
    3)
        TEMPLATE_ID=503
        TEMPLATE_IP="10.0.6.30"
        ;;
    *)
        echo "Invalid choice. Exiting."
        exit 1
        ;;
esac

echo "Using Template ID: $TEMPLATE_ID ($TEMPLATE_IP)"

# Function to find next available IP
find_next_available_ip() {
    local base_ip="10.0.10"
    # Loop from 100 to 250 in increments of 10 (start at 10.0.10.100)
    for i in $(seq 100 10 250); do
        local target_ip="$base_ip.$i"
        # Ping with 1 packet and 1 second timeout. 
        # If ping fails (!), the IP is likely free.
        if ! ping -c 1 -W 1 "$target_ip" &> /dev/null; then
            echo "$target_ip"
            return 0
        fi
    done
    echo ""
}

echo "Scanning for available IP in 10.0.10.x range (increment of 10)..."
SUGGESTED_IP=$(find_next_available_ip)

if [ -n "$SUGGESTED_IP" ]; then
    DEFAULT_IP_CIDR="${SUGGESTED_IP}/16"
    PROMPT_TEXT="Enter New Static IP for VM [$DEFAULT_IP_CIDR]: "
else
    DEFAULT_IP_CIDR=""
    PROMPT_TEXT="Enter New Static IP for VM (e.g. 10.0.10.10/16): "
fi

read -p "$PROMPT_TEXT" INPUT_STATIC_IP
NEW_STATIC_IP=${INPUT_STATIC_IP:-$DEFAULT_IP_CIDR}

if [ -z "$NEW_STATIC_IP" ]; then
    echo "Error: Static IP is required."
    exit 1
fi

# Remove old SSH key for the template IP to avoid conflicts
ssh-keygen -f "$HOME/.ssh/known_hosts" -R "$TEMPLATE_IP" > /dev/null 2>&1
# Also remove the new IP if it was previously known
NEW_IP_ONLY=$(echo $NEW_STATIC_IP | cut -d'/' -f1)
ssh-keygen -f "$HOME/.ssh/known_hosts" -R "$NEW_IP_ONLY" > /dev/null 2>&1

echo "Provisioning VM $VM_NAME (ID: $VM_ID) from Template $TEMPLATE_ID..."
echo "Target IP: $NEW_STATIC_IP"

# Optionally collect sudo/become password (keeps runs non-interactive after this script)
read -p "Do you want to provide the sudo/become password now? [y/N]: " USE_SUDO_PASS
USE_SUDO_PASS=${USE_SUDO_PASS:-N}

EXTRA_VARS="proxmox_vm_id=$VM_ID proxmox_vm_name=$VM_NAME proxmox_template_vm_id=$TEMPLATE_ID template_vm_ip=$TEMPLATE_IP static_ip=$NEW_STATIC_IP"

if [[ "$USE_SUDO_PASS" =~ ^[Yy]$ ]]; then
    # Read password silently and pass it as extra-var. We'll unset the variable afterwards.
    read -s -p "Enter sudo/become password: " SUDO_PASS
    echo
    # append become password to extra-vars
    EXTRA_VARS="$EXTRA_VARS ansible_become_pass=$SUDO_PASS"

    # Run playbook without -K (we already provided the password)
    ansible-playbook -i inventory.yml site.yml --extra-vars "$EXTRA_VARS"

    # Clear sensitive variable
    unset SUDO_PASS
else
    # No password provided up-front: ask Ansible interactively for the become password when needed (-K)
    ansible-playbook -i inventory.yml site.yml -K --extra-vars "$EXTRA_VARS"
fi

echo "Done!"
