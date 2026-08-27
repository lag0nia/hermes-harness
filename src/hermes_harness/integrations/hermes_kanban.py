"""Injectable Hermes Kanban adapter using the verified native CLI contract.

The adapter contains no gateway client and is safe to exercise with a recording
runner in tests.  Production wiring can inject a runner around ``hermes kanban``.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from hermes_harness.observability import ObservabilitySink, emit_job_observation


@dataclass(frozen=True)
class KanbanTask:
    task_id: str
    title: str
    prompt: str
    profile: str
    reasoning_effort: str
    metadata: Mapping[str, str] = field(default_factory=dict)


class KanbanAdapter(Protocol):
    def create_task(self, task: KanbanTask) -> str: ...

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
        # ``--reasoning-effort`` is Hermes Kanban's native per-task override.
        output = self._call(
            "create",
            "--title",
            task.title,
            "--prompt",
            task.prompt,
            "--profile",
            task.profile,
            "--reasoning-effort",
            task.reasoning_effort,
            "--metadata",
            json.dumps(dict(task.metadata), sort_keys=True),
        )
        task_id = output.rsplit(maxsplit=1)[-1]
        emit_job_observation(
            self._observability,
            job_id=task_id,
            event_type="kanban.task_created",
            component="kanban",
            phase="dispatch",
            status="success",
            summary="Kanban task created",
            metadata={"profile": task.profile},
        )
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
        self._call("block", task_id, "--reason", reason)
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
