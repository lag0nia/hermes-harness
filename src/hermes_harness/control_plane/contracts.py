"""Versioned, closed contracts for the control plane."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

SchemaVersion = Annotated[str, StringConstraints(pattern=r"^1\.0\.\d+$")]
ShortText = Annotated[str, StringConstraints(min_length=1, max_length=4096)]


class Intent(StrEnum):
    CALENDAR_CREATE_VTODO = "calendar.create_vtodo"
    CALENDAR_CREATE_EVENT = "calendar.create_event"
    CALENDAR_UPDATE = "calendar.update"
    CALENDAR_DELETE = "calendar.delete"
    CALENDAR_LIST = "calendar.list"
    PI_HEALTH_READ = "pi.health.read"
    PI_JOBS_LIST = "pi.jobs.list"
    PI_JOBS_CANCEL = "pi.jobs.cancel"
    BROWSER_RESEARCH = "browser.research"
    BROWSER_ORDER_PREPARE = "browser.order.prepare"
    BROWSER_FORM_PREPARE = "browser.form.prepare"
    BROWSER_AUTH_REQUIRED = "browser.auth_required"
    TRAVEL_PLAN = "travel.plan"
    TRAVEL_SEARCH_FLIGHTS = "travel.search_flights"
    TRAVEL_SEARCH_STAYS = "travel.search_stays"
    TECHNICAL_RESEARCH = "technical.research"
    TECHNICAL_PLAN = "technical.plan"
    TECHNICAL_CHANGE = "technical.change"
    TECHNICAL_REVIEW = "technical.review"
    DEVELOPMENT_COORDINATE = "development.coordinate"
    CODE_PLAN = "code.plan"
    CODE_CHANGE = "code.change"
    CODE_REVIEW = "code.review"
    DOCS_RECONCILE = "docs.reconcile"
    DOCS_QUERY = "docs.query"
    GENERAL_ANSWER = "general.answer"
    GENERAL_CLARIFY = "general.clarify"


class RiskClass(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Effort(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ModelPolicy(StrictModel):
    provider: Literal["openai-codex"]
    model: ShortText
    effort: Effort
    context_size_justification: ShortText | None = None


class CommonIdentifiers(StrictModel):
    schema_version: SchemaVersion
    job_id: UUID
    parent_job_id: UUID | None = None
    trace_id: UUID
    origin_profile: ShortText
    origin_session: ShortText
    delivery_target: ShortText
    intent: Intent
    idempotency_key: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    risk_class: RiskClass
    model_policy: ModelPolicy
    context_references: list[ShortText] = Field(max_length=100)


class IntentEnvelope(CommonIdentifiers):
    parameters: dict[str, Any]
    source_text: Annotated[str, StringConstraints(min_length=1, max_length=16_384)]
    dependencies: list[UUID] = Field(default_factory=list, max_length=20)

    @field_validator("source_text")
    @classmethod
    def source_has_no_secrets(cls, value: str) -> str:
        return reject_sensitive_text(value)

    @field_validator("parameters")
    @classmethod
    def reject_sensitive_fields(cls, value: dict[str, Any]) -> dict[str, Any]:
        reject_sensitive(value)
        return value


SENSITIVE_KEYS = {"password", "secret", "token", "card", "credential", "authorization"}
SENSITIVE_TEXT_PATTERN = (
    r"(?i)\b(password|secret|token|credential|authorization|api[_-]?key)\b\s*[:=]"
)


def reject_sensitive(value: object) -> None:
    """Reject secret-shaped keys recursively rather than trying to redact them."""
    if isinstance(value, dict):
        for key, nested in value.items():
            normalized = str(key).lower().replace("-", "_")
            if any(part in normalized for part in SENSITIVE_KEYS):
                raise ValueError(f"sensitive field is forbidden: {key}")
            reject_sensitive(nested)
    elif isinstance(value, list):
        for nested in value:
            reject_sensitive(nested)


def reject_sensitive_text(value: str) -> str:
    import re

    if re.search(SENSITIVE_TEXT_PATTERN, value):
        raise ValueError("sensitive assignment is forbidden in text")
    return value


class ErrorCode(StrEnum):
    INVALID_INPUT = "INVALID_INPUT"
    UNKNOWN_INTENT = "UNKNOWN_INTENT"
    MISSING_REQUIRED_INPUT = "MISSING_REQUIRED_INPUT"
    AMBIGUOUS_TARGET = "AMBIGUOUS_TARGET"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    CONFIRMATION_REQUIRED = "CONFIRMATION_REQUIRED"
    CONFIRMATION_EXPIRED = "CONFIRMATION_EXPIRED"
    CONFIRMATION_DIGEST_MISMATCH = "CONFIRMATION_DIGEST_MISMATCH"
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    RESOURCE_PRESSURE = "RESOURCE_PRESSURE"
    EXTERNAL_STATE_CHANGED = "EXTERNAL_STATE_CHANGED"
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    WORKER_STALE = "WORKER_STALE"
    CYCLE_DETECTED = "CYCLE_DETECTED"
    CANCELLED_BY_USER = "CANCELLED_BY_USER"
    ROLLBACK_FAILED = "ROLLBACK_FAILED"


class TypedError(StrictModel):
    code: ErrorCode
    message: ShortText
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("message")
    @classmethod
    def message_has_no_secrets(cls, value: str) -> str:
        return reject_sensitive_text(value)

    @field_validator("details")
    @classmethod
    def details_have_no_secrets(cls, value: dict[str, Any]) -> dict[str, Any]:
        reject_sensitive(value)
        return value


class JobRequest(CommonIdentifiers):
    requested_profile: ShortText
    input: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[UUID] = Field(default_factory=list, max_length=20)

    @field_validator("input")
    @classmethod
    def input_has_no_secrets(cls, value: dict[str, Any]) -> dict[str, Any]:
        reject_sensitive(value)
        return value


class EventBase(CommonIdentifiers):
    sequence: Annotated[int, Field(ge=0)]
    occurred_at: datetime
    message: ShortText
    payload: dict[str, Any]

    @field_validator("message")
    @classmethod
    def message_has_no_secrets(cls, value: str) -> str:
        return reject_sensitive_text(value)

    @field_validator("payload")
    @classmethod
    def payload_has_no_secrets(cls, value: dict[str, Any]) -> dict[str, Any]:
        reject_sensitive(value)
        return value


class ProgressEvent(EventBase):
    event_type: Literal["progress"]


class StateEvent(EventBase):
    event_type: Literal["state"]
    state: ShortText


class ChangeEvent(EventBase):
    event_type: Literal["change"]
    changed_paths: list[ShortText]
    change_kind: ShortText


AgentEvent = Annotated[ProgressEvent | StateEvent | ChangeEvent, Field(discriminator="event_type")]


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    ADMITTED = "ADMITTED"
    RUNNING = "RUNNING"
    WAITING_INPUT = "WAITING_INPUT"
    WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
    VERIFYING = "VERIFYING"
    BLOCKED = "BLOCKED"
    SUCCEEDED = "SUCCEEDED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_FINAL = "FAILED_FINAL"
    ROLLED_BACK = "ROLLED_BACK"
    CANCELLED = "CANCELLED"


class Confidence(StrictModel):
    score: Annotated[float, Field(ge=0.0, le=1.0)]
    signals: list[ShortText]


class JobResult(CommonIdentifiers):
    status: JobStatus
    summary: ShortText
    result: dict[str, Any]
    evidence: list[dict[str, Any]]
    side_effects: list[dict[str, Any]]
    verification: list[dict[str, Any]]
    confidence: Confidence
    error: TypedError | None = None
    artifacts: list[ShortText]
    documentation_impact: ShortText

    @field_validator("summary", "documentation_impact")
    @classmethod
    def result_text_has_no_secrets(cls, value: str) -> str:
        return reject_sensitive_text(value)

    @field_validator("result", "evidence", "side_effects", "verification")
    @classmethod
    def output_has_no_secrets(cls, value: object) -> object:
        reject_sensitive(value)
        return value


class NeedInput(CommonIdentifiers):
    prompt: ShortText
    missing_fields: list[ShortText]
    choices: list[ShortText]

    @field_validator("prompt")
    @classmethod
    def prompt_has_no_secrets(cls, value: str) -> str:
        return reject_sensitive_text(value)


class ConfirmationGrant(CommonIdentifiers):
    confirmation_id: UUID
    digest: Annotated[str, StringConstraints(pattern=r"^[a-f0-9]{64}$")]
    issued_at: datetime
    expires_at: datetime
    operation: dict[str, Any]
    external_state_version: ShortText

    @model_validator(mode="after")
    def has_valid_window(self) -> ConfirmationGrant:
        if self.expires_at <= self.issued_at:
            raise ValueError("confirmation must expire after issuance")
        if (self.expires_at - self.issued_at).total_seconds() > 1800:
            raise ValueError("confirmation validity cannot exceed 30 minutes")
        required = {
            "operation",
            "target",
            "amount",
            "options",
            "destination",
            "external_state_version",
        }
        if set(self.operation) != required:
            raise ValueError("confirmation operation fields are incomplete or unexpected")
        if self.operation["external_state_version"] != self.external_state_version:
            raise ValueError("confirmation external state version does not match operation")
        canonical = json.dumps(
            self.operation, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        if self.digest != hashlib.sha256(canonical.encode()).hexdigest():
            raise ValueError("confirmation digest does not match operation")
        reject_sensitive(self.operation)
        return self
