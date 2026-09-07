"""Injectable Hermes Kanban adapter using the verified native CLI contract.

The adapter contains no gateway client and is safe to exercise with a recording
runner in tests.  Production wiring can inject a runner around ``hermes kanban``.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from hermes_harness.observability import ObservabilitySink, emit_job_observation


@dataclass(frozen=True)
class KanbanTask:
    task_id: str
    title: str
    body: str
    assignee: str
    idempotency_key: str
    parent_task_ids: tuple[str, ...] = ()
    initial_status: str = "todo"
    skills: tuple[str, ...] = ()
    model: str | None = None
    provider: str | None = None
    workspace: str | None = None
    project: str | None = None
    goal: bool = False


class KanbanAdapter(Protocol):
    def create_task(self, task: KanbanTask) -> str: ...

    def show(self, task_id: str) -> Mapping[str, object]: ...

    def heartbeat(self, task_id: str) -> None: ...

    def comment(self, task_id: str, message: str) -> None: ...

    def complete(self, task_id: str, result: Mapping[str, object]) -> None: ...

    def block(self, task_id: str, reason: str) -> None: ...


Runner = Callable[[Sequence[str]], str]


class HermesKanbanCLI:
    """Small command adapter; all side effects are behind the injected runner."""

    def __init__(
        self,
        runner: Runner | None = None,
        observability: ObservabilitySink | None = None,
    ) -> None:
        self._runner = runner or self._run
        self._observability = observability

    @staticmethod
    def _run(argv: Sequence[str]) -> str:
        completed = subprocess.run(argv, check=True, capture_output=True, text=True)
        return completed.stdout.strip()

    def _call(self, *args: str) -> str:
        return self._runner(("hermes", "kanban", *args))

    def create_task(self, task: KanbanTask) -> str:
        args = [
            "create",
            task.title,
            "--body",
            task.body,
            "--assignee",
            task.assignee,
        ]
        for parent_task_id in task.parent_task_ids:
            args.extend(("--parent", parent_task_id))
        args.extend(("--idempotency-key", task.idempotency_key))
        args.extend(("--initial-status", task.initial_status))
        for skill in task.skills:
            args.extend(("--skill", skill))
        if task.model is not None:
            args.extend(("--model", task.model))
        if task.provider is not None:
            args.extend(("--provider", task.provider))
        if task.workspace is not None:
            args.extend(("--workspace", task.workspace))
        if task.project is not None:
            args.extend(("--project", task.project))
        if task.goal:
            args.append("--goal")
        output = self._call(*args, "--json")
        task_id = self._task_id_from_output(output)
        snapshot = self.show(task_id)
        self._validate_created_task(snapshot, task, task_id)
        emit_job_observation(
            self._observability,
            job_id=task_id,
            event_type="kanban.task_created",
            component="kanban",
            phase="dispatch",
            status="success",
            summary="Kanban task created",
            metadata={"profile": task.assignee},
        )
        return task_id

    def show(self, task_id: str) -> Mapping[str, object]:
        output = self._call("show", task_id, "--json")
        try:
            decoded = json.loads(output)
        except json.JSONDecodeError as exc:
            raise ValueError("Hermes Kanban show did not return JSON") from exc
        if not isinstance(decoded, Mapping):
            raise ValueError("Hermes Kanban show did not return an object")
        task = decoded.get("task")
        task_object = task if isinstance(task, Mapping) else decoded
        returned_id = task_object.get("id")
        if not isinstance(returned_id, str) or returned_id != task_id:
            raise ValueError("Hermes Kanban show returned a different task id")
        return decoded

    @staticmethod
    def _validate_created_task(
        snapshot: Mapping[str, object], task: KanbanTask, task_id: str
    ) -> None:
        """Verify the native read-back before acknowledging task creation."""
        native = snapshot.get("task")
        native_task = native if isinstance(native, Mapping) else snapshot
        if native_task.get("id") != task_id:
            raise ValueError("Hermes Kanban read-back returned a different task id")
        for field in ("title", "body", "assignee"):
            expected = getattr(task, field)
            actual = native_task.get(field)
            if actual != expected:
                raise ValueError(f"Hermes Kanban read-back mismatch for {field}")
        status = native_task.get("status")
        if not isinstance(status, str) or not status:
            raise ValueError("Hermes Kanban read-back did not include a task status")
        parents = snapshot.get("parents")
        if parents is None:
            return
        if isinstance(parents, (str, bytes)) or not isinstance(parents, Sequence):
            raise ValueError("Hermes Kanban read-back did not include valid parents")
        actual_parents = tuple(parent for parent in parents if isinstance(parent, str))
        if len(actual_parents) != len(parents) or actual_parents != task.parent_task_ids:
            raise ValueError("Hermes Kanban read-back mismatch for parents")

    @staticmethod
    def _task_id_from_output(output: str) -> str:
        decoded: object
        try:
            decoded = json.loads(output)
        except json.JSONDecodeError:
            decoded = None
        fallback_task_id = output.rsplit(maxsplit=1)[-1] if output.split() else ""
        if isinstance(decoded, Mapping):
            candidate: object = decoded.get("id")
            task_id = candidate.strip() if isinstance(candidate, str) else fallback_task_id
        else:
            task_id = fallback_task_id
        if not task_id:
            raise ValueError("Hermes Kanban did not return a task id")
        return task_id

    def heartbeat(self, task_id: str) -> None:
        self._call("heartbeat", task_id)
        emit_job_observation(
            self._observability,
            job_id=task_id,
            event_type="kanban.heartbeat",
            component="kanban",
            phase="worker",
            status="success",
            summary="Kanban heartbeat recorded",
        )

    def comment(self, task_id: str, message: str) -> None:
        self._call("comment", task_id, message)
        emit_job_observation(
            self._observability,
            job_id=task_id,
            event_type="kanban.comment",
            component="kanban",
            phase="worker",
            status="success",
            summary="Kanban checkpoint recorded",
        )

    def complete(self, task_id: str, result: Mapping[str, object]) -> None:
        self._call("complete", task_id, "--result", json.dumps(dict(result), sort_keys=True))
        emit_job_observation(
            self._observability,
            job_id=task_id,
            event_type="kanban.completed",
            component="kanban",
            phase="worker",
            status="success",
            summary="Kanban task completed",
        )

    def block(self, task_id: str, reason: str) -> None:
        self._call("block", task_id, reason)
        emit_job_observation(
            self._observability,
            job_id=task_id,
            event_type="kanban.blocked",
            component="kanban",
            phase="worker",
            status="blocked",
            summary="Kanban task blocked",
        )


HEARTBEAT_SECONDS = 60
STALE_SECONDS = 300
