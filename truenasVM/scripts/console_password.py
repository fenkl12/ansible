#!/usr/bin/env python3
"""Return the shared TrueNAS SPICE password for a deployment."""

from __future__ import annotations

import argparse

CONSOLE_PASSWORD = "fenkil"


def password_for_vm(vm: str) -> str:
    if not vm or "/" in vm or "\\" in vm or vm in {".", ".."}:
        raise ValueError("invalid deployment name")
    return CONSOLE_PASSWORD


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("vm")
    args = parser.parse_args()
    print(password_for_vm(args.vm))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
