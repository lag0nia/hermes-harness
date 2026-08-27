from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from hermes_harness.delivery import DeliveryEvent, DeliveryEventType, DeliveryRouter
from hermes_harness.observability import (
    AuditUnavailable,
    Observation,
    SQLiteObservabilitySink,
)


def _observation():
    return Observation(
        trace_id=uuid4(),
        span_id=uuid4(),
        event_type="fault.test",
        component="test",
        phase="run",
        status="failed",
        summary="bounded",
        metadata={},
        occurred_at=datetime.now(UTC),
    )


def test_normal_sink_failure_is_fail_open_but_critical_is_fail_closed(tmp_path, monkeypatch):
    sink = SQLiteObservabilitySink(tmp_path / "events.db")

    def fail_append(_observation):
        raise OSError("database unavailable")

    monkeypatch.setattr(sink, "_append", fail_append)
    assert sink.emit_normal(_observation()) is False
    assert sink.dropped_normal == 1
    with pytest.raises(AuditUnavailable):
        sink.emit_critical(_observation())


def test_trace_query_rejects_corrupt_limits(tmp_path):
    sink = SQLiteObservabilitySink(tmp_path / "events.db")
    with pytest.raises(ValueError):
        sink.trace_events(uuid4(), limit=0)
    with pytest.raises(ValueError):
        sink.trace_events(uuid4(), limit=201)


def test_disconnected_delivery_is_recorded_without_message_delivery(tmp_path):
    sink = SQLiteObservabilitySink(tmp_path / "events.db")
    router = DeliveryRouter(observability=sink)
    router.set_connected("desktop", False)
    router.set_connected("telegram", False)
    job_id = str(uuid4())
    assert router.route(
        [DeliveryEvent(job_id, "desktop", DeliveryEventType.TERMINAL, "failed", critical=True)]
    ) == []
    assert len(sink.job_events(UUID(job_id))) == 2
