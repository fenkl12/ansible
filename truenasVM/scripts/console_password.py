#!/usr/bin/env python3
"""Return a stable, local-only SPICE password for a deployment."""

from pathlib import Path
import secrets
import sys

if len(sys.argv) != 2 or not sys.argv[1]:
    raise SystemExit("usage: console_password.py <deployment-name>")

root = Path(__file__).resolve().parents[1]
path = root / ".secrets" / f"{sys.argv[1]}.console_password"
if not path.exists():
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(secrets.token_urlsafe(18) + "\n", encoding="utf-8")
    path.chmod(0o600)
print(path.read_text(encoding="utf-8").strip())
