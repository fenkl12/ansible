#!/usr/bin/env python3
"""Safe TrueNAS deployment preflight, verification, and readiness checks."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import ssl
import sys
import time
from typing import Any
from urllib.parse import quote
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SECRET_FILE = ROOT / ".secrets/truenas.env"
API_URL = "https://10.0.203.171/api/v2.0"


class OpsError(RuntimeError):
    pass


def token() -> str:
    if os.environ.get("TRUENAS_API_KEY"):
        return os.environ["TRUENAS_API_KEY"]
    if not SECRET_FILE.is_file():
        raise OpsError("Missing .secrets/truenas.env")
    for raw in SECRET_FILE.read_text(encoding="utf-8").splitlines():
        if raw.startswith("TRUENAS_API_KEY="):
            return raw.split("=", 1)[1].strip().strip("'\"")
    raise OpsError("TRUENAS_API_KEY is unavailable")


def api(endpoint: str, payload: Any | None = None, method: str | None = None) -> Any:
    method = method or ("GET" if payload is None else "POST")
    request = Request(
        f"{API_URL}/{endpoint.lstrip('/')}",
        data=None if payload is None else json.dumps(payload).encode(),
        method=method,
        headers={"Authorization": f"Bearer {token()}", "Content-Type": "application/json"},
    )
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        with urlopen(request, timeout=20, context=context) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise OpsError(f"TrueNAS API request failed: {exc}") from exc


def deployment(name: str) -> dict[str, Any]:
    path = ROOT / "deployments" / name / "deployment.auto.tfvars.json"
    if not path.is_file():
        raise OpsError(f"Unknown deployment: {name}")
    return json.loads(path.read_text(encoding="utf-8"))


def file_stat(path: str) -> dict[str, Any]:
    return api("filesystem/stat", path)


def cmd_secret(_: argparse.Namespace) -> None:
    print(token())


def cmd_preflight(args: argparse.Namespace) -> None:
    item = deployment(args.vm)
    version = str(api("system/info").get("version", ""))
    if "24.04" not in version:
        raise OpsError(f"Expected TrueNAS 24.04, found {version}")
    iso = file_stat(item.get("ubuntu_iso_path", "/mnt/WD1TB/ISOs/ubuntu-24.04-live-server-amd64.iso"))
    if iso.get("type") != "FILE" or int(iso.get("size", 0)) == 0:
        raise OpsError(f"Ubuntu ISO is missing or empty: {item.get('ubuntu_iso_path', '/mnt/WD1TB/ISOs/ubuntu-24.04-live-server-amd64.iso')}")
    print(f"Preflight OK: {item['vm_name']} on {version}; installer ISO={iso['size']} bytes")


def find_vm(name: str) -> dict[str, Any] | None:
    return next((vm for vm in api("vm") if vm.get("name") == name), None)


def zvol_name(item: dict[str, Any]) -> str:
    return f"{item.get('storage_pool', 'WD1TB')}/{item['vm_name'].lower().replace('_', '-')}-disk0"


def cmd_retire_disk(args: argparse.Namespace) -> None:
    item = deployment(args.vm)
    if find_vm(item["vm_name"]):
        raise OpsError(f"VM still exists: {item['vm_name']}; run make destroy VM={args.vm} first")

    name = zvol_name(item)
    dataset = next((entry for entry in api("pool/dataset") if entry.get("id") == name), None)
    if not dataset:
        raise OpsError(f"Zvol was not found: {name}; OpenTofu state was left unchanged")
    if dataset.get("type") != "VOLUME":
        raise OpsError(f"Refusing to delete non-zvol dataset: {name}")

    deleted = api(f"pool/dataset/id/{quote(name, safe='')}", method="DELETE")
    if deleted is not True:
        raise OpsError(f"TrueNAS did not confirm deletion of zvol: {name}")
    print(f"Zvol deleted: {name}")


def cmd_verify(args: argparse.Namespace) -> None:
    item = deployment(args.vm)
    vm = find_vm(item["vm_name"])
    if not vm:
        raise OpsError("VM was not found after apply")
    types = {device.get("dtype") for device in vm.get("devices", [])}
    missing = {"DISK", "NIC", "CDROM", "DISPLAY"} - types
    if missing or not vm.get("display_available"):
        raise OpsError(f"VM device verification failed: missing={sorted(missing)}, display={vm.get('display_available')}")
    seed_path = f"/mnt/{item.get('storage_pool', 'WD1TB')}/ISOs/cloud-init-{item['vm_name']}.iso"
    seed = file_stat(seed_path)
    if seed.get("type") != "FILE" or int(seed.get("size", 0)) == 0:
        raise OpsError(f"Cloud-init ISO is missing or empty: {seed_path}")
    print(f"VM verification OK: id={vm['id']} state={vm['status']['state']} console=available")


def cmd_wait(args: argparse.Namespace) -> None:
    item = deployment(args.vm)
    address = item["ip_address"]
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((address, 22), timeout=3):
                print(f"SSH is ready at {address}")
                return
        except OSError:
            time.sleep(5)
    vm = find_vm(item["vm_name"])
    detail = f"status={vm.get('status')} display={vm.get('display_available')}" if vm else "VM not found"
    raise OpsError(f"SSH timeout at {address}; {detail}. Open the VM display in TrueNAS.")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(required=True)
    sub.add_parser("secret").set_defaults(func=cmd_secret)
    for name, func in (("preflight", cmd_preflight), ("verify", cmd_verify), ("wait", cmd_wait), ("retire-disk", cmd_retire_disk)):
        command = sub.add_parser(name)
        command.add_argument("--vm", required=True)
        if name == "wait":
            command.add_argument("--timeout", type=int, default=1800)
        command.set_defaults(func=func)
    try:
        args = parser.parse_args()
        args.func(args)
        return 0
    except (OpsError, KeyboardInterrupt) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

