"""Side-effect-free risk-based technical change planning and gate execution."""

from __future__ import annotations

import posixpath
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class RiskLevel(StrEnum):
    R0 = "R0"
    R1 = "R1"
    R2 = "R2"


class Owner(StrEnum):
    ENGINEER = "Engineer"
    CODER = "Coder"


class Stage(StrEnum):
    RESEARCH = "research"
    ARCHITECT = "architect"
    IMPLEMENT = "implement"
    TEST = "test"
    SOL_REVIEW = "sol_review"
    REPLAY = "replay"
    CHECKPOINT = "checkpoint"
    CHANGE_EVENT = "change_event"
    DOCUMENT = "document"


class GateFailure(RuntimeError):
    """A promotion gate failed; no external side effect was performed."""


@dataclass(frozen=True)
class ChangeRequest:
    description: str
    risk: RiskLevel
    project: str
    critical: bool = False
    changed_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class PipelinePlan:
    owner: Owner
    stages: tuple[Stage, ...]
    metadata: dict[str, str]
    sol_effort: str | None = None


@dataclass(frozen=True)
class PipelineResult(PipelinePlan):
    status: str = "promoted"


class ChangePipeline:
    def __init__(
        self,
        *,
        run_tests: Callable[[ChangeRequest], bool],
        health_check: Callable[[ChangeRequest], bool],
        rollback_ready: Callable[[ChangeRequest], bool],
        sol_review: Callable[[ChangeRequest], bool] | None = None,
        replay: Callable[[ChangeRequest], bool] | None = None,
    ) -> None:
        self.run_tests = run_tests
        self.health_check = health_check
        self.rollback_ready = rollback_ready
        self.sol_review = sol_review
        self.replay = replay

    @staticmethod
    def _owner(request: ChangeRequest) -> Owner:
        return (
            Owner.ENGINEER
            if request.project.casefold() in {"harness", "hermes", "core"}
            else Owner.CODER
        )

    def plan(self, request: ChangeRequest) -> PipelinePlan:
        owner = self._owner(request)
        stages: list[Stage] = []
        if request.risk is RiskLevel.R1:
            stages.append(Stage.ARCHITECT)
        elif request.risk is RiskLevel.R2:
            stages.extend((Stage.RESEARCH, Stage.ARCHITECT))
        stages.extend((Stage.IMPLEMENT, Stage.TEST))
        if request.risk is RiskLevel.R2:
            stages.extend((Stage.SOL_REVIEW, Stage.REPLAY, Stage.CHECKPOINT))
        stages.extend((Stage.CHANGE_EVENT, Stage.DOCUMENT))
        return PipelinePlan(
            owner,
            tuple(stages),
            {"worktree": f"wt/{owner.value.lower()}-change", "patch_queue": "pending"},
            "medium" if request.risk is RiskLevel.R2 else None,
        )

    def execute(self, request: ChangeRequest, *, confirmed: bool = False) -> PipelineResult:
        plan = self.plan(request)
        for path in request.changed_paths:
            self.validate_path(plan.owner, path)
        needs_confirmation = request.critical or request.risk is RiskLevel.R2
        if needs_confirmation and not confirmed:
            return PipelineResult(
                plan.owner, plan.stages, plan.metadata, plan.sol_effort, "waiting_confirmation"
            )
        if not self.run_tests(request):
            raise GateFailure("tests gate failed")
        if request.risk is RiskLevel.R2:
            if self.sol_review is None or not self.sol_review(request):
                raise GateFailure("Sol review gate failed")
            if self.replay is None or not self.replay(request):
                raise GateFailure("replay gate failed")
        if not self.health_check(request):
            raise GateFailure("health gate failed")
        if not self.rollback_ready(request):
            raise GateFailure("rollback readiness gate failed")
        metadata = {**plan.metadata, "patch_queue": "ready", "checkpoint": "created"}
        return PipelineResult(plan.owner, plan.stages, metadata, plan.sol_effort, "promoted")

    @staticmethod
    def validate_path(owner: Owner, path: str) -> None:
        normalized = posixpath.normpath(path.replace("\\", "/"))
        if (
            normalized == ".."
            or normalized.startswith("../")
            or normalized.startswith("/")
            or re.match(r"^[A-Za-z]:/", normalized)
        ):
            raise PermissionError("path escapes the project boundary")
        if owner is Owner.CODER and (
            normalized.startswith(("src/hermes_harness/", "profiles/", "config/"))
            or normalized in {"pyproject.toml", "uv.lock"}
        ):
            raise PermissionError("Coder cannot modify Hermes/profile/config paths")
