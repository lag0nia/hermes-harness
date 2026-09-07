from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from uuid import uuid4

from hermes_harness.control_plane.contracts import (
    Effort,
    Intent,
    IntentEnvelope,
    ModelPolicy,
    RiskClass,
)
from hermes_harness.control_plane.ledger import Ledger
from hermes_harness.control_plane.policy import PolicyEngine
from hermes_harness.control_plane.router import Router
from hermes_harness.dispatcher import Dispatcher
from hermes_harness.integrations.hermes_kanban import KanbanTask
from hermes_harness.mcp_server import create_server
from hermes_harness.observability import SQLiteObservabilitySink
from hermes_harness.observability_bridge import BridgeDenied, ObservabilityBridge

ROOT = Path(__file__).resolve().parents[2]


class RecordingKanban:
    def __init__(self) -> None:
        self.created: list[KanbanTask] = []

    def create_task(self, task: KanbanTask) -> str:
        self.created.append(task)
        return f"task-{len(self.created)}"

    def show(self, task_id: str) -> dict[str, object]:
        return {"id": task_id, "status": "todo"}

    def heartbeat(self, task_id: str) -> None:
        pass

    def comment(self, task_id: str, message: str) -> None:
        pass

    def complete(self, task_id: str, result: Mapping[str, object]) -> None:
        pass

    def block(self, task_id: str, reason: str) -> None:
        pass


def make_envelope(
    intent: Intent, *, origin_profile: str, delegation_profile: str | None = None
) -> IntentEnvelope:
    return IntentEnvelope(
        schema_version="1.0.0",
        job_id=uuid4(),
        trace_id=uuid4(),
        origin_profile=origin_profile,
        origin_session="test-session",
        delivery_target="cli",
        intent=intent,
        idempotency_key=str(uuid4()),
        risk_class=RiskClass.LOW,
        model_policy=ModelPolicy(
            provider="openai-codex",
            model="gpt-5.6-luna",
            effort=Effort.MEDIUM,
        ),
        context_references=[],
        parameters=(
            {"delegation_profile": delegation_profile}
            if delegation_profile is not None
            else {}
        ),
        source_text="Research the harness dispatch boundary.",
    )


def make_bridge(tmp_path: Path, adapter: RecordingKanban) -> ObservabilityBridge:
    sink = SQLiteObservabilitySink(tmp_path / "events.db")
    dispatcher = Dispatcher(ledger=Ledger(tmp_path / "ledger.db"), kanban=adapter)
    return ObservabilityBridge(
        Router.from_files(ROOT / "config" / "routing.yaml", ROOT / "capabilities" / "agents"),
        PolicyEngine.from_directory(ROOT / "config"),
        sink,
        dispatcher=dispatcher,
    )


def test_submit_full_rejects_specialist_delegation_until_confirmation_is_wired(
    tmp_path: Path,
) -> None:
    adapter = RecordingKanban()
    bridge = make_bridge(tmp_path, adapter)
    envelope = make_envelope(
        Intent.TECHNICAL_RESEARCH,
        origin_profile="researcher",
        delegation_profile="researcher",
    )

    with __import__("pytest").raises(BridgeDenied, match="disabled"):
        bridge.submit_full(envelope)

    assert adapter.created == []


def test_submit_full_rejects_calendar_create_event_until_confirmation_is_wired(
    tmp_path: Path,
) -> None:
    adapter = RecordingKanban()
    bridge = make_bridge(tmp_path, adapter)
    envelope = make_envelope(Intent.CALENDAR_CREATE_EVENT, origin_profile="default")

    with __import__("pytest").raises(BridgeDenied, match="disabled"):
        bridge.submit_full(envelope)

    assert adapter.created == []


def test_submit_full_rejects_development_workflow_until_confirmation_is_wired(
    tmp_path: Path,
) -> None:
    adapter = RecordingKanban()
    bridge = make_bridge(tmp_path, adapter)
    envelope = make_envelope(Intent.DEVELOPMENT_COORDINATE, origin_profile="default")

    with __import__("pytest").raises(BridgeDenied, match="disabled"):
        bridge.submit_full(envelope)

    assert adapter.created == []


def test_harness_submit_is_not_exposed_before_full_submission_is_safe(tmp_path: Path) -> None:
    adapter = RecordingKanban()
    server = create_server(make_bridge(tmp_path, adapter))

    assert "harness_submit" not in server._tool_manager._tools
    assert adapter.created == []
