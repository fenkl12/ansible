#!/usr/bin/env python3
"""Safe TrueNAS deployment preflight, verification, and readiness checks."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
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
BACKUP_PARENT_DATASET = "tank/backups/truenasVM"
BACKUP_DATASET = f"{BACKUP_PARENT_DATASET}/dataOnly"
BACKUP_EXPORT_PATH = f"/mnt/{BACKUP_DATASET}"
BACKUP_NETWORK = "10.0.0.0/16"
SSH_USER = "fenkil"
INSTALL_MARKER = "/etc/truenas-vm-installed"


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
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace").strip()
        detail = f"; {body}" if body else ""
        raise OpsError(f"TrueNAS API request failed: {exc}{detail}") from exc
    except (URLError, TimeoutError) as exc:
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


def backup_storage_problems() -> list[str]:
    problems: list[str] = []

    datasets = {item.get("id"): item for item in api("pool/dataset")}
    for name in (BACKUP_PARENT_DATASET, BACKUP_DATASET):
        dataset = datasets.get(name)
        if not dataset:
            problems.append(f"missing dataset {name}")
        elif dataset.get("type") != "FILESYSTEM":
            problems.append(f"dataset is not a filesystem: {name}")

    shares = [item for item in api("sharing/nfs") if item.get("path") == BACKUP_EXPORT_PATH]
    if not shares:
        problems.append(f"missing NFS export {BACKUP_EXPORT_PATH}")
    else:
        share = shares[0]
        if not share.get("enabled"):
            problems.append("backup NFS export is disabled")
        if share.get("ro", share.get("readonly", False)):
            problems.append("backup NFS export is read-only")
        if BACKUP_NETWORK not in (share.get("networks") or []):
            problems.append(f"backup NFS export does not authorize {BACKUP_NETWORK}")
        if share.get("maproot_user") != "root":
            problems.append("backup NFS export does not map root to root")

    tasks = [item for item in api("pool/snapshottask") if item.get("dataset") == BACKUP_DATASET]
    if not tasks:
        problems.append(f"missing snapshot task for {BACKUP_DATASET}")
    else:
        task = tasks[0]
        schedule = task.get("schedule") or {}
        if not task.get("enabled"):
            problems.append("backup snapshot task is disabled")
        if task.get("lifetime_value") != 30 or task.get("lifetime_unit") != "DAY":
            problems.append("backup snapshot retention is not 30 days")
        if schedule.get("hour") != "2" or schedule.get("minute") != "0":
            problems.append("backup snapshot schedule is not daily at 02:00")

    return problems


def cmd_backup_storage_check(_: argparse.Namespace) -> None:
    problems = backup_storage_problems()
    if problems:
        detail = "; ".join(problems)
        raise OpsError(
            f"Shared backup storage is unavailable or unhealthy: {detail}. "
            "Run make backup-storage-apply once, then retry."
        )
    print(f"Backup storage OK: {BACKUP_DATASET} exported at {BACKUP_EXPORT_PATH}")


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

    devices = vm.get("devices", [])
    types = {device.get("dtype") for device in devices}
    problems = []
    missing = {"DISK", "NIC", "CDROM", "DISPLAY"} - types
    if missing:
        problems.append(f"missing device types={sorted(missing)}")
    if not vm.get("display_available"):
        problems.append("display unavailable")

    expected_disk = f"/dev/zvol/{zvol_name(item)}"
    disk_paths = {
        (device.get("attributes") or {}).get("path")
        for device in devices
        if device.get("dtype") == "DISK"
    }
    if expected_disk not in disk_paths:
        problems.append(f"expected disk is not attached: {expected_disk}")

    nic_targets = {
        (device.get("attributes") or {}).get("nic_attach")
        for device in devices
        if device.get("dtype") == "NIC"
    }
    if item.get("nic_attach", "enp3s0") not in nic_targets:
        problems.append(f"expected NIC target is not attached: {item.get('nic_attach', 'enp3s0')}")

    seed_path = f"/mnt/{item.get('storage_pool', 'WD1TB')}/ISOs/cloud-init-{item['vm_name']}.iso"
    cdrom_paths = {
        (device.get("attributes") or {}).get("path")
        for device in devices
        if device.get("dtype") == "CDROM"
    }
    if seed_path not in cdrom_paths:
        problems.append(f"cloud-init ISO is not attached: {seed_path}")
    installer_path = item.get(
        "ubuntu_iso_path",
        "/mnt/WD1TB/ISOs/ubuntu-24.04-live-server-amd64.iso",
    )
    phase = item.get("provisioning_phase", "install")
    if phase == "install" and installer_path not in cdrom_paths:
        problems.append(f"installer ISO is not attached: {installer_path}")
    if phase == "bootstrap" and installer_path in cdrom_paths:
        problems.append(f"installer ISO is still attached: {installer_path}")

    seed = file_stat(seed_path)
    if seed.get("type") != "FILE" or int(seed.get("size", 0)) == 0:
        problems.append(f"cloud-init ISO is missing or empty: {seed_path}")
    if problems:
        raise OpsError("VM verification failed: " + "; ".join(problems))
    print(f"VM verification OK: id={vm['id']} state={vm['status']['state']} console=available")

def cmd_detach_installer(args: argparse.Namespace) -> None:
    item = deployment(args.vm)
    vm_name = item["vm_name"]
    vm = find_vm(vm_name)
    if not vm:
        raise OpsError(f"VM was not found: {vm_name}")
    vm_id = vm["id"]
    if vm.get("status", {}).get("state") != "STOPPED":
        raise OpsError(f"Refusing to detach installer ISO while VM {vm_id} is running")

    iso_path = item.get(
        "ubuntu_iso_path",
        "/mnt/WD1TB/ISOs/ubuntu-24.04-live-server-amd64.iso",
    )
    devices = [
        device
        for device in vm.get("devices", [])
        if device.get("dtype") == "CDROM"
        and device.get("attributes", {}).get("path") == iso_path
    ]
    for device in devices:
        device_id = device["id"]
        deleted = api(
            f"vm/device/id/{device_id}",
            {"force": False},
            method="DELETE",
        )
        if deleted is not True:
            raise OpsError(
                f"TrueNAS did not confirm detachment of installer ISO device {device_id}"
            )

    current = find_vm(vm_name)
    if any(
        device.get("dtype") == "CDROM"
        and device.get("attributes", {}).get("path") == iso_path
        for device in current.get("devices", [])
    ):
        raise OpsError(f"Installer ISO is still attached: {iso_path}")
    print(f"Installer ISO detached: {iso_path}")


def cmd_status(args: argparse.Namespace) -> None:
    item = deployment(args.vm)
    vm = find_vm(item["vm_name"])
    expected_dataset = zvol_name(item)
    datasets = {entry.get("id") for entry in api("pool/dataset")}
    completion = ROOT / "build" / args.vm / "installer-complete.json"
    state_file = ROOT / "deployments" / args.vm / "terraform.tfstate"
    devices = []
    if vm:
        devices = [
            {
                "id": device.get("id"),
                "type": device.get("dtype"),
                "order": device.get("order"),
                "path": (device.get("attributes") or {}).get("path"),
            }
            for device in vm.get("devices", [])
        ]
    report = {
        "deployment": args.vm,
        "vm_name": item["vm_name"],
        "phase": item.get("provisioning_phase", "install"),
        "ip_address": item["ip_address"],
        "terraform_state": state_file.is_file(),
        "zvol": expected_dataset,
        "zvol_present": expected_dataset in datasets,
        "installer_checkpoint": completion.is_file(),
        "vm_present": vm is not None,
        "vm_id": vm.get("id") if vm else None,
        "status": vm.get("status") if vm else None,
        "command_line_args": vm.get("command_line_args") if vm else None,
        "display_available": vm.get("display_available") if vm else False,
        "devices": devices,
        "installed_guest_ready": installed_guest_ready(item["ip_address"]),
    }
    print(json.dumps(report, indent=2, sort_keys=True))


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


def installed_guest_ready(address: str) -> bool:
    command = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=5",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        f"{SSH_USER}@{address}",
        f'test -f {INSTALL_MARKER} && test "$(findmnt -n -o FSTYPE /)" != overlay',
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def cmd_wait_installed(args: argparse.Namespace) -> None:
    item = deployment(args.vm)
    address = item["ip_address"]
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        if installed_guest_ready(address):
            print(f"Installed guest is ready at {address}")
            return
        time.sleep(5)
    vm = find_vm(item["vm_name"])
    detail = f"status={vm.get('status')} display={vm.get('display_available')}" if vm else "VM not found"
    raise OpsError(f"Installed guest timeout at {address}; {detail}. Open the VM display in TrueNAS.")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(required=True)
    sub.add_parser("secret").set_defaults(func=cmd_secret)
    sub.add_parser("backup-storage-check").set_defaults(func=cmd_backup_storage_check)
    for name, func in (
        ("preflight", cmd_preflight),
        ("verify", cmd_verify),
        ("detach-installer", cmd_detach_installer),
        ("status", cmd_status),
        ("wait", cmd_wait),
        ("wait-installed", cmd_wait_installed),
        ("retire-disk", cmd_retire_disk),
    ):
        command = sub.add_parser(name)
        command.add_argument("--vm", required=True)
        if name in {"wait", "wait-installed"}:
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
