"""Name filters used by TrueNAS VM playbooks."""

from __future__ import annotations

import re


def truenas_hostname(value: object) -> str:
    """Convert a registered VM name into a valid, stable host name."""
    result = re.sub(r"[^a-z0-9-]+", "-", str(value).lower().replace("_", "-"))
    result = re.sub(r"-+", "-", result).strip("-")[:63].rstrip("-")
    if not result:
        raise ValueError("VM name does not produce a valid hostname")
    return result


class FilterModule:
    def filters(self) -> dict[str, object]:
        return {"truenas_hostname": truenas_hostname}
