"""Harness-side observability sink using the shared event contract."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

_SECRET_KEY = re.compile(
    r"(?:password|passwd|secret|token|api[_-]?key|credential|authorization|cookie|card)",
    re.I,
)
_SECRET = re.compile(
    r"(?i)(?:password|secret|token|api[_-]?key|authorization|cookie)\s*[:=]\s*[^\s,;]+"
)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(r"(?<!\w)(?:\+?\d[\d .()/-]{7,}\d)(?!\w)")
_CARD = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_URL = re.compile(r"https?://[^\s]+", re.I)


class AuditUnavailable(RuntimeError):
    pass


class ObservabilitySink(Protocol):
    def emit_normal(self, observation: Observation) -> bool: ...

    def emit_critical(self, observation: Observation) -> int: ...


@dataclass(frozen=True)
class Observation:
    trace_id: UUID
    span_id: UUID
    event_type: str
    component: str
    phase: str
    status: str
    summary: str
    metadata: dict[str, Any]
    occurred_at: datetime
    sequence: int = 0
    parent_span_id: UUID | None = None
    job_id: UUID | None = None
    session_id: str | None = None
    turn_id: str | None = None
    profile: str | None = None
    criticality: str = "normal"
    side_effect_class: str = "none"
    confirmation_state: str = "not_required"
    error_code: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    event_id: UUID | None = None

    def with_id(self) -> Observation:
        return Observation(**{**self.__dict__, "event_id": self.event_id or uuid4()})


def emit_observation(
    sink: ObservabilitySink | None,
    *,
    trace_id: UUID,
    event_type: str,
    component: str,
    phase: str,
    status: str,
    summary: str,
    metadata: dict[str, Any] | None = None,
    job_id: UUID | None = None,
    session_id: str | None = None,
    profile: str | None = None,
    critical: bool = False,
    side_effect_class: str = "none",
    span_id: UUID | None = None,
    occurred_at: datetime | None = None,
) -> None:
    if sink is None:
        return
    item = Observation(
        trace_id=trace_id,
        span_id=span_id or uuid4(),
        job_id=job_id,
        session_id=session_id,
        profile=profile,
        event_type=event_type,
        component=component,
        phase=phase,
        status=status,
        summary=summary[:160],
        metadata=sanitize(metadata or {}),
        occurred_at=occurred_at or datetime.now(UTC),
        criticality="critical" if critical else "normal",
        side_effect_class=side_effect_class,
    )
    if critical or side_effect_class != "none":
        sink.emit_critical(item)
    else:
        sink.emit_normal(item)


def emit_job_observation(
    sink: ObservabilitySink | None,
    *,
    job_id: str,
    event_type: str,
    component: str,
    phase: str,
    status: str,
    summary: str,
    metadata: dict[str, Any] | None = None,
    critical: bool = False,
) -> UUID:
    trace_id = _as_uuid(job_id)
    job_uuid: UUID | None
    try:
        job_uuid = UUID(job_id)
    except (ValueError, AttributeError):
        job_uuid = None
    emit_observation(
        sink,
        trace_id=trace_id,
        event_type=event_type,
        component=component,
        phase=phase,
        status=status,
        summary=summary,
        metadata=metadata,
        job_id=job_uuid,
        critical=critical,
    )
    return trace_id


def _as_uuid(value: str) -> UUID:
    try:
        return UUID(value)
    except (ValueError, AttributeError):
        return uuid5(NAMESPACE_URL, f"hermes-observability:{value}")


def sanitize(value: Any, *, _key: str = "") -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, nested in value.items():
            normalized = str(key).lower()
            result[str(key)] = sanitize(nested, _key=normalized)
        return result
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        if _SECRET_KEY.search(_key):
            return "[REDACTED]"
        try:
            parts = urlsplit(value)
        except ValueError:
            parts = None
        if parts is not None and parts.scheme in {"http", "https"} and parts.netloc:
            return urlunsplit((parts.scheme, parts.netloc, parts.path or "/", "", ""))
        def strip_url(match: re.Match[str]) -> str:
            try:
                url = urlsplit(match.group(0))
            except ValueError:
                return "[REDACTED_URL]"
            return urlunsplit((url.scheme, url.netloc, url.path or "/", "", ""))

        text = _URL.sub(strip_url, value)
        text = _SECRET.sub("[REDACTED]", text)
        text = _EMAIL.sub("[REDACTED_EMAIL]", text)
        text = _PHONE.sub("[REDACTED_PHONE]", text)
        return _CARD.sub("[REDACTED_CARD]", text)
    return value


class SQLiteObservabilitySink:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._dropped_normal = 0
        self._migrate()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _migrate(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL, span_id TEXT NOT NULL,
                    parent_span_id TEXT, job_id TEXT, session_id TEXT, turn_id TEXT, profile TEXT,
                    event_type TEXT NOT NULL, component TEXT NOT NULL, phase TEXT NOT NULL,
                    status TEXT NOT NULL, criticality TEXT NOT NULL,
                    side_effect_class TEXT NOT NULL,
                    confirmation_state TEXT NOT NULL, occurred_at TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    summary TEXT NOT NULL, metadata_json TEXT NOT NULL, error_code TEXT,
                    error_type TEXT, error_message TEXT, event_digest TEXT NOT NULL,
                    UNIQUE(trace_id, span_id, sequence)
                );
                CREATE INDEX IF NOT EXISTS harness_events_trace_idx ON events(trace_id, event_id);
                CREATE INDEX IF NOT EXISTS harness_events_job_idx ON events(job_id, event_id);
                COMMIT;
                """
            )

    @staticmethod
    def _safe(observation: Observation) -> tuple[Observation, str]:
        item = observation.with_id()
        safe_metadata = sanitize(item.metadata)
        safe_error = sanitize(item.error_message) if item.error_message else None
        safe_error_text = str(safe_error)[:512] if safe_error is not None else None
        safe_summary = sanitize(item.summary)
        clean = Observation(
            **{
                **item.__dict__,
                "metadata": safe_metadata,
                "summary": safe_summary if isinstance(safe_summary, str) else "[REDACTED]",
                "error_message": safe_error_text,
            }
        )
        canonical = json.dumps(clean.__dict__, default=str, sort_keys=True, separators=(",", ":"))
        return clean, hashlib.sha256(canonical.encode()).hexdigest()

    def emit_normal(self, observation: Observation) -> bool:
        try:
            self._append(observation)
            return True
        except Exception:
            with self._lock:
                self._dropped_normal += 1
            return False

    def emit_critical(self, observation: Observation) -> int:
        try:
            return self._append(observation)
        except Exception as exc:
            raise AuditUnavailable("critical audit event could not be persisted") from exc

    def _append(self, observation: Observation) -> int:
        item, digest = self._safe(observation)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            existing = conn.execute(
                "SELECT event_id,event_digest FROM events "
                "WHERE trace_id=? AND span_id=? AND sequence=?",
                (str(item.trace_id), str(item.span_id), item.sequence),
            ).fetchone()
            if existing:
                if existing["event_digest"] != digest:
                    raise ValueError("observation sequence conflict")
                conn.rollback()
                return (
                    int(existing["event_id"].split("-")[-1], 16)
                    if "-" in existing["event_id"]
                    else 1
                )
            event_id = str(item.event_id)
            conn.execute(
                "INSERT INTO events(event_id,trace_id,span_id,parent_span_id,job_id,"
                "session_id,turn_id,profile,event_type,component,phase,status,criticality,"
                "side_effect_class,confirmation_state,occurred_at,"
                "sequence,summary,metadata_json,error_code,error_type,error_message,event_digest) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    event_id,
                    str(item.trace_id),
                    str(item.span_id),
                    str(item.parent_span_id) if item.parent_span_id else None,
                    str(item.job_id) if item.job_id else None,
                    item.session_id,
                    item.turn_id,
                    item.profile,
                    item.event_type,
                    item.component,
                    item.phase,
                    item.status,
                    item.criticality,
                    item.side_effect_class,
                    item.confirmation_state,
                    item.occurred_at.isoformat(),
                    item.sequence,
                    item.summary[:160],
                    json.dumps(item.metadata, sort_keys=True, separators=(",", ":")),
                    item.error_code,
                    item.error_type,
                    item.error_message,
                    digest,
                ),
            )
            conn.commit()
        return 1

    @property
    def dropped_normal(self) -> int:
        with self._lock:
            return self._dropped_normal

    def trace_events(self, trace_id: UUID, *, limit: int = 200) -> list[dict[str, Any]]:
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE trace_id=? ORDER BY rowid LIMIT ?",
                (str(trace_id), limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def job_events(self, job_id: UUID, *, limit: int = 200) -> list[dict[str, Any]]:
        if not 1 <= limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events WHERE job_id=? ORDER BY rowid LIMIT ?",
                (str(job_id), limit),
            ).fetchall()
        return [dict(row) for row in rows]
