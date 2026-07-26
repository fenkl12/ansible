#!/usr/bin/env python3
"""Boot the stock Ubuntu installer unattended without modifying its ISO."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any
from urllib.parse import urljoin

from restart_vm import RestartError, find_vm, start_and_wait, wait_for_job
from truenas_ops import (
    API_URL,
    OpsError,
    api,
    deployment,
    file_stat,
    installed_guest_ready,
    token,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ISO = "/mnt/WD1TB/ISOs/ubuntu-24.04-live-server-amd64.iso"
INSTALL_TIMEOUT = 3600
READY_TIMEOUT = 900
RESUME_VERIFY_TIMEOUT = 300
POLL_INTERVAL = 5


class InstallerError(RuntimeError):
    pass


def source_identity(item: dict[str, Any]) -> dict[str, Any]:
    source = item.get("ubuntu_iso_path", DEFAULT_ISO)
    stat = file_stat(source)
    if stat.get("type") != "FILE" or int(stat.get("size", 0)) <= 0:
        raise InstallerError(f"Ubuntu ISO is missing or empty: {source}")
    return {
        "path": source,
        "size": int(stat["size"]),
        "mtime": float(stat.get("mtime", 0)),
    }


def artifact_paths(item: dict[str, Any], identity: dict[str, Any]) -> dict[str, str]:
    source_name = PurePosixPath(identity["path"]).name
    stem = source_name.removesuffix(".iso")
    base = f"/mnt/{item.get('storage_pool', 'WD1TB')}/ISOs/.truenasVM-{stem}"
    return {
        "kernel": f"{base}-vmlinuz",
        "initrd": f"{base}-initrd",
        "manifest": f"{base}-manifest.json",
    }


def remote_file(path: str) -> bool:
    try:
        stat = file_stat(path)
    except OpsError:
        return False
    return stat.get("type") == "FILE" and int(stat.get("size", 0)) > 0


def download_remote(path: str, destination: Path) -> None:
    response = api(
        "core/download",
        {"method": "filesystem.get", "args": [path], "filename": PurePosixPath(path).name},
    )
    if not isinstance(response, list) or len(response) != 2:
        raise InstallerError(f"TrueNAS did not provide a download URL for {path}")
    url = urljoin(API_URL.split("/api/", 1)[0] + "/", str(response[1]).lstrip("/"))
    result = subprocess.run(
        [
            "curl",
            "--fail",
            "--silent",
            "--show-error",
            "--insecure",
            "--header",
            f"Authorization: Bearer {token()}",
            "--output",
            str(destination),
            url,
        ],
        check=False,
    )
    if result.returncode != 0:
        raise InstallerError(f"Failed to download {path} from TrueNAS")


def upload_remote(source: Path, destination: str) -> None:
    result = subprocess.run(
        [
            "curl",
            "--fail",
            "--silent",
            "--show-error",
            "--insecure",
            "--header",
            f"Authorization: Bearer {token()}",
            "--form",
            f'data={{"path":{json.dumps(destination)}}}',
            "--form",
            f"file=@{source}",
            f"{API_URL}/filesystem/put",
        ],
        check=False,
    )
    if result.returncode != 0:
        raise InstallerError(f"Failed to upload installer artifact: {destination}")


def load_remote_manifest(path: str) -> dict[str, Any] | None:
    if not remote_file(path):
        return None
    with tempfile.TemporaryDirectory(prefix="truenasvm-manifest-") as directory:
        local = Path(directory) / "manifest.json"
        download_remote(path, local)
        try:
            return json.loads(local.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare(item: dict[str, Any]) -> tuple[dict[str, str], dict[str, Any]]:
    identity = source_identity(item)
    paths = artifact_paths(item, identity)
    manifest = load_remote_manifest(paths["manifest"])
    if (
        manifest
        and manifest.get("source") == identity
        and remote_file(paths["kernel"])
        and remote_file(paths["initrd"])
    ):
        print(f"Installer boot artifacts ready: {paths['kernel']}, {paths['initrd']}")
        return paths, manifest

    xorriso = shutil.which("xorriso")
    if not xorriso:
        raise InstallerError(
            "xorriso is required once to prepare installer boot files; "
            "install it, then rerun make provision-base"
        )

    with tempfile.TemporaryDirectory(prefix="truenasvm-installer-") as directory:
        work = Path(directory)
        iso = work / "source.iso"
        kernel = work / "vmlinuz"
        initrd = work / "initrd"
        download_remote(identity["path"], iso)
        identity["sha256"] = sha256(iso)
        for member, output in (("/casper/vmlinuz", kernel), ("/casper/initrd", initrd)):
            result = subprocess.run(
                [xorriso, "-osirrox", "on", "-indev", str(iso), "-extract", member, str(output)],
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
                detail = result.stderr.strip() or result.stdout.strip()
                raise InstallerError(f"Failed to extract {member} from Ubuntu ISO: {detail}")

        manifest = {
            "source": {key: identity[key] for key in ("path", "size", "mtime")},
            "source_sha256": identity["sha256"],
            "kernel_sha256": sha256(kernel),
            "initrd_sha256": sha256(initrd),
        }
        manifest_file = work / "manifest.json"
        manifest_file.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        upload_remote(kernel, paths["kernel"])
        upload_remote(initrd, paths["initrd"])
        upload_remote(manifest_file, paths["manifest"])

    print(f"Prepared installer boot artifacts from unchanged ISO: {identity['path']}")
    return paths, manifest


def stop_and_wait(vm: dict[str, Any]) -> dict[str, Any]:
    state = vm.get("status", {}).get("state")
    if state == "STOPPED":
        return vm
    if state != "RUNNING":
        raise InstallerError(f"VM {vm['id']} cannot stop safely from state={state}")
    job_id = api(f"vm/id/{vm['id']}/stop", {"force": False, "force_after_timeout": True})
    if not isinstance(job_id, int):
        raise InstallerError(f"TrueNAS did not return a stop job ID for VM {vm['id']}")
    try:
        wait_for_job(job_id)
    except RestartError as exc:
        raise InstallerError(str(exc)) from exc
    stopped = find_vm(vm_id=vm["id"])
    if stopped.get("status", {}).get("state") != "STOPPED":
        raise InstallerError(f"Stop job succeeded but VM {vm['id']} is not stopped")
    return stopped


def set_boot_arguments(vm_id: int, value: str) -> None:
    api(f"vm/id/{vm_id}", {"command_line_args": value}, method="PUT")
    current = find_vm(vm_id=vm_id)
    if current.get("command_line_args", "") != value:
        raise InstallerError(f"TrueNAS did not persist installer boot arguments for VM {vm_id}")


def wait_for_poweroff(vm_id: int, timeout: int = INSTALL_TIMEOUT) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        vm = find_vm(vm_id=vm_id)
        if vm.get("status", {}).get("state") == "STOPPED":
            print(f"Ubuntu installation powered off VM {vm_id}")
            return
        time.sleep(POLL_INTERVAL)
    raise InstallerError(f"Timed out waiting for Ubuntu installation to power off VM {vm_id}")


def completion_path(name: str) -> Path:
    return ROOT / "build" / name / "installer-complete.json"


def expected_zvol(item: dict[str, Any]) -> str:
    name = item["vm_name"].lower().replace("_", "-")
    return f"/dev/zvol/{item.get('storage_pool', 'WD1TB')}/{name}-disk0"


def write_completion(
    name: str, vm: dict[str, Any], manifest: dict[str, Any], zvol_path: str
) -> None:
    path = completion_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "vm_uuid": vm["uuid"],
                "vm_id": vm["id"],
                "source_sha256": manifest["source_sha256"],
                "zvol_path": zvol_path,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def completion_matches(
    name: str, vm: dict[str, Any], manifest: dict[str, Any], zvol_path: str
) -> bool:
    path = completion_path(name)
    if not path.is_file():
        return False
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        state.get("vm_uuid") == vm.get("uuid")
        and state.get("vm_id") == vm.get("id")
        and state.get("source_sha256") == manifest.get("source_sha256")
        and state.get("zvol_path") == zvol_path
    )


def wait_installed(address: str, timeout: int = READY_TIMEOUT) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if installed_guest_ready(address):
            print(f"Installed Ubuntu guest is ready at {address}")
            return
        time.sleep(POLL_INTERVAL)
    raise InstallerError(f"Installed Ubuntu guest did not become ready at {address}")


def boot_installed_and_verify(
    item: dict[str, Any], vm_id: int, *, timeout: int = READY_TIMEOUT
) -> dict[str, Any]:
    set_boot_arguments(vm_id, "")
    try:
        start_and_wait(vm_id)
    except RestartError as exc:
        raise InstallerError(f"Installed-disk start failed: {exc}") from exc
    wait_installed(item["ip_address"], timeout=timeout)
    return find_vm(vm_id=vm_id)


def run_installer(
    item: dict[str, Any], vm: dict[str, Any], expected_args: str
) -> dict[str, Any]:
    vm = stop_and_wait(vm)
    set_boot_arguments(vm["id"], expected_args)
    try:
        start_and_wait(vm["id"])
    except RestartError as exc:
        raise InstallerError(f"Installer start failed: {exc}") from exc
    print(f"Started unattended Ubuntu installation for {item['vm_name']}")
    wait_for_poweroff(vm["id"])
    return find_vm(vm_id=vm["id"])


def install(name: str) -> None:
    item = deployment(name)
    paths, manifest = prepare(item)
    vm = find_vm(name=item["vm_name"])
    expected_args = (
        f"-kernel {paths['kernel']} -initrd {paths['initrd']} "
        '-append "autoinstall ---"'
    )
    zvol_path = expected_zvol(item)
    complete = completion_matches(name, vm, manifest, zvol_path)

    if not complete:
        current_args = vm.get("command_line_args", "")
        state = vm.get("status", {}).get("state")
        if current_args == expected_args and state == "RUNNING":
            print(f"Resuming wait for Ubuntu installation on {item['vm_name']}")
            wait_for_poweroff(vm["id"])
            vm = find_vm(vm_id=vm["id"])
        elif current_args == expected_args and state == "STOPPED":
            # STOPPED may mean installation completed or direct boot failed.
            # Prove the zvol is bootable before recording completion.
            try:
                vm = boot_installed_and_verify(
                    item, vm["id"], timeout=RESUME_VERIFY_TIMEOUT
                )
            except InstallerError:
                vm = find_vm(vm_id=vm["id"])
                vm = run_installer(item, vm, expected_args)
        else:
            vm = run_installer(item, vm, expected_args)

        if vm.get("status", {}).get("state") == "STOPPED":
            vm = boot_installed_and_verify(item, vm["id"])
        write_completion(name, vm, manifest, zvol_path)
    else:
        vm = find_vm(name=item["vm_name"])
        if vm.get("command_line_args", ""):
            vm = stop_and_wait(vm)
            set_boot_arguments(vm["id"], "")
        if vm.get("status", {}).get("state") == "STOPPED":
            try:
                start_and_wait(vm["id"])
            except RestartError as exc:
                raise InstallerError(f"Installed-disk start failed: {exc}") from exc
        wait_installed(item["ip_address"])

def cmd_prepare(args: argparse.Namespace) -> None:
    prepare(deployment(args.vm))


def cmd_install(args: argparse.Namespace) -> None:
    install(args.vm)


def cmd_stop(args: argparse.Namespace) -> None:
    item = deployment(args.vm)
    stop_and_wait(find_vm(name=item["vm_name"]))
    print(f"Stopped {item['vm_name']}")


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(required=True)
    for command, func in (("prepare", cmd_prepare), ("install", cmd_install), ("stop", cmd_stop)):
        child = sub.add_parser(command)
        child.add_argument("--vm", required=True)
        child.set_defaults(func=func)
    try:
        args = parser.parse_args()
        args.func(args)
        return 0
    except (InstallerError, OpsError, RestartError, OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
