"""Exact, expiring, single-use confirmation grants."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4


class ConfirmationError(ValueError):
    pass


class ConfirmationExpired(ConfirmationError):
    pass


class ConfirmationDigestMismatch(ConfirmationError):
    pass


class ConfirmationUsed(ConfirmationError):
    pass


_REQUIRED_FIELDS = {
    "operation",
    "target",
    "amount",
    "options",
    "destination",
    "external_state_version",
}


@dataclass(frozen=True)
class ConfirmationPreview:
    confirmation_id: UUID
    job_id: UUID
    digest: str
    expires_at: datetime


class ConfirmationManager:
    def __init__(self, path: Path) -> None:
        self.path = path

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    @staticmethod
    def digest(operation: dict[str, Any]) -> str:
        if set(operation) != _REQUIRED_FIELDS:
            missing = sorted(_REQUIRED_FIELDS - operation.keys())
            extra = sorted(operation.keys() - _REQUIRED_FIELDS)
            raise ConfirmationDigestMismatch(
                f"confirmation fields mismatch: missing={missing}, extra={extra}"
            )
        canonical = json.dumps(operation, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(canonical.encode()).hexdigest()

    def issue(
        self,
        job_id: str | UUID,
        operation: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> ConfirmationPreview:
        issued_at = now or datetime.now(UTC)
        if issued_at.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        confirmation_id = uuid4()
        digest = self.digest(operation)
        expires_at = issued_at + timedelta(minutes=30)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """INSERT INTO confirmations(
                    confirmation_id,job_id,digest,operation_json,external_state_version,
                    issued_at,expires_at
                ) VALUES (?,?,?,?,?,?,?)""",
                (
                    str(confirmation_id),
                    str(job_id),
                    digest,
                    json.dumps(
                        operation, sort_keys=True, separators=(",", ":"), ensure_ascii=False
                    ),
                    str(operation["external_state_version"]),
                    issued_at.isoformat(),
                    expires_at.isoformat(),
                ),
            )
            connection.commit()
        return ConfirmationPreview(confirmation_id, UUID(str(job_id)), digest, expires_at)

    def consume(
        self,
        confirmation_id: str | UUID,
        expected_digest: str,
        current_operation: dict[str, Any],
        *,
        now: datetime | None = None,
    ) -> None:
        consumed_at = now or datetime.now(UTC)
        if consumed_at.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        current_digest = self.digest(current_operation)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM confirmations WHERE confirmation_id=?", (str(confirmation_id),)
            ).fetchone()
            if row is None:
                connection.rollback()
                raise ConfirmationDigestMismatch("unknown confirmation")
            if row["used_at"] is not None:
                connection.rollback()
                raise ConfirmationUsed("confirmation callback was already consumed")
            expires_at = datetime.fromisoformat(row["expires_at"])
            if consumed_at >= expires_at:
                connection.rollback()
                raise ConfirmationExpired("confirmation expired after 30 minutes")
            if not hmac.compare_digest(row["digest"], expected_digest) or not hmac.compare_digest(
                row["digest"], current_digest
            ):
                connection.rollback()
                raise ConfirmationDigestMismatch("operation or external state changed")
            updated = connection.execute(
                "UPDATE confirmations SET used_at=? WHERE confirmation_id=? AND used_at IS NULL",
                (consumed_at.isoformat(), str(confirmation_id)),
            )
            if updated.rowcount != 1:
                connection.rollback()
                raise ConfirmationUsed("confirmation callback was already consumed")
            connection.commit()
