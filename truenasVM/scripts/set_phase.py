#!/usr/bin/env python3
"""Set a deployment's persistent provisioning phase."""

import json
from pathlib import Path
import sys

if len(sys.argv) != 3 or sys.argv[2] not in {"install", "bootstrap"}:
    raise SystemExit("usage: set_phase.py <deployment-name> <install|bootstrap>")
path = Path(__file__).resolve().parents[1] / "deployments" / sys.argv[1] / "deployment.auto.tfvars.json"
data = json.loads(path.read_text())
data["provisioning_phase"] = sys.argv[2]
path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
print(f"{sys.argv[1]} phase={sys.argv[2]}")

