#!/usr/bin/env python3
"""TrueNAS-aware deployment registry and VM address selector."""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import shutil
import ssl
import subprocess
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
FLEET = ROOT / "fleet.json"
DEPLOYMENTS = ROOT / "deployments"
SECRETS = ROOT / ".secrets" / "truenas.env"
DEFAULT_URL = "https://10.0.203.171"
SUFFIXES = range(20, 241, 10)
NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9-]{1,40}$")
IP_NAME_RE = re.compile(r"_IP(\d{1,3})$")
DEFAULT_DOTFILES_PLAYBOOKS = (
    "ansible_localPc/stow_zshrc.yml",
    "ansible_localPc/stow_nvim.yml",
    "ansible_localPc/stow_codex.yml",
    "ansible_localPc/stow_myScripts.yml",
)


class FactoryError(RuntimeError):
    pass


def load_env_file(path: Path = SECRETS) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def api_get(endpoint: str) -> Any:
    load_env_file()
    token = os.environ.get("TRUENAS_API_KEY")
    if not token:
        raise FactoryError("TRUENAS_API_KEY is not set and .secrets/truenas.env is missing")
    base = os.environ.get("TRUENAS_URL", DEFAULT_URL).rstrip("/")
    request = Request(
        f"{base}/api/v2.0/{endpoint.lstrip('/')}",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
    )
    context = ssl.create_default_context()
    if os.environ.get("TRUENAS_VERIFY_TLS", "false").lower() not in {"1", "true", "yes"}:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    try:
        with urlopen(request, timeout=15, context=context) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise FactoryError(f"TrueNAS API request failed for {endpoint}: {exc}") from exc


def load_fleet() -> dict[str, Any]:
    if not FLEET.exists():
        return {"deployments": {}}
    return json.loads(FLEET.read_text(encoding="utf-8"))


def atomic_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def validate_base_name(name: str) -> str:
    name = name.strip()
    if not NAME_RE.fullmatch(name):
        raise FactoryError("Name must start with a letter and contain only letters, numbers, or hyphens")
    return name


def ping_in_use(address: str) -> bool:
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "1", address],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            timeout=2,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def neighbor_addresses() -> set[str]:
    try:
        output = subprocess.run(
            ["ip", "-4", "neigh", "show"], capture_output=True, text=True, check=False, timeout=3
        ).stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return set()
    resolved: set[str] = set()
    for line in output.splitlines():
        fields = line.split()
        # Failed probes create FAILED/INCOMPLETE entries without a MAC.
        if fields and "lladdr" in fields and not ({"FAILED", "INCOMPLETE"} & set(fields)):
            resolved.add(fields[0])
    return resolved


def discovered_allocations() -> tuple[set[str], set[str]]:
    names: set[str] = set()
    addresses: set[str] = {"10.0.203.171"}
    for vm in api_get("vm"):
        name = str(vm.get("name", ""))
        names.add(name)
        match = IP_NAME_RE.search(name)
        if match:
            addresses.add(f"10.0.203.{int(match.group(1))}")
    for interface in api_get("interface"):
        for alias in (interface.get("state") or {}).get("aliases", []):
            if alias.get("type") == "INET" and alias.get("address"):
                addresses.add(alias["address"])
    fleet = load_fleet().get("deployments", {})
    names.update(fleet)
    addresses.update(item["ip_address"] for item in fleet.values() if item.get("ip_address"))
    addresses.update(neighbor_addresses())
    return names, addresses


def suggestions(base_name: str, count: int = 3, probe: bool = True) -> list[tuple[str, str]]:
    base_name = validate_base_name(base_name)
    names, allocated = discovered_allocations()
    result: list[tuple[str, str]] = []
    for suffix in SUFFIXES:
        address = f"10.0.203.{suffix}"
        final_name = f"{base_name}_IP{suffix}"
        if address in allocated or final_name in names:
            continue
        if probe and ping_in_use(address):
            continue
        result.append((final_name, address))
        if len(result) == count:
            break
    return result


def find_public_key() -> tuple[Path, str]:
    configured = os.environ.get("VM_SSH_PUBLIC_KEY")
    candidates = [Path(configured).expanduser()] if configured else []
    candidates.extend([Path.home() / ".ssh/id_ed25519.pub", Path.home() / ".ssh/id_rsa.pub"])
    for path in candidates:
        if path.is_file():
            return path, path.read_text(encoding="utf-8").strip()
    raise FactoryError("No SSH public key found; set VM_SSH_PUBLIC_KEY to its path")


def deployment_path(vm: str) -> Path:
    return DEPLOYMENTS / vm


def register(base_name: str, final_name: str, address: str) -> None:
    validate_base_name(base_name)
    ipaddress.ip_address(address)
    expected_suffix = address.rsplit(".", 1)[1]
    if final_name != f"{base_name}_IP{expected_suffix}":
        raise FactoryError("VM name and IP suffix do not match")
    target = deployment_path(final_name)
    if target.exists():
        raise FactoryError(f"Deployment already exists: {final_name}")
    _, key = find_public_key()
    tfvars = {
        "vm_name": final_name,
        "ip_address": address,
        "ssh_public_key": key,
        "vcpus": 2,
        "memory_mb": 4096,
        "disk_size_gb": 40,
        "storage_pool": "WD1TB",
        "nic_attach": "enp3s0",
    }
    ansible_vars = (
        "---\n"
        "dotfiles_repo: 'http://10.0.10.20:7000/fenkil/dotfiles.git'\n"
        "dotfiles_nested_playbooks:\n"
        + "".join(f"  - {json.dumps(playbook)}\n" for playbook in DEFAULT_DOTFILES_PLAYBOOKS)
        + "nfs_server: '10.0.203.171'\n"
        "nfs_media_export: '/mnt/tank/media'\n"
        "nfs_media_mount: '/mnt/tn_media'\n"
    )
    target.mkdir(parents=True)
    atomic_json(target / "deployment.auto.tfvars.json", tfvars)
    (target / "ansible-vars.yml").write_text(ansible_vars, encoding="utf-8")
    fleet = load_fleet()
    fleet.setdefault("deployments", {})[final_name] = {
        "base_name": base_name,
        "ip_address": address,
        "core_profile": None,
    }
    atomic_json(FLEET, fleet)


def cmd_create(_: argparse.Namespace) -> None:
    base = validate_base_name(input("Base VM name (for example web): "))
    options = suggestions(base)
    if not options:
        raise FactoryError("No available candidate addresses were found")
    print("\nAvailable suggestions (offline devices may not answer probes):")
    for index, (name, address) in enumerate(options, 1):
        print(f"  {index}. {name:<32} {address}")
    raw = input("Select 1-3, or q to cancel: ").strip().lower()
    if raw == "q":
        return
    try:
        selected = options[int(raw) - 1]
    except (ValueError, IndexError) as exc:
        raise FactoryError("Invalid selection") from exc
    confirm = input(f"Register {selected[0]} at {selected[1]}? [y/N]: ").strip().lower()
    if confirm not in {"y", "yes"}:
        print("Cancelled")
        return
    latest = suggestions(base, count=24)
    if selected not in latest:
        raise FactoryError("The selected name or IP became unavailable; run again")
    register(base, selected[0], selected[1])
    print(f"Registered {selected[0]}. Run: make deploy VM={selected[0]}")


def cmd_suggest(args: argparse.Namespace) -> None:
    base = args.name or input("Base VM name: ")
    for name, address in suggestions(base, count=5):
        print(f"{name}\t{address}")


def cmd_list(_: argparse.Namespace) -> None:
    deployments = load_fleet().get("deployments", {})
    if not deployments:
        print("No deployments registered")
        return
    for name, item in sorted(deployments.items()):
        marker = ROOT / "build" / name / "base-configured.json"
        base_status = "base-ready" if marker.is_file() else "base-pending"
        profile = item.get("core_profile") or "unassigned"
        print(f"{name:<36} {item['ip_address']:<16} {base_status:<13} {profile}")


def cmd_remove(args: argparse.Namespace) -> None:
    target = deployment_path(args.vm)
    if target.resolve().parent != DEPLOYMENTS.resolve():
        raise FactoryError("Invalid deployment name")
    deployment = get_deployment(args.vm)
    vm_names = {vm.get("name") for vm in api_get("vm")}
    if deployment["vm_name"] in vm_names:
        raise FactoryError(f"VM still exists: {deployment['vm_name']}; destroy it before removing the deployment")
    zvol_name = f"{deployment['storage_pool']}/{deployment['vm_name'].lower().replace('_', '-')}-disk0"
    datasets = {item.get("id") for item in api_get("pool/dataset")}
    if zvol_name in datasets:
        raise FactoryError(f"Zvol still exists: {zvol_name}; run make destroy-disk VM={args.vm} first")

    build_target = ROOT / "build" / args.vm
    if build_target.resolve().parent != (ROOT / "build").resolve():
        raise FactoryError("Invalid deployment name")
    shutil.rmtree(target)
    if build_target.exists():
        shutil.rmtree(build_target)
    for secret_name in (f"{args.vm}.console_password", f"{args.vm}.login_password", f"{args.vm}.login_password_hash"):
        secret_path = ROOT / ".secrets" / secret_name
        if secret_path.exists():
            secret_path.unlink()
    fleet = load_fleet()
    fleet.setdefault("deployments", {}).pop(args.vm, None)
    atomic_json(FLEET, fleet)
    print(f"Removed deployment files: {target.relative_to(ROOT)}")
    print(f"Removed fleet entry: {args.vm}")


def get_deployment(vm: str) -> dict[str, Any]:
    path = deployment_path(vm) / "deployment.auto.tfvars.json"
    if not path.is_file():
        raise FactoryError(f"Unknown deployment: {vm}")
    return json.loads(path.read_text(encoding="utf-8"))


def cmd_preflight(args: argparse.Namespace) -> None:
    deployment = get_deployment(args.vm)
    system = api_get("system/info")
    version = str(system.get("version", ""))
    if "24.04" not in version:
        raise FactoryError(f"Expected TrueNAS 24.04, found {version}; validate provider compatibility")
    state_exists = (deployment_path(args.vm) / "terraform.tfstate").exists()
    existing_vm_names = {vm.get("name") for vm in api_get("vm")}
    # Never let a fresh deployment provision over an already-existing TrueNAS VM name.
    if deployment["vm_name"] in existing_vm_names and not state_exists:
        raise FactoryError("VM exists in TrueNAS but this deployment has no state; import it before continuing")
    if not state_exists and ping_in_use(deployment["ip_address"]):
        raise FactoryError(f"IP responds before first deployment: {deployment['ip_address']}")
    datasets = {item.get("id") for item in api_get("pool/dataset")}
    zvol_name = f"{deployment['storage_pool']}/{deployment['vm_name'].lower().replace('_', '-')}-disk0"
    if zvol_name in datasets and not state_exists:
        raise FactoryError(f"Zvol exists but this deployment has no state: {zvol_name}")
    print(f"Preflight OK: {deployment['vm_name']} on {version}")


def cmd_inventory(args: argparse.Namespace) -> None:
    deployment = get_deployment(args.vm)
    out = ROOT / "build" / args.vm / "inventory.yml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        "all:\n  hosts:\n"
        f"    {deployment['vm_name']}:\n"
        f"      ansible_host: {deployment['ip_address']}\n"
        "      ansible_user: fenkil\n"
        "      ansible_become: true\n",
        encoding="utf-8",
    )
    print(out.relative_to(ROOT))


def cmd_wait(args: argparse.Namespace) -> None:
    deployment = get_deployment(args.vm)
    address = deployment["ip_address"]
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((address, 22), timeout=3):
                print(f"SSH is ready at {address}")
                return
        except OSError:
            time.sleep(5)
    raise FactoryError(f"Timed out waiting for SSH at {address}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    sub = result.add_subparsers(dest="command", required=True)
    sub.add_parser("create").set_defaults(func=cmd_create)
    suggest = sub.add_parser("suggest")
    suggest.add_argument("--name")
    suggest.set_defaults(func=cmd_suggest)
    sub.add_parser("list").set_defaults(func=cmd_list)
    remove = sub.add_parser("remove")
    remove.add_argument("--vm", required=True)
    remove.set_defaults(func=cmd_remove)
    for command, function in (("preflight", cmd_preflight), ("inventory", cmd_inventory), ("wait", cmd_wait)):
        item = sub.add_parser(command)
        item.add_argument("--vm", required=True)
        if command == "wait":
            item.add_argument("--timeout", type=int, default=600)
        item.set_defaults(func=function)
    return result


def main() -> int:
    try:
        args = parser().parse_args()
        args.func(args)
        return 0
    except (FactoryError, KeyboardInterrupt) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
