import json
from pathlib import Path
from uuid import uuid4

import pytest

from hermes_harness.control_plane.observability_contracts import ObservabilityEvent

PLUGIN_SCHEMA = Path(
    "/opt/data/plugin-src/hermes-observability/contracts/observability-event-1.0.0.schema.json"
)
HARNESS_SCHEMA = Path("contracts/observability-event-1.0.0.schema.json")


def test_contract_schema_copies_are_identical() -> None:
    assert json.loads(PLUGIN_SCHEMA.read_text()) == json.loads(HARNESS_SCHEMA.read_text())


def test_harness_contract_rejects_raw_content_and_naive_time() -> None:
    with pytest.raises(ValueError):
        ObservabilityEvent(
            trace_id=uuid4(),
            span_id=uuid4(),
            event_type="x",
            component="x",
            phase="x",
            status="x",
            occurred_at="2026-01-01T00:00:00",
            metadata={},
        )
    with pytest.raises(ValueError):
        ObservabilityEvent(
            trace_id=uuid4(),
            span_id=uuid4(),
            event_type="x",
            component="x",
            phase="x",
            status="x",
            occurred_at="2026-01-01T00:00:00Z",
            metadata={"prompt": "raw"},
        )
