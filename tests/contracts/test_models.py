from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import TypeAdapter, ValidationError

from hermes_harness.control_plane.confirmations import ConfirmationManager
from hermes_harness.control_plane.contracts import (
    AgentEvent,
    ChangeEvent,
    ConfirmationGrant,
    ErrorCode,
    IntentEnvelope,
    JobRequest,
    JobResult,
    NeedInput,
    ProgressEvent,
    TypedError,
)
from tests.contracts.test_intent import envelope


def common() -> dict[str, object]:
    return {
        key: value for key, value in envelope().items() if key not in {"parameters", "source_text"}
    }


def test_job_request_and_discriminated_agent_event_validate() -> None:
    request = JobRequest.model_validate({**common(), "requested_profile": "researcher"})
    event = TypeAdapter(AgentEvent).validate_python(
        {
            **common(),
            "event_type": "progress",
            "sequence": 1,
            "occurred_at": datetime.now(UTC),
            "message": "Buscando fuentes",
            "payload": {},
        }
    )
    assert request.requested_profile == "researcher"
    assert isinstance(event, ProgressEvent)


def test_result_need_input_change_and_typed_error_are_closed() -> None:
    error = TypedError(code=ErrorCode.MISSING_REQUIRED_INPUT, message="Falta la fecha")
    result = JobResult.model_validate(
        {
            **common(),
            "status": "FAILED_FINAL",
            "summary": "No se pudo continuar",
            "result": {},
            "evidence": [],
            "side_effects": [],
            "verification": [],
            "confidence": {"score": 0.0, "signals": []},
            "error": error.model_dump(mode="json"),
            "artifacts": [],
            "documentation_impact": "none",
        }
    )
    need = NeedInput.model_validate(
        {
            **common(),
            "prompt": "¿Qué fecha?",
            "missing_fields": ["date"],
            "choices": [],
        }
    )
    change = ChangeEvent.model_validate(
        {
            **common(),
            "event_type": "change",
            "sequence": 2,
            "occurred_at": datetime.now(UTC),
            "message": "Archivo actualizado",
            "payload": {},
            "changed_paths": ["README.md"],
            "change_kind": "documentation",
        }
    )
    assert result.error == error
    assert need.missing_fields == ["date"]
    assert change.change_kind == "documentation"


def test_confirmation_grant_rejects_expired_or_sensitive_payload() -> None:
    now = datetime.now(UTC)
    operation = {
        "operation": "checkout.submit",
        "target": "Ejemplo",
        "amount": "12.30 EUR",
        "options": {"size": "large"},
        "destination": "delivery",
        "external_state_version": "cart-v1",
    }
    grant = ConfirmationGrant.model_validate(
        {
            **common(),
            "confirmation_id": str(uuid4()),
            "digest": ConfirmationManager.digest(operation),
            "issued_at": now,
            "expires_at": now + timedelta(minutes=30),
            "operation": operation,
            "external_state_version": "cart-v1",
        }
    )
    assert grant.digest == ConfirmationManager.digest(operation)
    with pytest.raises(ValidationError):
        ConfirmationGrant.model_validate(
            {
                **grant.model_dump(),
                "expires_at": now - timedelta(seconds=1),
            }
        )
    with pytest.raises(ValidationError):
        ProgressEvent.model_validate(
            {
                **common(),
                "event_type": "progress",
                "sequence": 1,
                "occurred_at": now,
                "message": "x",
                "payload": {"nested": {"access_token": "forbidden"}},
            }
        )


def test_confirmation_grant_rejects_arbitrary_operation_and_digest() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        ConfirmationGrant.model_validate(
            {
                **common(),
                "confirmation_id": str(uuid4()),
                "digest": "a" * 64,
                "issued_at": now,
                "expires_at": now + timedelta(minutes=30),
                "operation": {"merchant": "Ejemplo"},
                "external_state_version": "cart-v1",
            }
        )


def test_text_contracts_reject_secret_assignments() -> None:
    with pytest.raises(ValidationError):
        IntentEnvelope.model_validate(envelope(source_text="password=top-secret"))
    with pytest.raises(ValidationError):
        ProgressEvent.model_validate(
            {
                **common(),
                "event_type": "progress",
                "sequence": 1,
                "occurred_at": datetime.now(UTC),
                "message": "Password=top-secret",
                "payload": {},
            }
        )
