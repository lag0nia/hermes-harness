from __future__ import annotations

import json
from collections.abc import Sequence

import pytest

from hermes_harness.integrations.hermes_kanban import (
    HermesKanbanCLI,
    KanbanTask,
)

TASK = KanbanTask(
    task_id="",
    title="technical.research",
    body="investiga",
    assignee="researcher",
    idempotency_key="job-1",
    parent_task_ids=("parent-1",),
)


def test_create_rejects_native_readback_title_mismatch() -> None:
    def runner(argv: Sequence[str]) -> str:
        if argv[2] == "create":
            return json.dumps({"id": "task-1"})
        return json.dumps(
            {
                "task": {
                    "id": "task-1",
                    "title": "different",
                    "body": TASK.body,
                    "assignee": TASK.assignee,
                    "status": "todo",
                },
                "parents": ["parent-1"],
            }
        )

    with pytest.raises(ValueError, match="title"):
        HermesKanbanCLI(runner=runner).create_task(TASK)


def test_create_rejects_native_readback_parent_mismatch() -> None:
    def runner(argv: Sequence[str]) -> str:
        if argv[2] == "create":
            return json.dumps({"id": "task-1"})
        return json.dumps(
            {
                "task": {
                    "id": "task-1",
                    "title": TASK.title,
                    "body": TASK.body,
                    "assignee": TASK.assignee,
                    "status": "todo",
                },
                "parents": ["other-parent"],
            }
        )

    with pytest.raises(ValueError, match="parents"):
        HermesKanbanCLI(runner=runner).create_task(TASK)


def test_show_rejects_another_native_task_id() -> None:
    def runner(_: Sequence[str]) -> str:
        return json.dumps(
            {
                "task": {
                    "id": "task-elsewhere",
                    "title": TASK.title,
                    "body": TASK.body,
                    "assignee": TASK.assignee,
                    "status": "todo",
                }
            }
        )

    with pytest.raises(ValueError, match="different task id"):
        HermesKanbanCLI(runner=runner).show("task-1")
