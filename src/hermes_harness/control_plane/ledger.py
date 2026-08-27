"""Durable SQLite ledger, state projection, and immutable audit log."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import UUID

from hermes_harness.control_plane.contracts import IntentEnvelope


class IdempotencyConflict(ValueError):
    pass


class InvalidTransition(ValueError):
    pass


class JobState(StrEnum):
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


TERMINAL_STATES = {
    JobState.SUCCEEDED,
    JobState.FAILED_FINAL,
    JobState.ROLLED_BACK,
    JobState.CANCELLED,
}
ALLOWED_TRANSITIONS: dict[JobState, set[JobState]] = {
    JobState.QUEUED: {JobState.ADMITTED},
    JobState.ADMITTED: {JobState.RUNNING},
    JobState.RUNNING: {
        JobState.WAITING_INPUT,
        JobState.WAITING_CONFIRMATION,
        JobState.VERIFYING,
        JobState.BLOCKED,
    },
    JobState.WAITING_INPUT: {JobState.RUNNING},
    JobState.WAITING_CONFIRMATION: {JobState.RUNNING, JobState.VERIFYING},
    JobState.BLOCKED: {JobState.RUNNING, JobState.FAILED_FINAL},
    JobState.VERIFYING: {
        JobState.SUCCEEDED,
        JobState.FAILED_RETRYABLE,
        JobState.FAILED_FINAL,
        JobState.ROLLED_BACK,
    },
    JobState.FAILED_RETRYABLE: {JobState.QUEUED, JobState.FAILED_FINAL},
}


@dataclass(frozen=True)
class JobRecord:
    job_id: UUID
    idempotency_key: str
    state: JobState
    origin_profile: str
    origin_session: str
    delivery_target: str
    kanban_task_id: str | None
    cancel_requested: bool


@dataclass(frozen=True)
class LedgerEvent:
    event_id: int
    job_id: UUID
    event_type: str
    state: JobState | None
    payload: dict[str, Any]


class Ledger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _migrate(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(
                """
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    parent_job_id TEXT REFERENCES jobs(job_id),
                    trace_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    payload_digest TEXT NOT NULL,
                    state TEXT NOT NULL,
                    origin_profile TEXT NOT NULL,
                    origin_session TEXT NOT NULL,
                    delivery_target TEXT NOT NULL,
                    intent TEXT NOT NULL,
                    kanban_task_id TEXT,
                    cancel_requested INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL REFERENCES jobs(job_id),
                    event_type TEXT NOT NULL,
                    state TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TRIGGER IF NOT EXISTS events_no_update
                BEFORE UPDATE ON events BEGIN
                    SELECT RAISE(ABORT, 'event log is immutable');
                END;
                CREATE TRIGGER IF NOT EXISTS events_no_delete
                BEFORE DELETE ON events BEGIN
                    SELECT RAISE(ABORT, 'event log is immutable');
                END;
                CREATE TABLE IF NOT EXISTS confirmations (
                    confirmation_id TEXT PRIMARY KEY,
                    job_id TEXT NOT NULL REFERENCES jobs(job_id),
                    digest TEXT NOT NULL,
                    operation_json TEXT NOT NULL,
                    external_state_version TEXT NOT NULL,
                    issued_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used_at TEXT
                );
                INSERT OR IGNORE INTO schema_migrations(version) VALUES (1);
                PRAGMA user_version=1;
                COMMIT;
                """
            )

    @property
    def journal_mode(self) -> str:
        with self._connect() as connection:
            row = connection.execute("PRAGMA journal_mode").fetchone()
            return str(row[0]).lower()

    def create_job(self, envelope: IntentEnvelope) -> JobRecord:
        canonical = json.dumps(
            envelope.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM jobs WHERE idempotency_key=?", (envelope.idempotency_key,)
            ).fetchone()
            if existing is not None:
                connection.rollback()
                if existing["payload_digest"] != digest:
                    raise IdempotencyConflict(
                        "idempotency key was already used for another payload"
                    )
                return self._row_to_job(existing)
            connection.execute(
                """INSERT INTO jobs(
                    job_id,parent_job_id,trace_id,idempotency_key,payload_digest,state,
                    origin_profile,origin_session,delivery_target,intent
                ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    str(envelope.job_id),
                    str(envelope.parent_job_id) if envelope.parent_job_id else None,
                    str(envelope.trace_id),
                    envelope.idempotency_key,
                    digest,
                    JobState.QUEUED.value,
                    envelope.origin_profile,
                    envelope.origin_session,
                    envelope.delivery_target,
                    envelope.intent.value,
                ),
            )
            self._append_event(connection, envelope.job_id, "state", JobState.QUEUED, {})
            connection.commit()
        return self.get_job(envelope.job_id)

    def get_job(self, job_id: UUID) -> JobRecord:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM jobs WHERE job_id=?", (str(job_id),)).fetchone()
        if row is None:
            raise KeyError(str(job_id))
        return self._row_to_job(row)

    def transition(self, job_id: UUID, new_state: JobState) -> JobRecord:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT state FROM jobs WHERE job_id=?", (str(job_id),)
            ).fetchone()
            if row is None:
                connection.rollback()
                raise KeyError(str(job_id))
            current = JobState(row["state"])
            if new_state not in ALLOWED_TRANSITIONS.get(current, set()):
                connection.rollback()
                raise InvalidTransition(f"{current} -> {new_state}")
            self._set_state(connection, job_id, new_state)
            connection.commit()
        return self.get_job(job_id)

    def request_cancel(self, job_id: UUID, *, atomic_section: bool) -> JobRecord:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT state FROM jobs WHERE job_id=?", (str(job_id),)
            ).fetchone()
            if row is None:
                connection.rollback()
                raise KeyError(str(job_id))
            current = JobState(row["state"])
            if current in TERMINAL_STATES:
                connection.rollback()
                raise InvalidTransition(f"cannot cancel terminal job: {current}")
            connection.execute(
                "UPDATE jobs SET cancel_requested=1, updated_at=CURRENT_TIMESTAMP WHERE job_id=?",
                (str(job_id),),
            )
            if atomic_section:
                if current is not JobState.VERIFYING:
                    self._set_state(connection, job_id, JobState.VERIFYING)
            else:
                self._set_state(connection, job_id, JobState.CANCELLED)
            connection.commit()
        return self.get_job(job_id)

    def attach_kanban_task(self, job_id: UUID, task_id: str) -> JobRecord:
        if not task_id.strip():
            raise ValueError("Kanban task id cannot be empty")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT kanban_task_id FROM jobs WHERE job_id=?", (str(job_id),)
            ).fetchone()
            if row is None:
                connection.rollback()
                raise KeyError(str(job_id))
            existing = row["kanban_task_id"]
            if existing is not None and existing != task_id:
                connection.rollback()
                raise ValueError("job already has a different Kanban task")
            if existing is None:
                connection.execute(
                    "UPDATE jobs SET kanban_task_id=?, updated_at=CURRENT_TIMESTAMP WHERE job_id=?",
                    (task_id, str(job_id)),
                )
                self._append_event(
                    connection, job_id, "kanban_attached", None, {"kanban_task_id": task_id}
                )
            connection.commit()
        return self.get_job(job_id)

    def finish_atomic_and_cancel(self, job_id: UUID, read_back: dict[str, Any]) -> JobRecord:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT state,cancel_requested FROM jobs WHERE job_id=?", (str(job_id),)
            ).fetchone()
            if row is None:
                connection.rollback()
                raise KeyError(str(job_id))
            if JobState(row["state"]) is not JobState.VERIFYING or not row["cancel_requested"]:
                connection.rollback()
                raise InvalidTransition("atomic cancellation is not pending")
            self._append_event(connection, job_id, "verification", None, read_back)
            self._set_state(connection, job_id, JobState.CANCELLED)
            connection.commit()
        return self.get_job(job_id)

    def events(self, job_id: UUID) -> list[LedgerEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM events WHERE job_id=? ORDER BY event_id", (str(job_id),)
            ).fetchall()
        return [
            LedgerEvent(
                event_id=row["event_id"],
                job_id=UUID(row["job_id"]),
                event_type=row["event_type"],
                state=JobState(row["state"]) if row["state"] else None,
                payload=json.loads(row["payload_json"]),
            )
            for row in rows
        ]

    @staticmethod
    def _append_event(
        connection: sqlite3.Connection,
        job_id: UUID,
        event_type: str,
        state: JobState | None,
        payload: dict[str, Any],
    ) -> None:
        connection.execute(
            "INSERT INTO events(job_id,event_type,state,payload_json) VALUES (?,?,?,?)",
            (
                str(job_id),
                event_type,
                state.value if state else None,
                json.dumps(payload, sort_keys=True),
            ),
        )

    def _set_state(self, connection: sqlite3.Connection, job_id: UUID, state: JobState) -> None:
        connection.execute(
            "UPDATE jobs SET state=?, updated_at=CURRENT_TIMESTAMP WHERE job_id=?",
            (state.value, str(job_id)),
        )
        self._append_event(connection, job_id, "state", state, {})

    @staticmethod
    def _row_to_job(row: sqlite3.Row) -> JobRecord:
        return JobRecord(
            job_id=UUID(row["job_id"]),
            idempotency_key=row["idempotency_key"],
            state=JobState(row["state"]),
            origin_profile=row["origin_profile"],
            origin_session=row["origin_session"],
            delivery_target=row["delivery_target"],
            kanban_task_id=row["kanban_task_id"],
            cancel_requested=bool(row["cancel_requested"]),
        )
