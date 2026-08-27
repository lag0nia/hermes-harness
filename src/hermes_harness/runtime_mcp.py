"""Build the real MCP bridge from the checked-in harness configuration."""

from __future__ import annotations

from pathlib import Path

from .control_plane.policy import PolicyEngine
from .control_plane.router import Router
from .observability import SQLiteObservabilitySink
from .observability_bridge import ObservabilityBridge

ROOT = Path(__file__).resolve().parents[2]


def build_bridge(root: Path = ROOT, db_path: Path | None = None) -> ObservabilityBridge:
    sink = SQLiteObservabilitySink(db_path or root / "var" / "observability.sqlite3")
    router = Router.from_files(
        root / "config" / "routing.yaml",
        root / "capabilities" / "agents",
    )
    policy = PolicyEngine.from_directory(root / "config")
    return ObservabilityBridge(router, policy, sink)
