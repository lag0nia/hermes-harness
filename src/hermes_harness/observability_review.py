"""Fail-closed dispatch of one sanitized architecture review over JSON-RPC."""
# ruff: noqa: E501

from __future__ import annotations

import json
import os
import select
import shlex
import subprocess
import time
from collections.abc import Callable, Mapping
from typing import Any, Protocol
from uuid import UUID, uuid5

from .control_plane.contracts import Effort, Intent, IntentEnvelope, ModelPolicy, RiskClass

REVIEW_MODEL_POLICY = {
    "provider": "openai-codex",
    "model": "gpt-5.6-luna",
    "effort": "medium",
}
_REVIEW_NAMESPACE = UUID("0e46b4b2-bf01-47dd-9c3e-f5d4ddb7ee49")
_REVIEW_COMPLETION_TIMEOUT_SECONDS = 120.0
_ALLOWED_EVIDENCE = frozenset(
    {
        "event_id", "trace_id", "occurred_at", "event_type", "component", "phase", "status",
        "side_effect_class", "summary", "error_code", "error_type", "tool_name",
    }
)
_FORBIDDEN_EVIDENCE = frozenset(
    {"prompt", "response", "headers", "cookies", "credentials", "token", "secret", "payload", "tool_result", "metadata", "error_message"}
)
_ACCEPTED_SUBMISSION_STATUSES = frozenset({"streaming", "queued", "accepted"})
_GLOBAL_EVENT_TYPES = frozenset(
    {
        "gateway.ready",
        "session.reclaimed",
        "skin.changed",
        "pet.changed",
        "cron.changed",
        "sessions.changed",
        "platforms.changed",
        "pairing.changed",
        "bot_relay.outbox.pending",
    }
)
_SESSION_EVENT_TYPES_WITHOUT_PAYLOAD = frozenset({"message.start"})


class ReviewExecutionBlocked(RuntimeError):
    """Raised whenever the constrained review path cannot be proven."""


class ReviewRpcTransport(Protocol):
    notifications: list[dict[str, object]]

    def request(self, method: str, params: dict[str, object]) -> dict[str, object]: ...

    def wait_for_message_complete(self, session_id: str, timeout_seconds: float) -> dict[str, object]: ...

    def close(self) -> None: ...


class JsonRpcStdioClient:
    """One durable JSON-RPC connection with interleaved event buffering.

    Calls are deliberately serial. A review session is one prompt only, so no
    event correlation field beyond the unique session identifier is trusted.
    """

    def __init__(
        self,
        argv: list[str],
        *,
        timeout_seconds: float = 30.0,
        popen: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
    ) -> None:
        if not argv:
            raise ReviewExecutionBlocked("gateway RPC command is empty")
        self._argv = argv
        self._timeout_seconds = timeout_seconds
        self._popen = popen
        self._process: subprocess.Popen[str] | None = None
        self._next_request_id = 0
        self.notifications: list[dict[str, object]] = []
        self._completed_sessions: set[str] = set()

    def _start(self) -> subprocess.Popen[str]:
        if self._process is None:
            try:
                self._process = self._popen(
                    self._argv,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    bufsize=1,
                )
            except OSError as exc:
                raise ReviewExecutionBlocked(f"gateway RPC transport failed: {exc}") from exc
        process = self._process
        if process.poll() is not None or process.stdin is None or process.stdout is None:
            raise ReviewExecutionBlocked("gateway RPC process is not a durable live connection")
        return process

    def _read_frame(self, deadline: float) -> dict[str, object]:
        process = self._start()
        assert process.stdout is not None
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ReviewExecutionBlocked("gateway RPC timeout")
        try:
            ready, _, _ = select.select([process.stdout], [], [], remaining)
            if not ready:
                raise ReviewExecutionBlocked("gateway RPC timeout")
            line = process.stdout.readline()
        except OSError as exc:
            raise ReviewExecutionBlocked(f"gateway RPC transport failed: {exc}") from exc
        if not line:
            raise ReviewExecutionBlocked("gateway RPC connection closed before completion")
        try:
            frame = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ReviewExecutionBlocked("gateway RPC stream returned invalid JSON") from exc
        if not isinstance(frame, dict) or frame.get("jsonrpc") != "2.0":
            raise ReviewExecutionBlocked("gateway RPC stream returned an invalid frame")
        return frame

    def _record_event(self, frame: Mapping[str, object]) -> bool:
        if frame.get("method") != "event":
            return False
        params = frame.get("params")
        if not isinstance(params, dict):
            raise ReviewExecutionBlocked("gateway event parameters are invalid")
        event_type = params.get("type")
        if not isinstance(event_type, str):
            raise ReviewExecutionBlocked("gateway event cannot verify its session")
        if event_type in _GLOBAL_EVENT_TYPES:
            payload = params.get("payload")
            if not isinstance(payload, dict):
                raise ReviewExecutionBlocked("gateway event cannot verify its session")
            self.notifications.append({"type": event_type, "payload": payload})
            return True
        session_id = params.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise ReviewExecutionBlocked("gateway event cannot verify its session")
        payload = params.get("payload")
        if payload is None:
            if event_type not in _SESSION_EVENT_TYPES_WITHOUT_PAYLOAD:
                raise ReviewExecutionBlocked("gateway event payload is missing")
            self.notifications.append({"type": event_type, "session_id": session_id})
            return True
        if not isinstance(payload, dict):
            raise ReviewExecutionBlocked("gateway event payload is invalid")
        event: dict[str, object] = {
            "type": event_type,
            "session_id": session_id,
            "payload": payload,
        }
        self.notifications.append(event)
        if event_type == "message.complete":
            if session_id in self._completed_sessions:
                raise ReviewExecutionBlocked("gateway emitted a second message completion")
            self._completed_sessions.add(session_id)
        return True

    def request(self, method: str, params: dict[str, object]) -> dict[str, object]:
        process = self._start()
        assert process.stdin is not None
        self._next_request_id += 1
        request_id = f"observability-review-{self._next_request_id}"
        request = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        try:
            process.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
            process.stdin.flush()
        except OSError as exc:
            raise ReviewExecutionBlocked(f"gateway RPC transport failed: {exc}") from exc
        deadline = time.monotonic() + self._timeout_seconds
        while True:
            frame = self._read_frame(deadline)
            if self._record_event(frame):
                continue
            if frame.get("id") != request_id:
                raise ReviewExecutionBlocked("gateway RPC response cannot be correlated")
            if "error" in frame:
                raise ReviewExecutionBlocked("gateway RPC returned an error response")
            result = frame.get("result")
            if not isinstance(result, dict):
                raise ReviewExecutionBlocked("gateway RPC result must be an object")
            return result

    def wait_for_message_complete(self, session_id: str, timeout_seconds: float) -> dict[str, object]:
        if not session_id or session_id in self._completed_sessions:
            raise ReviewExecutionBlocked("gateway completion session is not unique")
        deadline = time.monotonic() + timeout_seconds
        while True:
            frame = self._read_frame(deadline)
            is_event = self._record_event(frame)
            if not is_event:
                raise ReviewExecutionBlocked("gateway emitted an unexpected response while streaming")
            event = self.notifications[-1]
            if event["type"] == "message.complete" and event["session_id"] == session_id:
                payload = event["payload"]
                assert isinstance(payload, dict)
                return payload

    def close(self) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        if process.stdin is not None:
            process.stdin.close()
        if process.stdout is not None:
            process.stdout.close()


class ReadOnlyReviewExecutor:
    """Guard for an adapter that must prove its constrained execution path."""

    def prepare(self, envelope: IntentEnvelope) -> IntentEnvelope:
        if envelope.intent is not Intent.TECHNICAL_PLAN:
            raise ReviewExecutionBlocked("review must remain technical.plan")
        expected = ModelPolicy(provider="openai-codex", model="gpt-5.6-luna", effort=Effort.MEDIUM)
        if envelope.model_policy != expected:
            raise ReviewExecutionBlocked("review model policy is not the pinned policy")
        if envelope.parameters.get("requested_profile") != "architect-planner":
            raise ReviewExecutionBlocked("review must target architect-planner")
        if envelope.parameters.get("read_only") is not True:
            raise ReviewExecutionBlocked("review must explicitly be read-only")
        candidates = envelope.parameters.get("candidates")
        if not isinstance(candidates, list):
            raise ReviewExecutionBlocked("review candidates must be a list")
        _validate_candidates(candidates)
        return envelope

    def execute_read_only(self, envelope: IntentEnvelope, *, output_contract: str) -> dict[str, object]:
        self.prepare(envelope)
        if output_contract != "architect-review-draft-1.0.0":
            raise ReviewExecutionBlocked("review output contract is not accepted")
        raise ReviewExecutionBlocked("no verified Hermes runtime review submitter is configured")


class GatewayJsonRpcReviewExecutor(ReadOnlyReviewExecutor):
    """One-session, one-prompt JSON-RPC adapter for a read-only review."""

    def __init__(self, transport: ReviewRpcTransport) -> None:
        self._transport = transport

    def execute_read_only(self, envelope: IntentEnvelope, *, output_contract: str) -> dict[str, object]:
        self.prepare(envelope)
        if output_contract != "architect-review-draft-1.0.0":
            raise ReviewExecutionBlocked("review output contract is not accepted")
        try:
            created = self._transport.request(
                "session.create",
                {
                    "profile": "architect-planner", "title": "Observability review",
                    "model": REVIEW_MODEL_POLICY["model"], "provider": REVIEW_MODEL_POLICY["provider"],
                    "reasoning_effort": REVIEW_MODEL_POLICY["effort"], "read_only": True,
                    "source": "observability-review",
                },
            )
            session_id = created.get("session_id")
            if not isinstance(session_id, str) or not session_id:
                raise ReviewExecutionBlocked("gateway did not create a verifiable dedicated planner session")
            submitted = self._transport.request(
                "prompt.submit",
                {
                    "session_id": session_id,
                    "text": json.dumps(envelope.model_dump(mode="json"), sort_keys=True, separators=(",", ":")),
                    "read_only": True,
                },
            )
            if submitted.get("status") not in _ACCEPTED_SUBMISSION_STATUSES:
                raise ReviewExecutionBlocked("gateway did not accept the review prompt")
            completed = self._transport.wait_for_message_complete(
                session_id, timeout_seconds=_REVIEW_COMPLETION_TIMEOUT_SECONDS
            )
            if completed.get("status") == "error":
                raise ReviewExecutionBlocked("gateway review completion has error status")
            text = completed.get("text")
            if not isinstance(text, str):
                raise ReviewExecutionBlocked("gateway completion did not contain payload.text")
            try:
                draft = json.loads(text)
            except json.JSONDecodeError as exc:
                raise ReviewExecutionBlocked("gateway completion payload.text is not JSON") from exc
            if not isinstance(draft, dict):
                raise ReviewExecutionBlocked("gateway completion payload.text must be an object")
            _validate_draft(draft)
            return draft
        finally:
            self._transport.close()


def configured_gateway_review_executor() -> GatewayJsonRpcReviewExecutor:
    """Build the local durable gateway bridge without passing credentials."""
    command = os.environ.get("HERMES_OBSERVABILITY_GATEWAY_RPC_COMMAND", "").strip()
    if not command:
        raise ReviewExecutionBlocked("HERMES_OBSERVABILITY_GATEWAY_RPC_COMMAND is not configured")
    return GatewayJsonRpcReviewExecutor(JsonRpcStdioClient(shlex.split(command)))


def _validate_draft(draft: Mapping[str, object]) -> None:
    fields = {"schema_version", "title", "description", "observed_behavior", "undesired_behavior", "desired_behavior", "impact", "acceptance_criteria"}
    if set(draft) != fields or draft.get("schema_version") != "architect-review-draft-1.0.0":
        raise ReviewExecutionBlocked("planner draft does not match the strict versioned contract")
    for field in fields - {"schema_version", "acceptance_criteria"}:
        value = draft.get(field)
        if not isinstance(value, str) or not value:
            raise ReviewExecutionBlocked("planner draft contains an invalid text field")
    criteria = draft.get("acceptance_criteria")
    if not isinstance(criteria, list) or not criteria or any(not isinstance(item, str) or not item for item in criteria):
        raise ReviewExecutionBlocked("planner draft contains invalid acceptance criteria")


def _validate_candidates(candidates: list[object]) -> None:
    if len(candidates) > 200:
        raise ReviewExecutionBlocked("review candidates exceed the bounded limit")
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            raise ReviewExecutionBlocked("review candidate must be an object")
        keys = {str(key) for key in candidate}
        if keys & _FORBIDDEN_EVIDENCE or not keys <= _ALLOWED_EVIDENCE:
            raise ReviewExecutionBlocked("review evidence contains a forbidden field")


def build_review_envelope(*, review_run_id: UUID, candidate_digest: str, candidates: list[Mapping[str, Any]], origin_session: str) -> IntentEnvelope:
    if len(candidate_digest) != 64 or any(char not in "0123456789abcdef" for char in candidate_digest):
        raise ReviewExecutionBlocked("candidate digest must be sha256")
    _validate_candidates(list(candidates))
    model_policy = ModelPolicy(provider="openai-codex", model="gpt-5.6-luna", effort=Effort.MEDIUM)
    return IntentEnvelope(
        schema_version="1.0.0", job_id=uuid5(_REVIEW_NAMESPACE, f"review:{review_run_id}"), trace_id=uuid5(_REVIEW_NAMESPACE, f"trace:{review_run_id}"), origin_profile="default", origin_session=origin_session, delivery_target="control-plane", intent=Intent.TECHNICAL_PLAN, idempotency_key=f"observability-review:{review_run_id}", risk_class=RiskClass.MEDIUM, model_policy=model_policy, context_references=[f"observability-review:{review_run_id}"],
        parameters={"requested_profile": "architect-planner", "read_only": True, "candidate_digest": candidate_digest, "candidates": [dict(candidate) for candidate in candidates], "output_contract": "architect-review-draft-1.0.0"},
        source_text="Review the bounded sanitized failure evidence in this envelope as a read-only architect-planner. Your entire response MUST be one JSON object with exactly these keys and no others: schema_version, title, description, observed_behavior, undesired_behavior, desired_behavior, impact, acceptance_criteria. Set schema_version exactly to architect-review-draft-1.0.0. Use strings for title, description, observed_behavior, undesired_behavior, desired_behavior, and impact; use a non-empty array of strings for acceptance_criteria. Do not return markdown. Do not return schema_version 1.0.0, a review or contract wrapper, recommended_plan, risks, or rollback_strategy. Do not modify repositories, invoke tools that write, recover raw content, or include secrets.",
    )


__all__ = ["REVIEW_MODEL_POLICY", "GatewayJsonRpcReviewExecutor", "JsonRpcStdioClient", "ReadOnlyReviewExecutor", "ReviewExecutionBlocked", "build_review_envelope", "configured_gateway_review_executor"]
