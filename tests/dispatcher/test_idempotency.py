import sqlite3
from pathlib import Path

import pytest

from hermes_harness.control_plane.contracts import IntentEnvelope
from hermes_harness.control_plane.ledger import (
    IdempotencyConflict,
    InvalidTransition,
    JobState,
    Ledger,
)
from tests.contracts.test_intent import envelope


def test_atomic_idempotent_creation_survives_restart_and_maps_origin(tmp_path: Path) -> None:
    path = tmp_path / "ledger.db"
    request = IntentEnvelope.model_validate(envelope())
    first = Ledger(path).create_job(request)
    second = Ledger(path).create_job(request)
    restarted = Ledger(path).get_job(first.job_id)
    assert second.job_id == first.job_id
    assert restarted.origin_session == "telegram:42"
    assert restarted.delivery_target == "telegram:42"
    assert Ledger(path).journal_mode == "wal"


def test_same_idempotency_key_with_different_payload_is_conflict(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.db")
    ledger.create_job(IntentEnvelope.model_validate(envelope()))
    with pytest.raises(IdempotencyConflict):
        ledger.create_job(IntentEnvelope.model_validate(envelope(intent="calendar.create_event")))


def test_state_machine_cancel_and_atomic_cancel_semantics(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.db")
    ordinary = ledger.create_job(
        IntentEnvelope.model_validate(envelope(idempotency_key="ordinary"))
    )
    ledger.transition(ordinary.job_id, JobState.ADMITTED)
    ledger.transition(ordinary.job_id, JobState.RUNNING)
    ledger.request_cancel(ordinary.job_id, atomic_section=False)
    assert ledger.get_job(ordinary.job_id).state is JobState.CANCELLED

    atomic = ledger.create_job(IntentEnvelope.model_validate(envelope(idempotency_key="atomic")))
    ledger.transition(atomic.job_id, JobState.ADMITTED)
    ledger.transition(atomic.job_id, JobState.RUNNING)
    ledger.request_cancel(atomic.job_id, atomic_section=True)
    assert ledger.get_job(atomic.job_id).state is JobState.VERIFYING
    assert ledger.get_job(atomic.job_id).cancel_requested is True
    ledger.finish_atomic_and_cancel(atomic.job_id, {"read_back": "cart-v2"})
    assert ledger.get_job(atomic.job_id).state is JobState.CANCELLED
    assert ledger.events(atomic.job_id)[-2].payload["read_back"] == "cart-v2"


def test_invalid_transitions_and_event_mutation_are_rejected(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path / "ledger.db")
    job = ledger.create_job(IntentEnvelope.model_validate(envelope()))
    with pytest.raises(InvalidTransition):
        ledger.transition(job.job_id, JobState.SUCCEEDED)
    assert not hasattr(ledger, "execute_for_test")
    with pytest.raises(sqlite3.DatabaseError), sqlite3.connect(ledger.path) as connection:
        connection.execute("UPDATE events SET event_type = 'tampered'")
