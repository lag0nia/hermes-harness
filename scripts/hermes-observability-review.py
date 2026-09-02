"""Hermes cron wrapper for the bounded observability review runner."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO_ROOT = Path(os.environ.get("HERMES_HARNESS_ROOT", Path(__file__).resolve().parents[1]))
_PLUGIN_ROOT = Path(
    os.environ.get(
        "HERMES_OBSERVABILITY_SOURCE",
        _REPO_ROOT.parent / "plugin-src" / "hermes-observability",
    )
)
for _path in (_REPO_ROOT / "src", _PLUGIN_ROOT / "src"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


def _run() -> int:
    from hermes_harness.observability_review_runner import main

    return main()


raise SystemExit(_run())
