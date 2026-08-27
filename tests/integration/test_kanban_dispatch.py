from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from hermes_harness.control_plane.contracts import Effort, IntentEnvelope, ModelPolicy, RiskClass
from hermes_harness.control_plane.ledger import Ledger
from hermes_harness.dispatcher import Dispatcher
from hermes_harness.integrations.hermes_kanban import KanbanTask


def make_envelope(intent: str = "technical.research") -> IntentEnvelope:
    return IntentEnvelope(
        schema_version="1.0.0",
        job_id=uuid4(),
        trace_id=uuid4(),
        origin_profile="default",
        origin_session="telegram:42",
        delivery_target="telegram:42",
        intent=intent,
        idempotency_key=str(uuid4()),
        risk_class=RiskClass.LOW,
        model_policy=ModelPolicy(
            provider="openai-codex", model="gpt-5.6-luna", effort=Effort.MEDIUM
        ),
        context_references=[],
        parameters={"question": "kanban"},
        source_text="investiga kanban",
    )


class RecordingKanban:
    def __init__(self) -> None:
        self.created: list[KanbanTask] = []
        self.heartbeats: list[str] = []

    def create_task(self, task: KanbanTask) -> str:
        self.created.append(task)
        return "task-abc123"

    def heartbeat(self, task_id: str) -> None:
        self.heartbeats.append(task_id)

    def comment(self, task_id: str, message: str) -> None:
        pass

    def complete(self, task_id: str, result: dict[str, object]) -> None:
        pass

    def block(self, task_id: str, reason: str) -> None:
        pass


def test_dispatches_specialist_to_exact_profile_with_native_effort_and_cp_reference(
    tmp_path: Path,
) -> None:
    ledger = Ledger(tmp_path / "ledger.db")
    envelope = make_envelope()
    job = ledger.create_job(envelope)
    adapter = RecordingKanban()
    result = Dispatcher(ledger=ledger, kanban=adapter).dispatch(envelope)
    assert result.kanban_task_id == "task-abc123"
    assert adapter.created == [
        KanbanTask(
            "",
            "technical.research",
            "investiga kanban",
            "researcher",
            "medium",
            {"job_id": str(job.job_id), "trace_id": str(envelope.trace_id)},
        )
    ]
    assert ledger.get_job(job.job_id).kanban_task_id == "task-abc123"
    assert ledger.events(job.job_id)[-1].event_type == "kanban_attached"


def test_direct_calendar_operation_does_not_use_kanban(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.db")
    envelope = make_envelope("calendar.create_event")
    ledger.create_job(envelope)
    adapter = RecordingKanban()
    result = Dispatcher(ledger=ledger, kanban=adapter).dispatch(envelope)
    assert result.kanban_task_id is None
    assert adapter.created == []


def test_worker_activity_uses_native_heartbeat_and_translates_need_input_and_completion(
    tmp_path: Path,
) -> None:
    ledger = Ledger(tmp_path / "ledger.db")
    envelope = make_envelope()
    ledger.create_job(envelope)
    adapter = RecordingKanban()
    dispatcher = Dispatcher(ledger=ledger, kanban=adapter)
    dispatcher.dispatch(envelope)
    dispatcher.heartbeat(envelope.job_id)
    need_input = dispatcher.translate_event(
        envelope, {"type": "need_input", "message": "falta una fecha", "payload": {"field": "date"}}
    )
    completed = dispatcher.translate_event(
        envelope, {"type": "complete", "message": "terminado", "payload": {"answer": "ok"}}
    )
    assert adapter.heartbeats == ["task-abc123"]
    assert need_input.event_type == "state" and need_input.state == "WAITING_INPUT"
    assert completed.event_type == "state" and completed.state == "SUCCEEDED"
    assert (completed.sequence, need_input.sequence) == (1, 0)


def test_cli_adapter_emits_verified_hermes_kanban_commands_without_gateway_access() -> None:
    calls: list[tuple[str, ...]] = []

    def runner(argv: tuple[str, ...]) -> str:
        calls.append(argv)
        return "created task-cli"

    from hermes_harness.integrations.hermes_kanban import HermesKanbanCLI

    adapter = HermesKanbanCLI(runner=runner)
    task_id = adapter.create_task(
        KanbanTask("", "title", "prompt", "researcher", "high", {"job": "1"})
    )
    adapter.heartbeat(task_id)
    adapter.comment(task_id, "checkpoint")
    adapter.complete(task_id, {"status": "ok"})
    adapter.block(task_id, "NEED_INPUT")
    assert calls[0][:4] == ("hermes", "kanban", "create", "--title")
    assert "--profile" in calls[0] and "researcher" in calls[0]
    assert "--reasoning-effort" in calls[0] and "high" in calls[0]
    assert calls[1] == ("hermes", "kanban", "heartbeat", "task-cli")
    assert calls[-1] == ("hermes", "kanban", "block", "task-cli", "--reason", "NEED_INPUT")
