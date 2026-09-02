"""Idempotent installer contract for the periodic observability review cron job."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

OBSERVABILITY_REVIEW_JOB_NAME = "observability-architect-review-v1"
OBSERVABILITY_REVIEW_SCRIPT = "hermes-observability-review.py"
_RUNTIME_PIN_FIELDS = frozenset({"profile", "provider", "model", "reasoning_effort"})


@dataclass(frozen=True)
class ObservabilityJobInstall:
    job_id: str
    created: bool


def _normalize_actual_value(key: str, value: Any) -> Any:
    if (
        key == "schedule"
        and isinstance(value, Mapping)
        and value.get("kind") == "interval"
        and value.get("minutes") == 2880
    ):
        return "every 2d"
    if key == "repeat" and isinstance(value, Mapping) and value.get("times") is None:
        return None
    return value


def _spec() -> dict[str, Any]:
    # next_run_at is intentionally absent from the scheduler command contract;
    # it is computed by Hermes from the interval at creation. The installer never
    # calls cron run, so installation cannot execute the first review.
    return {
        "name": OBSERVABILITY_REVIEW_JOB_NAME,
        "schedule": "every 2d",
        "no_agent": True,
        "script": OBSERVABILITY_REVIEW_SCRIPT,
        "repeat": None,
        "profile": "architect-planner",
        "provider": "openai-codex",
        "model": "gpt-5.6-luna",
        "reasoning_effort": "medium",
        "next_run_at": None,
    }


def ensure_single_observability_review_job(
    existing_jobs: list[Mapping[str, Any]], create: Callable[[dict[str, Any]], Mapping[str, Any]]
) -> ObservabilityJobInstall:
    matches = [job for job in existing_jobs if job.get("name") == OBSERVABILITY_REVIEW_JOB_NAME]
    if len(matches) > 1:
        raise ValueError("duplicate observability review jobs fail closed")
    desired = _spec()
    if matches:
        actual = matches[0]
        expected = {key: value for key, value in desired.items() if key != "next_run_at"}
        comparable = {}
        for key in expected:
            if key not in actual and key in _RUNTIME_PIN_FIELDS:
                continue
            actual_value = _normalize_actual_value(key, actual.get(key))
            if key in _RUNTIME_PIN_FIELDS and actual_value is None:
                continue
            comparable[key] = actual_value
        expected = {
            key: value
            for key, value in expected.items()
            if key not in _RUNTIME_PIN_FIELDS
            or (key in actual and _normalize_actual_value(key, actual.get(key)) is not None)
        }
        if comparable != expected:
            raise ValueError("observability review job spec conflict")
        job_id = actual.get("id")
        if not isinstance(job_id, str) or not job_id:
            raise ValueError("observability review job has no id")
        return ObservabilityJobInstall(job_id=job_id, created=False)
    created = create(desired)
    job_id = created.get("id")
    if not isinstance(job_id, str) or not job_id:
        raise ValueError("cron create did not return a job id")
    return ObservabilityJobInstall(job_id=job_id, created=True)


__all__ = [
    "OBSERVABILITY_REVIEW_JOB_NAME",
    "OBSERVABILITY_REVIEW_SCRIPT",
    "ObservabilityJobInstall",
    "ensure_single_observability_review_job",
]
