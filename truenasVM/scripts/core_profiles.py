#!/usr/bin/env python3
"""Manage declarative core-profile assignment for TrueNAS VMs."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
FLEET = ROOT / "fleet.json"
DEPLOYMENTS = ROOT / "deployments"
PROFILES = ROOT / "ansible" / "core_profiles"
BUILD = ROOT / "build"
PROFILE_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")
VM_RE = re.compile(r"^[A-Za-z][A-Za-z0-9-]*_IP\d{1,3}$")


class ProfileError(RuntimeError):
    pass


def load_fleet() -> dict[str, Any]:
    if not FLEET.is_file():
        return {"deployments": {}}
    return json.loads(FLEET.read_text(encoding="utf-8"))


def atomic_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def validate_profile_name(profile: str) -> str:
    if not PROFILE_RE.fullmatch(profile):
        raise ProfileError("Profile names must use lowercase kebab-case")
    return profile


def validate_vm_name(vm: str) -> str:
    if not VM_RE.fullmatch(vm):
        raise ProfileError("Invalid deployment name")
    return vm


def profile_path(profile: str) -> Path:
    return PROFILES / validate_profile_name(profile)


def require_profile(profile: str) -> Path:
    path = profile_path(profile)
    missing = [name for name in ("site.yml", "vars.yml", "profile.json") if not (path / name).is_file()]
    if missing:
        raise ProfileError(f"Unknown or incomplete core profile {profile}: missing {', '.join(missing)}")
    return path


def fleet_entry(vm: str, fleet: dict[str, Any]) -> dict[str, Any]:
    validate_vm_name(vm)
    if not (DEPLOYMENTS / vm / "deployment.auto.tfvars.json").is_file():
        raise ProfileError(f"Unknown deployment: {vm}")
    try:
        return fleet["deployments"][vm]
    except KeyError as exc:
        raise ProfileError(f"Deployment is missing from fleet registry: {vm}") from exc


def select_profile(vm: str, requested: str | None) -> str:
    fleet = load_fleet()
    entry = fleet_entry(vm, fleet)
    current = entry.get("core_profile")
    if current:
        require_profile(current)
        if requested and requested != current:
            raise ProfileError(
                f"{vm} is assigned to {current}, not {requested}; use change-core-profile explicitly"
            )
        return current
    if not requested:
        raise ProfileError(f"{vm} has no core profile; set PROFILE=<name> on the first core setup")
    require_profile(requested)
    return requested


def assign_profile(vm: str, requested: str | None) -> str:
    selected = select_profile(vm, requested)
    fleet = load_fleet()
    entry = fleet_entry(vm, fleet)
    if entry.get("core_profile"):
        return selected
    entry["core_profile"] = selected
    atomic_json(FLEET, fleet)
    return selected


def profile_metadata(profile: str) -> dict[str, Any]:
    path = require_profile(profile) / "profile.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    required = data.get("requires_backup_storage")
    if not isinstance(required, bool):
        raise ProfileError(f"Invalid requires_backup_storage value in {path.relative_to(ROOT)}")
    return data


def base_marker(vm: str) -> Path:
    return BUILD / validate_vm_name(vm) / "base-configured.json"


def require_base(vm: str) -> None:
    validate_vm_name(vm)
    if not (DEPLOYMENTS / vm / "deployment.auto.tfvars.json").is_file():
        raise ProfileError(f"Unknown deployment: {vm}")
    if not base_marker(vm).is_file():
        raise ProfileError(f"Base configuration has not completed for {vm}; run make provision-base VM={vm}")


def cmd_create(args: argparse.Namespace) -> None:
    target = profile_path(args.profile)
    if target.exists():
        raise ProfileError(f"Core profile already exists: {args.profile}")
    target.mkdir(parents=True)
    (target / "vars.yml").write_text(
        "---\n# Declare profile-specific variables here.\n", encoding="utf-8"
    )
    atomic_json(target / "profile.json", {"requires_backup_storage": False})
    (target / "site.yml").write_text(
        "---\n"
        f"- name: Configure {args.profile} core profile\n"
        "  hosts: all\n"
        "  become: true\n"
        "  gather_facts: true\n"
        "  vars_files:\n"
        "    - vars.yml\n"
        "  tasks:\n"
        "    - name: Confirm core profile scaffold\n"
        "      ansible.builtin.debug:\n"
        f"        msg: Replace this task with the declared state for {args.profile}\n"
        "      changed_when: false\n",
        encoding="utf-8",
    )
    print(f"Created core profile: {target.relative_to(ROOT)}")


def cmd_resolve(args: argparse.Namespace) -> None:
    print(assign_profile(args.vm, args.profile))


def cmd_select(args: argparse.Namespace) -> None:
    print(select_profile(args.vm, args.profile))


def cmd_requires_backup(args: argparse.Namespace) -> None:
    print("true" if profile_metadata(args.profile)["requires_backup_storage"] else "false")


def cmd_change(args: argparse.Namespace) -> None:
    require_profile(args.profile)
    fleet = load_fleet()
    entry = fleet_entry(args.vm, fleet)
    current = entry.get("core_profile")
    if current == args.profile:
        print(f"{args.vm} is already assigned to {args.profile}")
        return
    if not args.yes:
        old = current or "unassigned"
        prompt = (
            f"Change {args.vm} from {old} to {args.profile}? Existing guest state will not be removed. [y/N]: "
        )
        if input(prompt).strip().lower() not in {"y", "yes"}:
            raise ProfileError("Profile change cancelled")
    entry["core_profile"] = args.profile
    atomic_json(FLEET, fleet)
    print(f"Assigned {args.vm} to {args.profile}")
    print("For a strictly clean profile transition, rebuild the VM before reconciliation.")


def cmd_mark_base(args: argparse.Namespace) -> None:
    validate_vm_name(args.vm)
    if not (DEPLOYMENTS / args.vm / "deployment.auto.tfvars.json").is_file():
        raise ProfileError(f"Unknown deployment: {args.vm}")
    atomic_json(
        base_marker(args.vm),
        {"vm": args.vm, "configured_at": datetime.now(timezone.utc).isoformat()},
    )
    print(f"Recorded successful base configuration for {args.vm}")


def cmd_require_base(args: argparse.Namespace) -> None:
    require_base(args.vm)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    sub = result.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("--profile", required=True)
    create.set_defaults(func=cmd_create)
    resolve = sub.add_parser("resolve")
    resolve.add_argument("--vm", required=True)
    resolve.add_argument("--profile")
    resolve.set_defaults(func=cmd_resolve)
    select = sub.add_parser("select")
    select.add_argument("--vm", required=True)
    select.add_argument("--profile")
    select.set_defaults(func=cmd_select)
    requires = sub.add_parser("requires-backup")
    requires.add_argument("--profile", required=True)
    requires.set_defaults(func=cmd_requires_backup)
    change = sub.add_parser("change")
    change.add_argument("--vm", required=True)
    change.add_argument("--profile", required=True)
    change.add_argument("--yes", action="store_true")
    change.set_defaults(func=cmd_change)
    mark = sub.add_parser("mark-base")
    mark.add_argument("--vm", required=True)
    mark.set_defaults(func=cmd_mark_base)
    require = sub.add_parser("require-base")
    require.add_argument("--vm", required=True)
    require.set_defaults(func=cmd_require_base)
    return result


def main() -> None:
    args = parser().parse_args()
    try:
        args.func(args)
    except (ProfileError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
