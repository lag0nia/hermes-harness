from pathlib import Path

from hermes_harness.control_plane.contracts import Intent
from hermes_harness.control_plane.policy import PolicyEngine
from hermes_harness.control_plane.router import Router
from hermes_harness.mcp_server import create_server
from hermes_harness.observability import SQLiteObservabilitySink
from hermes_harness.observability_bridge import ObservabilityBridge


def make_bridge(tmp_path: Path) -> ObservabilityBridge:
    router = Router(
        {Intent.GENERAL_ANSWER: {"profile": "default", "confirmation": "none"}}, {"default": {}}
    )
    policy = PolicyEngine(
        {
            "provider": "openai-codex",
            "profiles": {"default": {"models": ["gpt-5.6-luna"], "efforts": ["high"]}},
            "sol": {"allowed_intents": []},
            "models_900k": {"allowed_profiles": [], "allowed_intents": []},
        },
        set(),
        set(),
    )
    return ObservabilityBridge(router, policy, SQLiteObservabilitySink(tmp_path / "events.db"))


def test_mcp_server_exposes_only_safe_tools(tmp_path: Path) -> None:
    server = create_server(make_bridge(tmp_path))
    assert len(server._tool_manager._tools) == 5
    assert "purge" not in server._tool_manager._tools


def test_mcp_server_has_bounded_read_only_surface(tmp_path: Path) -> None:
    server = create_server(make_bridge(tmp_path))
    assert server.name == "Hermes Control Plane Observability Bridge"
    assert set(server._tool_manager._tools) == {
        "harness_plan_intent",
        "harness_submit_read_only",
        "harness_submit",
        "harness_job_status",
        "harness_trace_context",
    }
