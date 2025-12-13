#!/usr/bin/env python3
import os
import sys
import json
import ipaddress
from pathlib import Path
from dotenv import load_dotenv
from proxmoxer import ProxmoxAPI

# Defaults matching the original script
DEFAULT_IP_START = ipaddress.ip_address("10.0.70.10")
DEFAULT_IP_STEP = 10

def load_env():
    # Load .env from the parent directory
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(dotenv_path=env_path)

def connect_proxmox():
    host = "10.0.5.100"
    token_id = os.getenv("PROXMOX_TOKEN_ID")
    token_secret = os.getenv("PROXMOX_TOKEN_SECRET")
    
    if not token_id or not token_secret:
        print(json.dumps({"error": "Missing PROXMOX_TOKEN_ID or PROXMOX_TOKEN_SECRET"}), file=sys.stderr)
        sys.exit(1)

    if "!" not in token_id:
        print(json.dumps({"error": "PROXMOX_TOKEN_ID must be user@realm!tokenname"}), file=sys.stderr)
        sys.exit(1)
        
    user_part, token_name = token_id.split("!", 1)
    
    # Insecure by default as per original script args or common setup
    return ProxmoxAPI(host, user=user_part, token_name=token_name, token_value=token_secret, verify_ssl=False)

def get_next_ctid(proxmox):
    resources = proxmox.cluster.resources.get(type="vm")
    used_ids = {int(res["vmid"]) for res in resources}
    ctid = 710
    while ctid in used_ids:
        ctid += 10
    return ctid

def parse_net_ip(net_conf):
    # net_conf example: "name=eth0,bridge=vmbr0,ip=10.0.70.10/24,gw=10.0.70.1"
    for part in net_conf.split(","):
        if part.startswith("ip="):
            ip_part = part.split("=", 1)[1]
            ip_only = ip_part.split("/")[0]
            try:
                return ipaddress.ip_address(ip_only)
            except ValueError:
                return None
    return None

def get_next_ip(proxmox, node="pve"):
    used_ips = set()
    # Scan all LXC containers for used IPs in the 10.0.70.x range
    # type="vm" returns both qemu and lxc
    for res in proxmox.cluster.resources.get(type="vm"):
        if res.get("type") != "lxc":
            continue
        vmid = res.get("vmid")
        try:
            # We need to check the config of the container
            # The resource list might have the node name
            res_node = res.get("node", node)
            cfg = proxmox.nodes(res_node).lxc(vmid).config.get()
            net0 = cfg.get("net0")
            if net0:
                ip = parse_net_ip(net0)
                if ip and str(ip).startswith("10.0.70."):
                    used_ips.add(ip)
        except Exception:
            continue
            
    candidate = DEFAULT_IP_START
    while True:
        if candidate not in used_ips:
            return str(candidate)
        candidate += DEFAULT_IP_STEP

def main():
    try:
        load_env()
        proxmox = connect_proxmox()
        ctid = get_next_ctid(proxmox)
        ip = get_next_ip(proxmox)
        
        print(json.dumps({
            "ctid": ctid,
            "ip": ip,
            "token_id": os.getenv("PROXMOX_TOKEN_ID"),
            "token_secret": os.getenv("PROXMOX_TOKEN_SECRET")
        }))
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
