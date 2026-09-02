import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from hermes_harness import observability_review_runner as runner
from hermes_harness.observability_review import ReviewExecutionBlocked


def test_missing_gateway_records_blocked_run_without_ticket_or_cursor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plugin_source = Path(
        os.environ.get(
            "HERMES_OBSERVABILITY_SOURCE",
            Path(__file__).resolve().parents[3] / "plugin-src" / "hermes-observability",
        )
    )
    monkeypatch.syspath_prepend(str(plugin_source / "src"))
    from hermes_observability.events import make_event
    from hermes_observability.storage import EventStore

    db_path = tmp_path / "events.sqlite3"
    store = EventStore(db_path)
    store.append(
        make_event(
            trace_id=uuid4(),
            span_id=uuid4(),
            event_type="post_tool_call",
            component="tool",
            phase="execute",
            status="failed",
            summary="tool execution failed",
            occurred_at=datetime.now(UTC),
            metadata={"tool_name": "example"},
            error_code="broker_unavailable",
            error_type="URLError",
        )
    )
    monkeypatch.setenv("HERMES_OBSERVABILITY_DB", str(db_path))
    monkeypatch.delenv("HERMES_OBSERVABILITY_GATEWAY_RPC_COMMAND", raising=False)

    def missing_gateway():
        raise ReviewExecutionBlocked("gateway bridge is not configured")

    monkeypatch.setattr(runner, "configured_gateway_review_executor", missing_gateway)

    with pytest.raises(ReviewExecutionBlocked, match="gateway bridge"):
        runner.run_review(now=datetime.now(UTC))

    with store._connect() as conn:
        run_rows = conn.execute("SELECT status FROM review_runs").fetchall()
        ticket_count = conn.execute("SELECT COUNT(*) FROM review_tickets").fetchone()[0]
    assert [row["status"] for row in run_rows] == ["blocked"]
    assert ticket_count == 0
    assert store.get_review_cursor("observability-architect-planner-v1").last_event_id == 0
