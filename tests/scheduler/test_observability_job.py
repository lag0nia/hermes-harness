
# ruff: noqa: E501
import pytest

from hermes_harness.observability_job import (
    OBSERVABILITY_REVIEW_JOB_NAME,
    OBSERVABILITY_REVIEW_SCRIPT,
    ensure_single_observability_review_job,
)


def test_job_installation_is_idempotent_and_does_not_fire_now() -> None:
    created = []
    def create(spec):
        created.append(spec)
        return {"id": "job-1", **spec}
    result = ensure_single_observability_review_job([], create)
    assert result.created is True
    assert result.job_id == "job-1"
    assert created[0]["name"] == OBSERVABILITY_REVIEW_JOB_NAME
    assert created[0]["schedule"] == "every 2d"
    assert created[0]["no_agent"] is True
    assert created[0]["next_run_at"] is None
    assert created[0]["script"] == "hermes-observability-review.py"


def test_duplicate_or_spec_conflict_fails_closed() -> None:
    job = {"id": "one", "name": OBSERVABILITY_REVIEW_JOB_NAME, "schedule": "every 2d", "no_agent": True, "script": OBSERVABILITY_REVIEW_SCRIPT, "repeat": None}
    with pytest.raises(ValueError, match="duplicate"):
        ensure_single_observability_review_job([job, {**job, "id": "two"}], lambda _: None)
    with pytest.raises(ValueError, match="spec"):
        ensure_single_observability_review_job([{**job, "schedule": "every 1d"}], lambda _: None)


def test_existing_hermes_job_shape_is_reconciled_without_false_conflict() -> None:
    actual = {
        "id": "job-1",
        "name": OBSERVABILITY_REVIEW_JOB_NAME,
        "schedule": {"kind": "interval", "minutes": 2880, "display": "every 2880m"},
        "repeat": {"times": None, "completed": 0},
        "no_agent": True,
        "script": OBSERVABILITY_REVIEW_SCRIPT,
        "model": None,
        "provider": None,
    }

    result = ensure_single_observability_review_job(
        [actual], lambda _: (_ for _ in ()).throw(AssertionError("must not create"))
    )

    assert result.created is False
    assert result.job_id == "job-1"


def test_job_spec_is_pinned_to_architect_planner_without_an_install_run() -> None:
    created = []
    ensure_single_observability_review_job([], lambda spec: created.append(spec) or {"id": "job-2", **spec})

    assert created[0]["profile"] == "architect-planner"
    assert created[0]["provider"] == "openai-codex"
    assert created[0]["model"] == "gpt-5.6-luna"
    assert created[0]["reasoning_effort"] == "medium"
    assert "run" not in created[0]
