from __future__ import annotations

import json
from uuid import uuid4

from hermes_harness.observability_review import GatewayJsonRpcReviewExecutor, build_review_envelope


class RecordingTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.notifications: list[dict[str, object]] = []
        self.closed = False

    def request(self, method: str, params: dict[str, object]) -> dict[str, object]:
        self.calls.append((method, params))
        return (
            {"session_id": "planner-session"}
            if method == "session.create"
            else {"status": "streaming"}
        )

    def wait_for_message_complete(
        self, session_id: str, timeout_seconds: float
    ) -> dict[str, object]:
        assert session_id == "planner-session"
        assert timeout_seconds > 0
        return {
            "text": json.dumps(
                {
                    "schema_version": "architect-review-draft-1.0.0",
                    "title": "Failure review",
                    "description": "bounded",
                    "observed_behavior": "request failed",
                    "undesired_behavior": "failure remains",
                    "desired_behavior": "safe recovery",
                    "impact": "delay",
                    "acceptance_criteria": ["bounded"],
                }
            )
        }

    def close(self) -> None:
        self.closed = True


def test_gateway_adapter_sends_pinned_sanitized_envelope_and_one_prompt() -> None:
    transport = RecordingTransport()
    envelope = build_review_envelope(
        review_run_id=uuid4(),
        candidate_digest="a" * 64,
        candidates=[],
        origin_session="cron:review",
    )

    draft = GatewayJsonRpcReviewExecutor(transport).execute_read_only(
        envelope, output_contract="architect-review-draft-1.0.0"
    )

    assert draft["schema_version"] == "architect-review-draft-1.0.0"
    assert [method for method, _ in transport.calls] == ["session.create", "prompt.submit"]
    assert transport.calls[1][1]["session_id"] == "planner-session"
    assert "prompt" not in str(transport.calls[1][1]).lower()
    assert transport.closed is True
