from datetime import UTC, datetime
from uuid import uuid4

from hermes_harness.observability import Observation, SQLiteObservabilitySink


def test_sink_uses_wal_and_limits_queries(tmp_path) -> None:
    sink = SQLiteObservabilitySink(tmp_path / "observability.sqlite3")
    assert sink._connect().execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    trace = uuid4()
    sink.emit_normal(
        Observation(
            trace,
            uuid4(),
            "test",
            "test",
            "run",
            "success",
            "ok",
            {"token": "secret"},
            datetime.now(UTC),
        )
    )
    rows = sink.trace_events(trace)
    assert len(rows) == 1
    assert "secret" not in rows[0]["metadata_json"]


def test_critical_sink_failure_is_fail_closed(tmp_path) -> None:
    sink = SQLiteObservabilitySink(tmp_path / "observability.sqlite3")
    sink._append = lambda _event: (_ for _ in ()).throw(OSError("down"))  # type: ignore[method-assign]
    import pytest

    from hermes_harness.observability import AuditUnavailable

    with pytest.raises(AuditUnavailable):
        sink.emit_critical(
            Observation(
                uuid4(),
                uuid4(),
                "audit",
                "test",
                "run",
                "pending",
                "audit",
                {},
                datetime.now(UTC),
                criticality="critical",
            )
        )
