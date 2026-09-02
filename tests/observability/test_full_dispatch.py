from __future__ import annotations

from dataclasses import asdict
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
from hermes_harness.observability_bridge import ObservabilityBridge

ROOT = Path(__file__).resolve().parents[2]


class RecordingKanban:
    def __init__(self) -> None:
        self.created: list[KanbanTask] = []

    def create_task(self, task: KanbanTask) -> str:
        self.created.append(task)
        return f"task-{len(self.created)}"

    def heartbeat(self, task_id: str) -> None:
        pass

    def comment(self, task_id: str, message: str) -> None:
        pass

    def complete(self, task_id: str, result: dict[str, object]) -> None:
        pass

    def block(self, task_id: str, reason: str) -> None:
        pass


def make_envelope(intent: Intent, *, origin_profile: str) -> IntentEnvelope:
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
        parameters={},
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


def test_submit_full_delegates_technical_research_to_recording_kanban(tmp_path: Path) -> None:
    adapter = RecordingKanban()
    bridge = make_bridge(tmp_path, adapter)
    envelope = make_envelope(Intent.TECHNICAL_RESEARCH, origin_profile="researcher")

    result = bridge.submit_full(envelope)

    assert result.allowed is True
    assert result.dispatch is not None
    assert result.dispatch.job_id == envelope.job_id
    assert result.dispatch.direct is False
    assert result.dispatch.kanban_task_id == "task-1"
    assert [task.assignee for task in adapter.created] == ["researcher"]


def test_submit_full_keeps_calendar_create_event_direct_without_kanban(tmp_path: Path) -> None:
    adapter = RecordingKanban()
    bridge = make_bridge(tmp_path, adapter)
    envelope = make_envelope(Intent.CALENDAR_CREATE_EVENT, origin_profile="default")

    result = bridge.submit_full(envelope)

    assert result.allowed is True
    assert result.dispatch is not None
    assert result.dispatch.job_id == envelope.job_id
    assert result.dispatch.direct is True
    assert result.dispatch.kanban_task_id is None
    assert adapter.created == []


def test_submit_full_coordinates_idempotent_development_kanban_chain(tmp_path: Path) -> None:
    adapter = RecordingKanban()
    bridge = make_bridge(tmp_path, adapter)
    envelope = make_envelope(Intent.DEVELOPMENT_COORDINATE, origin_profile="default")

    first = bridge.submit_full(envelope)
    second = bridge.submit_full(envelope)

    assert first.dispatch is not None
    assert second.dispatch == first.dispatch
    assert first.dispatch.job_id == envelope.job_id
    assert first.dispatch.direct is False
    assert first.dispatch.kanban_task_id is None
    assert [(child.job_id, child.kanban_task_id) for child in first.dispatch.children] == [
        (child.job_id, f"task-{index}")
        for index, child in enumerate(first.dispatch.children, start=1)
    ]
    assert [task.title for task in adapter.created] == [
        "technical.research",
        "technical.plan",
        "technical.change",
    ]
    assert [task.assignee for task in adapter.created] == [
        "researcher",
        "architect-planner",
        "engineer",
    ]
    assert [task.parent_task_ids for task in adapter.created] == [(), ("task-1",), ("task-2",)]
    assert [task.idempotency_key for task in adapter.created] == [
        f"{envelope.idempotency_key}:research",
        f"{envelope.idempotency_key}:plan",
        f"{envelope.idempotency_key}:change",
    ]
    assert len(adapter.created) == 3
    assert envelope.source_text not in str(asdict(first.dispatch))


def test_harness_submit_returns_plan_and_dispatch_without_source_text(tmp_path: Path) -> None:
    adapter = RecordingKanban()
    server = create_server(make_bridge(tmp_path, adapter))
    envelope = make_envelope(Intent.TECHNICAL_RESEARCH, origin_profile="researcher")

    response = server._tool_manager._tools["harness_submit"].fn(
        envelope.model_dump(mode="json")
    )

    assert response["ok"] is True
    assert response["plan"]["job_id"] == str(envelope.job_id)
    assert response["dispatch"] == {
        "job_id": str(envelope.job_id),
        "direct": False,
        "kanban_task_id": "task-1",
        "children": [],
    }
    assert envelope.source_text not in str(response)
    assert [task.assignee for task in adapter.created] == ["researcher"]
