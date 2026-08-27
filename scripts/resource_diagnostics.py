#!/usr/bin/env python3
"""Read-only resource diagnostics for scheduler calibration."""

from __future__ import annotations

import json
import os
from pathlib import Path


def _read(path: str) -> int | None:
    try:
        value = Path(path).read_text().strip()
        return None if value == "max" else int(value)
    except (FileNotFoundError, PermissionError, ValueError):
        return None


def diagnostics() -> dict[str, object]:
    current = _read("/sys/fs/cgroup/memory.current")
    maximum = _read("/sys/fs/cgroup/memory.max")
    try:
        load = os.getloadavg()
    except OSError:
        load = (0.0, 0.0, 0.0)
    return {
        "cgroup": {"current_bytes": current, "max_bytes": maximum},
        "load": {"one": load[0], "five": load[1], "fifteen": load[2]},
        "cpu_count": os.cpu_count(),
        "read_only": True,
    }


if __name__ == "__main__":
    print(json.dumps(diagnostics(), sort_keys=True))
