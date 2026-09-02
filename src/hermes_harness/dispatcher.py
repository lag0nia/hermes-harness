"""Control-plane dispatcher for specialist work on the Kanban execution bus."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid5

from hermes_harness.control_plane.contracts import (
    AgentEvent,
    Intent,
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
from hermes_harness.observability import ObservabilitySink, emit_observation

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
    children: tuple[DevelopmentWorkflowStep, ...] = ()


@dataclass(frozen=True)
class DevelopmentWorkflowStep:
    envelope: IntentEnvelope
    kanban_task_id: str


@dataclass(frozen=True)
class DevelopmentWorkflowResult:
    parent_job_id: UUID
    steps: tuple[DevelopmentWorkflowStep, ...]


DEVELOPMENT_WORKFLOW: tuple[tuple[str, Intent, str], ...] = (
    ("research", Intent.TECHNICAL_RESEARCH, "researcher"),
    ("plan", Intent.TECHNICAL_PLAN, "architect-planner"),
    ("change", Intent.TECHNICAL_CHANGE, "engineer"),
)


class Dispatcher:
    def __init__(
        self,
        *,
        ledger: Ledger,
        kanban: KanbanAdapter,
        observability: ObservabilitySink | None = None,
    ) -> None:
        self.ledger = ledger
        self.kanban = kanban
        self._observability = observability
        self._sequences: dict[UUID, int] = {}
        self._last_activity: dict[UUID, datetime] = {}

    def dispatch(self, envelope: IntentEnvelope) -> DispatchResult:
        if envelope.intent is Intent.DEVELOPMENT_COORDINATE:
            workflow = self.coordinate_development(envelope)
            return DispatchResult(
                job_id=workflow.parent_job_id,
                kanban_task_id=None,
                direct=False,
                children=workflow.steps,
            )
        job = self._ensure_job(envelope)
        profile = PROFILE_BY_INTENT.get(envelope.intent.value)
        if profile is None:
            if envelope.intent.value not in DIRECT_INTENTS:
                raise ValueError(f"no Kanban route for intent: {envelope.intent.value}")
            emit_observation(
                self._observability,
                trace_id=envelope.trace_id,
                job_id=job.job_id,
                session_id=envelope.origin_session,
                profile=envelope.origin_profile,
                event_type="dispatcher.direct",
                component="dispatcher",
                phase="dispatch",
                status="success",
                summary=f"Direct intent dispatched: {envelope.intent.value}",
                metadata={"intent": envelope.intent.value},
            )
            return DispatchResult(job.job_id, None, True)
        if job.kanban_task_id:
            return DispatchResult(job.job_id, job.kanban_task_id, False)
        task_id = self.kanban.create_task(
            KanbanTask(
                task_id="",
                title=envelope.intent.value,
                body=envelope.source_text,
                assignee=profile,
                idempotency_key=envelope.idempotency_key,
                model=envelope.model_policy.model,
                provider=envelope.model_policy.provider,
            )
        )
        self._store_task_id(job.job_id, task_id)
        self._last_activity[job.job_id] = datetime.now(UTC)
        emit_observation(
            self._observability,
            trace_id=envelope.trace_id,
            job_id=job.job_id,
            session_id=envelope.origin_session,
            profile=envelope.origin_profile,
            event_type="dispatcher.delegated",
            component="dispatcher",
            phase="dispatch",
            status="success",
            summary=f"Delegated intent: {envelope.intent.value}",
            metadata={"intent": envelope.intent.value, "worker_profile": profile},
        )
        return DispatchResult(job.job_id, task_id, False)

    def coordinate_development(self, envelope: IntentEnvelope) -> DevelopmentWorkflowResult:
        """Create the deterministic research, plan, and implementation workflow."""
        if envelope.intent is not Intent.DEVELOPMENT_COORDINATE:
            raise ValueError("development workflow requires development.coordinate intent")

        parent = self._ensure_job(envelope)
        parent_task_id = parent.kanban_task_id
        dependency: UUID | None = None
        steps: list[DevelopmentWorkflowStep] = []
        for stage, intent, assignee in DEVELOPMENT_WORKFLOW:
            child = self._development_child_envelope(envelope, stage, intent, dependency)
            job = self._ensure_job(child)
            task_id = job.kanban_task_id
            if task_id is None:
                task_id = self.kanban.create_task(
                    KanbanTask(
                        task_id="",
                        title=child.intent.value,
                        body=child.source_text,
                        assignee=assignee,
                        idempotency_key=child.idempotency_key,
                        parent_task_ids=(parent_task_id,) if parent_task_id else (),
                        model=child.model_policy.model,
                        provider=child.model_policy.provider,
                    )
                )
                self._store_task_id(child.job_id, task_id)
                self._last_activity[child.job_id] = datetime.now(UTC)
            steps.append(DevelopmentWorkflowStep(child, task_id))
            dependency = child.job_id
            parent_task_id = task_id
        return DevelopmentWorkflowResult(envelope.job_id, tuple(steps))

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

    def _ensure_job(self, envelope: IntentEnvelope) -> JobRecord:
        try:
            return self.ledger.get_job(envelope.job_id)
        except KeyError:
            return self.ledger.create_job(envelope)

    @staticmethod
    def _development_child_envelope(
        parent: IntentEnvelope,
        stage: str,
        intent: Intent,
        dependency: UUID | None,
    ) -> IntentEnvelope:
        idempotency_key = f"{parent.idempotency_key}:{stage}"
        if len(idempotency_key) > 256:
            idempotency_key = str(
                uuid5(parent.job_id, f"development-coordinate:{stage}:idempotency")
            )
        return IntentEnvelope(
            schema_version=parent.schema_version,
            job_id=uuid5(parent.job_id, f"development-coordinate:{stage}"),
            parent_job_id=parent.job_id,
            trace_id=parent.trace_id,
            origin_profile=parent.origin_profile,
            origin_session=parent.origin_session,
            delivery_target=parent.delivery_target,
            intent=intent,
            idempotency_key=idempotency_key,
            risk_class=parent.risk_class,
            model_policy=parent.model_policy,
            context_references=list(parent.context_references),
            parameters=dict(parent.parameters),
            source_text=parent.source_text,
            dependencies=[dependency] if dependency else [],
        )


__all__ = [
    "HEARTBEAT_SECONDS",
    "STALE_SECONDS",
    "DevelopmentWorkflowResult",
    "DevelopmentWorkflowStep",
    "DispatchResult",
    "Dispatcher",
]
