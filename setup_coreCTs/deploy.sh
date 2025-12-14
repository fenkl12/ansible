#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== LXD Container Application Deployer ===${NC}"

# 1. Scan for available containers
echo -e "${BLUE}Scanning for available containers (10.0.70.20 - 10.0.70.50)...${NC}"
available_ips=()

for i in {20..50..10}; do
    target_ip="10.0.70.$i"
    # Ping check with 1 second timeout
    if ping -c 1 -W 1 "$target_ip" &> /dev/null; then

        available_ips+=("$target_ip")
        echo -e "${GREEN}Found: $target_ip${NC}"
    fi
done

if [ ${#available_ips[@]} -eq 0 ]; then
    echo -e "${RED}No containers found in the specified range.${NC}"
    exit 1
fi

echo -e "\n${BLUE}Select a Container:${NC}"
j=1
for ip in "${available_ips[@]}"; do
    echo "[$j] $ip"
    ((j++))
done

read -p "Select a container number: " IP_SELECTION

if ! [[ "$IP_SELECTION" =~ ^[0-9]+$ ]] || [ "$IP_SELECTION" -lt 1 ] || [ "$IP_SELECTION" -gt "${#available_ips[@]}" ]; then
    echo -e "${RED}Invalid selection.${NC}"
    exit 1
fi

CONTAINER_IP="${available_ips[$((IP_SELECTION-1))]}"
echo -e "${GREEN}Selected Container: $CONTAINER_IP${NC}"

# 2. Ask for SSH User (Default to fenkil)
read -p "Enter SSH User [fenkil]: " SSH_USER
SSH_USER=${SSH_USER:-fenkil}

echo -e "${GREEN}Targeting: ${SSH_USER}@${CONTAINER_IP}${NC}"

# 3. List available applications (subdirectories)
echo -e "\n${BLUE}Available Applications:${NC}"
apps=($(find . -maxdepth 1 -type d -not -path '*/.*' -not -path '.' | sed 's|^\./||' | sort))

if [ ${#apps[@]} -eq 0 ]; then
    echo -e "${RED}No application folders found in current directory.${NC}"
    exit 1
fi

i=1
for app in "${apps[@]}"; do
    echo "[$i] $app"
    ((i++))
done

# 4. Select Application
read -p "Select an application number: " APP_SELECTION

# Validate selection
if ! [[ "$APP_SELECTION" =~ ^[0-9]+$ ]] || [ "$APP_SELECTION" -lt 1 ] || [ "$APP_SELECTION" -gt "${#apps[@]}" ]; then
    echo -e "${RED}Invalid selection.${NC}"
    exit 1
fi

SELECTED_APP="${apps[$((APP_SELECTION-1))]}"
PLAYBOOK_PATH="./$SELECTED_APP/playbook.yml"

echo -e "${GREEN}Selected Application: $SELECTED_APP${NC}"

# 5. Check for playbook
if [ ! -f "$PLAYBOOK_PATH" ]; then
    echo -e "${RED}Error: No playbook.yml found in $SELECTED_APP${NC}"
    exit 1
fi

# 6. Confirm and Run
echo -e "\n${BLUE}Ready to deploy $SELECTED_APP to $CONTAINER_IP${NC}"

# Ask for sudo password requirement
read -p "Do you need to provide a sudo password for the remote user? (y/N): " ASK_SUDO
ANSIBLE_ARGS=""
if [[ "$ASK_SUDO" =~ ^[Yy]$ ]]; then
    ANSIBLE_ARGS="-K"
fi

read -p "Press Enter to continue or Ctrl+C to cancel..."

# Create a temporary inventory or use comma separated list
# Using comma separated list for single host
echo -e "${BLUE}Running Ansible Playbook...${NC}"

# We disable host key checking for convenience with dynamic containers, 
# but warn the user in a real env they might want to manage known_hosts.
export ANSIBLE_HOST_KEY_CHECKING=False

ansible-playbook -i "$CONTAINER_IP," -u "$SSH_USER" $ANSIBLE_ARGS "$PLAYBOOK_PATH"

if [ $? -eq 0 ]; then
    echo -e "\n${GREEN}Deployment Completed Successfully!${NC}"
else
    echo -e "\n${RED}Deployment Failed.${NC}"
fi
