"""Control-plane dispatcher for specialist work on the Kanban execution bus."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from hermes_harness.control_plane.contracts import (
    AgentEvent,
    IntentEnvelope,
    ProgressEvent,
    StateEvent,
)
from hermes_harness.control_plane.ledger import JobRecord, JobState, Ledger
from hermes_harness.integrations.hermes_kanban import (
    HEARTBEAT_SECONDS,
    STALE_SECONDS,
    KanbanAdapter,
    KanbanTask,
)

DIRECT_INTENTS = frozenset(
    {
        "calendar.create_vtodo",
        "calendar.create_event",
        "calendar.update",
        "calendar.delete",
        "calendar.list",
        "pi.health.read",
        "pi.jobs.list",
        "pi.jobs.cancel",
        "general.answer",
        "general.clarify",
    }
)
PROFILE_BY_INTENT = {
    "browser.research": "browser-operator",
    "browser.order.prepare": "browser-operator",
    "browser.form.prepare": "browser-operator",
    "browser.auth_required": "browser-operator",
    "travel.plan": "travel-planner",
    "travel.search_flights": "travel-planner",
    "travel.search_stays": "travel-planner",
    "technical.research": "researcher",
    "technical.plan": "architect-planner",
    "technical.change": "engineer",
    "technical.review": "engineer",
    "code.plan": "coder",
    "code.change": "coder",
    "code.review": "coder",
    "docs.reconcile": "documentator",
    "docs.query": "documentator",
}


@dataclass(frozen=True)
class DispatchResult:
    job_id: UUID
    kanban_task_id: str | None
    direct: bool


class Dispatcher:
    def __init__(self, *, ledger: Ledger, kanban: KanbanAdapter) -> None:
        self.ledger = ledger
        self.kanban = kanban
        self._sequences: dict[UUID, int] = {}
        self._last_activity: dict[UUID, datetime] = {}

    def dispatch(self, envelope: IntentEnvelope) -> DispatchResult:
        try:
            job = self.ledger.get_job(envelope.job_id)
        except KeyError:
            job = self.ledger.create_job(envelope)
        profile = PROFILE_BY_INTENT.get(envelope.intent.value)
        if profile is None:
            if envelope.intent.value not in DIRECT_INTENTS:
                raise ValueError(f"no Kanban route for intent: {envelope.intent.value}")
            return DispatchResult(job.job_id, None, True)
        if job.kanban_task_id:
            return DispatchResult(job.job_id, job.kanban_task_id, False)
        task_id = self.kanban.create_task(
            KanbanTask(
                task_id="",
                title=envelope.intent.value,
                prompt=envelope.source_text,
                profile=profile,
                reasoning_effort=envelope.model_policy.effort.value,
                metadata={"job_id": str(job.job_id), "trace_id": str(envelope.trace_id)},
            )
        )
        self._store_task_id(job.job_id, task_id)
        self._last_activity[job.job_id] = datetime.now(UTC)
        return DispatchResult(job.job_id, task_id, False)

    def heartbeat(self, job_id: UUID) -> None:
        task_id = self.ledger.get_job(job_id).kanban_task_id
        if task_id:
            self.kanban.heartbeat(task_id)
            self._last_activity[job_id] = datetime.now(UTC)

    def checkpoint(
        self, job_id: UUID, message: str, payload: Mapping[str, Any] | None = None
    ) -> None:
        task_id = self.ledger.get_job(job_id).kanban_task_id
        if task_id:
            self.kanban.comment(task_id, message)

    def cancel(self, job_id: UUID) -> None:
        task_id = self.ledger.get_job(job_id).kanban_task_id
        if task_id:
            self.kanban.block(task_id, "CANCELLED_BY_USER")

    def need_input(self, job_id: UUID, prompt: str) -> None:
        task_id = self.ledger.get_job(job_id).kanban_task_id
        if task_id:
            self.kanban.block(task_id, f"NEED_INPUT: {prompt}")

    def reclaim_stale(self, jobs: list[JobRecord], *, now: datetime | None = None) -> list[UUID]:
        """Identify running workers with no activity for the stale threshold."""
        observed_at = now or datetime.now(UTC)
        return [
            job.job_id
            for job in jobs
            if job.state is JobState.RUNNING
            and job.job_id in self._last_activity
            and (observed_at - self._last_activity[job.job_id]).total_seconds() >= STALE_SECONDS
        ]

    def translate_event(self, envelope: IntentEnvelope, event: Mapping[str, Any]) -> AgentEvent:
        job_id = envelope.job_id
        sequence = self._sequences.get(job_id, 0)
        self._sequences[job_id] = sequence + 1
        event_type = str(event.get("type", "progress"))
        payload = dict(event.get("payload", {}))
        message = str(event.get("message", event_type))
        common: dict[str, Any] = dict(
            schema_version="1.0.0",
            job_id=job_id,
            trace_id=envelope.trace_id,
            origin_profile=envelope.origin_profile,
            origin_session=envelope.origin_session,
            delivery_target=envelope.delivery_target,
            intent=envelope.intent,
            idempotency_key=envelope.idempotency_key,
            risk_class=envelope.risk_class,
            model_policy=envelope.model_policy,
            context_references=envelope.context_references,
            sequence=sequence,
            occurred_at=datetime.now(UTC),
            message=message,
            payload=payload,
        )
        if event_type in {"complete", "completed", "success"}:
            return StateEvent(**common, event_type="state", state=JobState.SUCCEEDED.value)
        if event_type in {"block", "blocked", "need_input", "checkpoint", "cancelled"}:
            state = {
                "block": "BLOCKED",
                "blocked": "BLOCKED",
                "need_input": "WAITING_INPUT",
                "checkpoint": "RUNNING",
                "cancelled": "CANCELLED",
            }[event_type]
            return StateEvent(**common, event_type="state", state=state)
        return ProgressEvent(**common, event_type="progress")

    def _store_task_id(self, job_id: UUID, task_id: str) -> None:
        self.ledger.attach_kanban_task(job_id, task_id)


__all__ = ["HEARTBEAT_SECONDS", "STALE_SECONDS", "DispatchResult", "Dispatcher"]
