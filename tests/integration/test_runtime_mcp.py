from pathlib import Path

from hermes_harness.mcp_server import create_server
from hermes_harness.runtime_mcp import build_bridge


def test_runtime_mcp_bridge_loads_real_routing_and_tools(tmp_path: Path):
    server = create_server(build_bridge(db_path=tmp_path / "events.db"))
    assert set(server._tool_manager._tools) == {
        "harness_plan_intent",
        "harness_submit_read_only",
        "harness_submit",
        "harness_job_status",
        "harness_trace_context",
    }
