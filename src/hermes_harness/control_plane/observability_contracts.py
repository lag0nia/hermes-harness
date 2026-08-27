"""Harness-side Pydantic contract mirror for observability-event-1.0.0."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ObservabilityEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_name: Literal["observability-event"] = "observability-event"
    schema_version: Literal["1.0.0"] = "1.0.0"
    event_id: UUID = Field(default_factory=uuid4)
    trace_id: UUID
    span_id: UUID
    parent_span_id: UUID | None = None
    job_id: UUID | None = None
    session_id: str | None = Field(default=None, max_length=256)
    turn_id: str | None = Field(default=None, max_length=256)
    profile: str | None = Field(default=None, max_length=128)
    event_type: str = Field(min_length=1, max_length=128)
    component: str = Field(min_length=1, max_length=64)
    phase: str = Field(min_length=1, max_length=64)
    status: str = Field(min_length=1, max_length=64)
    criticality: Literal["normal", "critical"] = "normal"
    side_effect_class: Literal["none", "read_only", "reversible", "irreversible"] = "none"
    confirmation_state: Literal["not_required", "pending", "approved", "denied", "consumed"] = (
        "not_required"
    )
    occurred_at: datetime
    duration_ms: int | None = Field(default=None, ge=0, le=86_400_000)
    sequence: int = Field(default=0, ge=0)
    summary: str = Field(min_length=1, max_length=160)
    metadata: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = Field(default=None, max_length=128)
    error_type: str | None = Field(default=None, max_length=128)
    error_message: str | None = Field(default=None, max_length=512)

    @field_validator("occurred_at")
    @classmethod
    def aware_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        return value

    @field_validator("metadata")
    @classmethod
    def no_raw_fields(cls, value: dict[str, Any]) -> dict[str, Any]:
        forbidden = {
            "prompt",
            "response",
            "body",
            "headers",
            "cookies",
            "credentials",
            "args",
            "result",
        }

        def walk(item: object) -> None:
            if isinstance(item, dict):
                for key, nested in item.items():
                    if str(key).lower() in forbidden:
                        raise ValueError(f"raw field is forbidden: {key}")
                    walk(nested)
            elif isinstance(item, list):
                for nested in item:
                    walk(nested)

        walk(value)
        return value
