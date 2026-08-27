from uuid import uuid4

import pytest
from pydantic import ValidationError

from hermes_harness.control_plane.contracts import Intent, IntentEnvelope


def envelope(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": "1.0.0",
        "job_id": str(uuid4()),
        "trace_id": str(uuid4()),
        "origin_profile": "default",
        "origin_session": "telegram:42",
        "delivery_target": "telegram:42",
        "intent": "calendar.create_vtodo",
        "idempotency_key": "telegram:update:123",
        "risk_class": "low",
        "model_policy": {"provider": "openai-codex", "model": "gpt-5.6-luna", "effort": "medium"},
        "context_references": [],
        "parameters": {"summary": "Comprar leche"},
        "source_text": "Crea una tarea para comprar leche",
    }
    value.update(overrides)
    return value


def test_intent_envelope_accepts_closed_intent() -> None:
    parsed = IntentEnvelope.model_validate(envelope())
    assert parsed.intent is Intent.CALENDAR_CREATE_VTODO


def test_intent_envelope_rejects_unknown_intent_and_bad_identifier() -> None:
    with pytest.raises(ValidationError):
        IntentEnvelope.model_validate(envelope(intent="calendar.guess"))
    with pytest.raises(ValidationError):
        IntentEnvelope.model_validate(envelope(job_id="not-an-id"))
