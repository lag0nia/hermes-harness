from pathlib import Path

from hermes_harness.dispatcher import Dispatcher
from hermes_harness.integrations.hermes_kanban import HermesKanbanCLI
from hermes_harness.mcp_server import create_server
from hermes_harness.runtime_mcp import build_bridge

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def runtime_root(tmp_path: Path) -> Path:
    root = tmp_path / "runtime-root"
    root.mkdir()
    for name in ("config", "capabilities"):
        (root / name).symlink_to(PROJECT_ROOT / name, target_is_directory=True)
    return root


def test_runtime_mcp_bridge_loads_real_routing_and_tools(tmp_path: Path):
    server = create_server(build_bridge(db_path=tmp_path / "events.db"))
    assert set(server._tool_manager._tools) == {
        "harness_plan_intent",
        "harness_submit_read_only",
        "harness_submit",
        "harness_job_status",
        "harness_trace_context",
    }


def test_runtime_mcp_builds_full_dispatcher_with_control_plane_ledger(tmp_path: Path) -> None:
    root = runtime_root(tmp_path)

    bridge = build_bridge(root=root)

    assert bridge.sink.path == root / "var" / "observability.sqlite3"
    assert isinstance(bridge.dispatcher, Dispatcher)
    assert bridge.dispatcher.ledger.path == root / "var" / "control-plane.sqlite3"
    assert isinstance(bridge.dispatcher.kanban, HermesKanbanCLI)
    assert bridge.dispatcher.kanban._observability is bridge.sink


def test_runtime_mcp_derives_ledger_beside_injected_observability_db(tmp_path: Path) -> None:
    root = runtime_root(tmp_path)
    observability_path = tmp_path / "events.db"

    bridge = build_bridge(root=root, db_path=observability_path)

    assert bridge.sink.path == observability_path
    assert bridge.dispatcher is not None
    assert bridge.dispatcher.ledger.path == tmp_path / "control-plane.sqlite3"
    assert not (root / "var").exists()
