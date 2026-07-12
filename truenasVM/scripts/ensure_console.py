#!/usr/bin/env python3
"""Idempotently ensure a TrueNAS SPICE display for one deployment."""

import json
from pathlib import Path
import sys

from console_password import password_for_vm
from truenas_ops import api

if len(sys.argv) != 2:
    raise SystemExit("usage: ensure_console.py <deployment-name>")

root = Path(__file__).resolve().parents[1]
name = sys.argv[1]
deployment = json.loads((root / "deployments" / name / "deployment.auto.tfvars.json").read_text())
vm = next((item for item in api("vm") if item.get("name") == deployment["vm_name"]), None)
if not vm:
    raise SystemExit("VM was not found")

display = next((item for item in vm.get("devices", []) if item.get("dtype") == "DISPLAY"), None)
if not display:
    display = api(
        "vm/device",
        {
            "vm": vm["id"],
            "dtype": "DISPLAY",
            "attributes": {
                "type": "SPICE",
                "bind": "0.0.0.0",
                "password": password_for_vm(name),
                "web": True,
                "wait": False,
                "resolution": "1024x768",
            },
            "order": 1004,
        },
    )
print(f"SPICE console ready: device={display['id']}")
