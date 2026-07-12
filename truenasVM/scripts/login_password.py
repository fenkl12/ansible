#!/usr/bin/env python3
"""Return the shared VM login password or its SHA-512 crypt hash."""

from __future__ import annotations

import argparse

LOGIN_PASSWORD = "fenkil"
LOGIN_PASSWORD_HASH = "$6$truenasvm$69ePkug18xMh/3xUDy/Gpn7Q4C0Jm6IzeqzyNAYXlajxq/vnoArJQ3N9SSJj02z0J0ap1Mt9DGcVg0GRm133b/"


def password_and_hash(vm: str) -> tuple[str, str]:
    if not vm or "/" in vm or "\\" in vm or vm in {".", ".."}:
        raise ValueError("invalid deployment name")
    return LOGIN_PASSWORD, LOGIN_PASSWORD_HASH


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("vm")
    parser.add_argument("--hash", action="store_true")
    args = parser.parse_args()
    password, password_hash = password_and_hash(args.vm)
    print(password_hash if args.hash else password)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
