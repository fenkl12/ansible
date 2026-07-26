#!/usr/bin/env python3
"""Restart a deployment VM through the TrueNAS API."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any

from truenas_ops import api


ROOT = Path(__file__).resolve().parents[1]
STOP_TIMEOUT = 180
START_TIMEOUT = 60
START_STABILITY = 5
POLL_INTERVAL = 2
TERMINAL_JOB_FAILURES = {"ABORTED", "FAILED"}


class RestartError(RuntimeError):
    pass


def find_vm(*, name: str | None = None, vm_id: int | None = None) -> dict[str, Any]:
    vm = next(
        (
            item
            for item in api("vm")
            if (name is not None and item.get("name") == name)
            or (vm_id is not None and item.get("id") == vm_id)
        ),
        None,
    )
    identity = name if name is not None else vm_id
    if vm is None:
        raise RestartError(f"VM was not found: {identity}")
    return vm


def wait_for_job(job_id: int, timeout: int = STOP_TIMEOUT) -> None:
    deadline = time.monotonic() + timeout
    while True:
        job = next((item for item in api("core/get_jobs") if item.get("id") == job_id), None)
        if job is None:
            raise RestartError(f"TrueNAS stop job disappeared: {job_id}")

        state = str(job.get("state", "")).upper()
        if state == "SUCCESS":
            return
        if state in TERMINAL_JOB_FAILURES:
            detail = job.get("error") or "no error detail"
            raise RestartError(f"TrueNAS stop job {job_id} ended in {state}: {detail}")
        if time.monotonic() >= deadline:
            raise RestartError(f"Timed out waiting for TrueNAS stop job {job_id}")
        time.sleep(POLL_INTERVAL)


def wait_for_state(vm_id: int, expected: str, timeout: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while True:
        vm = find_vm(vm_id=vm_id)
        state = vm.get("status", {}).get("state")
        if state == expected:
            return vm
        if time.monotonic() >= deadline:
            raise RestartError(f"VM {vm_id} did not reach {expected}; current state={state}")
        time.sleep(POLL_INTERVAL)


def start_and_wait(vm_id: int) -> dict[str, Any]:
    started = api(f"vm/id/{vm_id}/start", {})
    if started not in (None, True):
        raise RestartError(f"TrueNAS rejected start for VM {vm_id}: {started!r}")
    wait_for_state(vm_id, "RUNNING", START_TIMEOUT)
    time.sleep(START_STABILITY)
    vm = find_vm(vm_id=vm_id)
    state = vm.get("status", {}).get("state")
    if state != "RUNNING":
        raise RestartError(
            f"VM {vm_id} entered RUNNING but was not stable; current state={state}"
        )
    return vm


def deployment_vm(deployment_name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    path = ROOT / "deployments" / deployment_name / "deployment.auto.tfvars.json"
    if not path.is_file():
        raise RestartError(f"Unknown deployment: {deployment_name}")
    deployment = json.loads(path.read_text(encoding="utf-8"))
    return deployment, find_vm(name=deployment["vm_name"])


def start(deployment_name: str) -> None:
    deployment, vm = deployment_vm(deployment_name)
    state = vm.get("status", {}).get("state")
    if state == "RUNNING":
        print(f"Already running: {deployment['vm_name']}")
        return
    if state != "STOPPED":
        raise RestartError(f"VM {vm['id']} cannot be started from state={state}")
    start_and_wait(vm["id"])
    print(f"Started {deployment['vm_name']}")


def restart(deployment_name: str) -> None:
    deployment, vm = deployment_vm(deployment_name)
    vm_id = vm["id"]
    state = vm.get("status", {}).get("state")

    if state == "RUNNING":
        job_id = api(f"vm/id/{vm_id}/stop", {"force": False, "force_after_timeout": True})
        if not isinstance(job_id, int):
            raise RestartError(f"TrueNAS did not return a stop job ID for VM {vm_id}")
        wait_for_job(job_id)
        vm = find_vm(vm_id=vm_id)
        state = vm.get("status", {}).get("state")
        if state != "STOPPED":
            raise RestartError(f"TrueNAS stop job succeeded but VM {vm_id} state={state}")
    elif state != "STOPPED":
        raise RestartError(f"VM {vm_id} cannot be restarted from state={state}")

    start_and_wait(vm_id)
    print(f"Restarted {deployment['vm_name']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("deployment")
    parser.add_argument(
        "--start",
        action="store_true",
        help="Start a stopped VM without restarting an already-running VM",
    )
    args = parser.parse_args(argv)
    try:
        (start if args.start else restart)(args.deployment)
        return 0
    except (RestartError, OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
