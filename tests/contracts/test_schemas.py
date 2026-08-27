import json
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from hermes_harness.control_plane.contracts import IntentEnvelope
from tests.contracts.test_intent import envelope

SCHEMAS = Path(__file__).parents[2] / "contracts"


@pytest.mark.parametrize(
    "filename",
    [
        "intent-envelope-1.0.0.schema.json",
        "job-request-1.0.0.schema.json",
        "agent-event-1.0.0.schema.json",
        "job-result-1.0.0.schema.json",
        "need-input-1.0.0.schema.json",
        "confirmation-grant-1.0.0.schema.json",
        "change-event-1.0.0.schema.json",
        "error-1.0.0.schema.json",
    ],
)
def test_exported_json_schema_is_valid(filename: str) -> None:
    schema = json.loads((SCHEMAS / filename).read_text())
    Draft202012Validator.check_schema(schema)


def test_compatible_patch_schema_version_is_accepted_but_other_minor_is_not() -> None:
    assert IntentEnvelope.model_validate(envelope(schema_version="1.0.9")).schema_version == "1.0.9"
    with pytest.raises(ValidationError):
        IntentEnvelope.model_validate(envelope(schema_version="1.1.0"))


@given(st.text(min_size=257, max_size=300))
def test_oversized_idempotency_keys_are_rejected(value: str) -> None:
    with pytest.raises(ValidationError):
        IntentEnvelope.model_validate(envelope(idempotency_key=value))
