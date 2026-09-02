from __future__ import annotations

import json
from collections.abc import Iterator
from uuid import uuid4

import pytest

from hermes_harness.observability_review import (
    GatewayJsonRpcReviewExecutor,
    JsonRpcStdioClient,
    ReviewExecutionBlocked,
    build_review_envelope,
)


def envelope():
    return build_review_envelope(
        review_run_id=uuid4(),
        candidate_digest="a" * 64,
        candidates=[],
        origin_session="cron:review",
    )


def draft() -> dict[str, object]:
    return {
        "schema_version": "architect-review-draft-1.0.0",
        "title": "Provider unavailable",
        "description": "The provider request cannot complete.",
        "observed_behavior": "A provider request fails with PROVIDER_UNAVAILABLE.",
        "undesired_behavior": "The scheduled review cannot classify the failure.",
        "desired_behavior": "The provider retry path records an actionable failure.",
        "impact": "Review processing is delayed.",
        "acceptance_criteria": ["A failed provider request is classified."],
    }


def test_stdio_client_accepts_global_gateway_ready_event() -> None:
    client = JsonRpcStdioClient(["gateway"])

    assert client._record_event(
        {
            "jsonrpc": "2.0",
            "method": "event",
            "params": {
                "type": "gateway.ready",
                "payload": {"change_events": True},
            },
        }
    ) is True


def test_stdio_client_accepts_global_sessions_changed_event() -> None:
    client = JsonRpcStdioClient(["gateway"])

    assert client._record_event(
        {
            "jsonrpc": "2.0",
            "method": "event",
            "params": {
                "type": "sessions.changed",
                "payload": {},
            },
        }
    ) is True


def test_stdio_client_accepts_session_message_start_without_payload() -> None:
    client = JsonRpcStdioClient(["gateway"])

    assert client._record_event(
        {
            "jsonrpc": "2.0",
            "method": "event",
            "params": {
                "type": "message.start",
                "session_id": "planner-session",
            },
        }
    ) is True


class FrameTransport:
    """In-memory transport replaying actual JSON-RPC frame shapes."""

    def __init__(self, frames: list[dict[str, object]]) -> None:
        self.frames: Iterator[dict[str, object]] = iter(frames)
        self.requests: list[tuple[str, dict[str, object]]] = []
        self.notifications: list[dict[str, object]] = []
        self.closed = False
        self.completed_sessions: set[str] = set()
        self.completion_timeouts: list[float] = []

    def request(self, method: str, params: dict[str, object]) -> dict[str, object]:
        self.requests.append((method, params))
        while True:
            frame = next(self.frames)
            if frame.get("method") == "event":
                event = frame["params"]
                assert isinstance(event, dict)
                self.notifications.append(event)
                continue
            return frame["result"]  # type: ignore[return-value]

    def wait_for_message_complete(
        self, session_id: str, timeout_seconds: float
    ) -> dict[str, object]:
        self.completion_timeouts.append(timeout_seconds)
        while True:
            frame = next(self.frames)
            if frame.get("method") != "event":
                continue
            event = frame["params"]
            assert isinstance(event, dict)
            self.notifications.append(event)
            if event.get("type") != "message.complete" or event.get("session_id") != session_id:
                continue
            if session_id in self.completed_sessions:
                raise ReviewExecutionBlocked("gateway emitted a second message completion")
            self.completed_sessions.add(session_id)
            payload = event.get("payload")
            assert isinstance(payload, dict)
            return payload

    def close(self) -> None:
        self.closed = True


def test_gateway_executor_accepts_streaming_and_uses_only_session_completion() -> None:
    transport = FrameTransport(
        [
            {
                "jsonrpc": "2.0",
                "method": "event",
                "params": {"type": "status.update", "session_id": "other", "payload": {}},
            },
            {"jsonrpc": "2.0", "id": "gateway-id-1", "result": {"session_id": "planner-session"}},
            {
                "jsonrpc": "2.0",
                "method": "event",
                "params": {
                    "type": "message.delta",
                    "session_id": "planner-session",
                    "payload": {"text": "{"},
                },
            },
            {"jsonrpc": "2.0", "id": "gateway-id-2", "result": {"status": "streaming"}},
            {
                "jsonrpc": "2.0",
                "method": "event",
                "params": {
                    "type": "message.complete",
                    "session_id": "other",
                    "payload": {"text": "{}"},
                },
            },
            {
                "jsonrpc": "2.0",
                "method": "event",
                "params": {
                    "type": "message.complete",
                    "session_id": "planner-session",
                    "payload": {"text": json.dumps(draft())},
                },
            },
        ]
    )

    assert (
        GatewayJsonRpcReviewExecutor(transport).execute_read_only(
            envelope(), output_contract="architect-review-draft-1.0.0"
        )
        == draft()
    )
    assert [method for method, _ in transport.requests] == ["session.create", "prompt.submit"]
    assert transport.completion_timeouts == [120.0]
    assert transport.closed is True


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "error", "text": json.dumps(draft())},
        {"text": "not JSON"},
        {"text": json.dumps({"title": "wrong contract"})},
    ],
)
def test_gateway_executor_fails_closed_for_bad_completion(payload: dict[str, object]) -> None:
    transport = FrameTransport(
        [
            {"jsonrpc": "2.0", "id": "gateway-id-1", "result": {"session_id": "planner-session"}},
            {"jsonrpc": "2.0", "id": "gateway-id-2", "result": {"status": "accepted"}},
            {
                "jsonrpc": "2.0",
                "method": "event",
                "params": {
                    "type": "message.complete",
                    "session_id": "planner-session",
                    "payload": payload,
                },
            },
        ]
    )
    with pytest.raises(ReviewExecutionBlocked):
        GatewayJsonRpcReviewExecutor(transport).execute_read_only(
            envelope(), output_contract="architect-review-draft-1.0.0"
        )
    assert transport.closed is True


def test_gateway_executor_fails_closed_for_second_finalization() -> None:
    transport = FrameTransport(
        [
            {"jsonrpc": "2.0", "id": "gateway-id-1", "result": {"session_id": "planner-session"}},
            {"jsonrpc": "2.0", "id": "gateway-id-2", "result": {"status": "queued"}},
            {
                "jsonrpc": "2.0",
                "method": "event",
                "params": {
                    "type": "message.complete",
                    "session_id": "planner-session",
                    "payload": {"text": json.dumps(draft())},
                },
            },
            {
                "jsonrpc": "2.0",
                "method": "event",
                "params": {
                    "type": "message.complete",
                    "session_id": "planner-session",
                    "payload": {"text": json.dumps(draft())},
                },
            },
        ]
    )
    transport.completed_sessions.add("planner-session")
    with pytest.raises(ReviewExecutionBlocked, match="second"):
        GatewayJsonRpcReviewExecutor(transport).execute_read_only(
            envelope(), output_contract="architect-review-draft-1.0.0"
        )


def test_stdio_client_buffers_interleaved_notifications_before_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Stdin:
        def write(self, _: str) -> int:
            return 1

        def flush(self) -> None:
            pass

        def close(self) -> None:
            pass

    class Stdout:
        def __init__(self) -> None:
            self.lines = iter(
                [
                    '{"jsonrpc":"2.0","method":"event","params":{"type":"message.delta","session_id":"planner-session","payload":{"text":"draft"}}}\n',
                    '{"jsonrpc":"2.0","id":"observability-review-1","result":{"session_id":"planner-session"}}\n',
                ]
            )

        def fileno(self) -> int:
            return 3

        def readline(self) -> str:
            return next(self.lines)

        def close(self) -> None:
            pass

    class Process:
        stdin = Stdin()
        stdout = Stdout()

        def poll(self):
            return None

        def terminate(self):
            pass

        def wait(self, timeout=None):
            return 0

    monkeypatch.setattr(
        "hermes_harness.observability_review.select.select", lambda *_: ([3], [], [])
    )
    client = JsonRpcStdioClient(["gateway"], popen=lambda *_args, **_kwargs: Process())

    assert client.request("session.create", {}) == {"session_id": "planner-session"}
    assert client.notifications == [
        {"type": "message.delta", "session_id": "planner-session", "payload": {"text": "draft"}}
    ]
