#!/usr/bin/env python3
"""Restart a deployment VM through the TrueNAS API."""

import json
from pathlib import Path
import sys
import time
from truenas_ops import api

if len(sys.argv) != 2:
    raise SystemExit("usage: restart_vm.py <deployment-name>")
root = Path(__file__).resolve().parents[1]
deployment = json.loads((root / "deployments" / sys.argv[1] / "deployment.auto.tfvars.json").read_text())
vm = next(item for item in api("vm") if item.get("name") == deployment["vm_name"])
if vm["status"]["state"] == "RUNNING":
    api(f"vm/id/{vm['id']}/stop", {"force": False, "force_after_timeout": True})
    for _ in range(30):
        time.sleep(2)
        vm = next(item for item in api("vm") if item.get("id") == vm["id"])
        if vm["status"]["state"] == "STOPPED":
            break
api(f"vm/id/{vm['id']}/start", {})
print(f"Restarted {deployment['vm_name']}")
