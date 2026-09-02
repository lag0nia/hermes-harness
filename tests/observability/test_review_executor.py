# ruff: noqa: E501
from uuid import uuid4

import pytest

from hermes_harness.control_plane.contracts import Intent, IntentEnvelope, ModelPolicy, RiskClass
from hermes_harness.observability_review import (
    REVIEW_MODEL_POLICY,
    ReadOnlyReviewExecutor,
    ReviewExecutionBlocked,
    build_review_envelope,
)


def test_review_envelope_is_explicitly_routed_and_pinned() -> None:
    envelope = build_review_envelope(
        review_run_id=uuid4(),
        candidate_digest="a" * 64,
        candidates=[],
        origin_session="cron:review",
    )
    assert envelope.intent is Intent.TECHNICAL_PLAN
    assert envelope.parameters["requested_profile"] == "architect-planner"
    assert envelope.model_policy.model == "gpt-5.6-luna"
    assert envelope.model_policy.effort.value == "medium"
    assert envelope.source_text.startswith("Review the bounded sanitized")


def test_review_envelope_requires_exact_planner_output_instructions() -> None:
    envelope = build_review_envelope(
        review_run_id=uuid4(),
        candidate_digest="a" * 64,
        candidates=[],
        origin_session="cron:review",
    )

    assert "architect-review-draft-1.0.0" in envelope.source_text
    assert "exactly these keys" in envelope.source_text
    assert "Do not return markdown" in envelope.source_text


def test_executor_requires_verified_runtime_and_rejects_changes() -> None:
    executor = ReadOnlyReviewExecutor()
    envelope = build_review_envelope(
        review_run_id=uuid4(), candidate_digest="a" * 64, candidates=[], origin_session="cron:review"
    )
    with pytest.raises(ReviewExecutionBlocked):
        executor.execute_read_only(envelope, output_contract="architect-review-draft-1.0.0")
    changed = envelope.model_copy(update={"intent": Intent.TECHNICAL_CHANGE})
    with pytest.raises(ReviewExecutionBlocked):
        executor.prepare(changed)


def test_only_exact_policy_is_accepted() -> None:
    assert REVIEW_MODEL_POLICY == {"provider": "openai-codex", "model": "gpt-5.6-luna", "effort": "medium"}
    bad = ModelPolicy(provider="openai-codex", model="gpt-5.6-luna", effort="high")
    envelope = IntentEnvelope(
        schema_version="1.0.0",
        job_id=uuid4(),
        trace_id=uuid4(),
        origin_profile="default",
        origin_session="cron:review",
        delivery_target="control-plane",
        intent=Intent.TECHNICAL_PLAN,
        idempotency_key="review",
        risk_class=RiskClass.MEDIUM,
        model_policy=bad,
        context_references=["observability-review:test"],
        parameters={"requested_profile": "architect-planner", "candidates": []},
        source_text="Review the bounded sanitized failure evidence.",
    )
    with pytest.raises(ReviewExecutionBlocked):
        ReadOnlyReviewExecutor().prepare(envelope)


def test_review_envelope_allows_tool_name_but_excludes_raw_evidence() -> None:
    candidate = {"event_id": 1, "tool_name": "example_tool", "error_type": "tool_error"}
    envelope = build_review_envelope(
        review_run_id=uuid4(), candidate_digest="a" * 64, candidates=[candidate], origin_session="cron:review"
    )
    assert envelope.parameters["candidates"] == [candidate]
    for forbidden in ("prompt", "metadata", "error_message"):
        with pytest.raises(ReviewExecutionBlocked):
            build_review_envelope(
                review_run_id=uuid4(),
                candidate_digest="a" * 64,
                candidates=[{"event_id": 1, forbidden: "raw"}],
                origin_session="cron:review",
            )
