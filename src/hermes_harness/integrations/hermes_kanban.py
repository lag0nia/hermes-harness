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

    def __init__(self, runner: Runner | None = None) -> None:
        self._runner = runner or self._run

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
        return output.rsplit(maxsplit=1)[-1]

    def heartbeat(self, task_id: str) -> None:
        self._call("heartbeat", task_id)

    def comment(self, task_id: str, message: str) -> None:
        self._call("comment", task_id, message)

    def complete(self, task_id: str, result: Mapping[str, object]) -> None:
        self._call("complete", task_id, "--result", json.dumps(dict(result), sort_keys=True))

    def block(self, task_id: str, reason: str) -> None:
        self._call("block", task_id, "--reason", reason)


HEARTBEAT_SECONDS = 60
STALE_SECONDS = 300
