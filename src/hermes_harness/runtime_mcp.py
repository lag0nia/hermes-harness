"""Build the real MCP bridge from the checked-in harness configuration."""

from __future__ import annotations

from pathlib import Path

from .control_plane.ledger import Ledger
from .control_plane.policy import PolicyEngine
from .control_plane.router import Router
from .dispatcher import Dispatcher
from .integrations.hermes_kanban import HermesKanbanCLI
from .observability import SQLiteObservabilitySink
from .observability_bridge import ObservabilityBridge

ROOT = Path(__file__).resolve().parents[2]


def build_bridge(root: Path = ROOT, db_path: Path | None = None) -> ObservabilityBridge:
    observability_path = db_path or root / "var" / "observability.sqlite3"
    ledger_path = (
        root / "var" / "control-plane.sqlite3"
        if db_path is None
        else db_path.with_name("control-plane.sqlite3")
    )
    sink = SQLiteObservabilitySink(observability_path)
    dispatcher = Dispatcher(
        ledger=Ledger(ledger_path, observability=sink),
        kanban=HermesKanbanCLI(observability=sink),
        observability=sink,
    )
    router = Router.from_files(
        root / "config" / "routing.yaml",
        root / "capabilities" / "agents",
    )
    policy = PolicyEngine.from_directory(root / "config")
    return ObservabilityBridge(router, policy, sink, dispatcher=dispatcher)
