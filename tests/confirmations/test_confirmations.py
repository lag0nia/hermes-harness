from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from hermes_harness.control_plane.confirmations import (
    ConfirmationDigestMismatch,
    ConfirmationExpired,
    ConfirmationManager,
    ConfirmationUsed,
)
from hermes_harness.control_plane.contracts import IntentEnvelope
from hermes_harness.control_plane.ledger import Ledger
from tests.contracts.test_intent import envelope


def operation(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "operation": "checkout.submit",
        "target": "Restaurante Ejemplo",
        "amount": "23.40 EUR",
        "options": {"size": "large"},
        "destination": "home-address-id",
        "external_state_version": "cart-v1",
    }
    value.update(overrides)
    return value


def setup_manager(path: Path) -> tuple[ConfirmationManager, str]:
    ledger = Ledger(path)
    job = ledger.create_job(IntentEnvelope.model_validate(envelope()))
    return ConfirmationManager(path), str(job.job_id)


def test_exact_digest_confirmation_is_single_use_across_restart(tmp_path: Path) -> None:
    path = tmp_path / "ledger.db"
    manager, job_id = setup_manager(path)
    now = datetime.now(UTC)
    preview = manager.issue(job_id, operation(), now=now)
    restarted = ConfirmationManager(path)
    restarted.consume(
        preview.confirmation_id,
        preview.digest,
        operation(),
        now=now + timedelta(minutes=1),
    )
    with pytest.raises(ConfirmationUsed):
        restarted.consume(
            preview.confirmation_id,
            preview.digest,
            operation(),
            now=now + timedelta(minutes=2),
        )


def test_stale_or_modified_external_state_invalidates_confirmation(tmp_path: Path) -> None:
    manager, job_id = setup_manager(tmp_path / "ledger.db")
    now = datetime.now(UTC)
    preview = manager.issue(job_id, operation(), now=now)
    with pytest.raises(ConfirmationDigestMismatch):
        manager.consume(
            preview.confirmation_id,
            preview.digest,
            operation(amount="24.00 EUR"),
            now=now + timedelta(minutes=1),
        )
    with pytest.raises(ConfirmationDigestMismatch):
        manager.consume(
            preview.confirmation_id,
            preview.digest,
            operation(external_state_version="cart-v2"),
            now=now + timedelta(minutes=1),
        )
    with pytest.raises(ConfirmationExpired):
        manager.consume(
            preview.confirmation_id,
            preview.digest,
            operation(),
            now=now + timedelta(minutes=31),
        )
