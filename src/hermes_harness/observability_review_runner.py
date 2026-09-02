"""Entrypoint for the reconciliable two-day observability review cron job.

It deliberately performs no work unless both the plugin package and the
configured JSON-RPC gateway bridge are available.  A failed invocation leaves
the plugin cursor untouched, so the next official Hermes cron tick can retry.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from importlib import import_module
from typing import Any

from .observability_review import (
    ReviewExecutionBlocked,
    build_review_envelope,
    configured_gateway_review_executor,
)


def run_review(*, now: datetime | None = None) -> dict[str, object]:
    """Execute one bounded review through the installed plugin contracts."""
    try:
        contracts: Any = import_module("hermes_observability.review_contracts")
        controller_module: Any = import_module("hermes_observability.review_controller")
        tools: Any = import_module("hermes_observability.tools")
    except ImportError as exc:
        raise ReviewExecutionBlocked(
            "installed hermes-observability plugin is required for review runner"
        ) from exc
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    ArchitectReviewDraft: Any = contracts.ArchitectReviewDraft
    FailureReviewController: Any = controller_module.FailureReviewController
    get_store: Any = tools.get_store
    gateway: Any = None
    gateway_error: ReviewExecutionBlocked | None = None
    try:
        gateway = configured_gateway_review_executor()
    except ReviewExecutionBlocked as exc:
        gateway_error = exc
    controller_blocked = controller_module.ReviewExecutionBlocked

    def execute(payload: object) -> Any:
        if gateway_error is not None:
            raise controller_blocked(str(gateway_error))
        if not isinstance(payload, dict):
            raise ReviewExecutionBlocked("review controller supplied an invalid payload")
        run = payload.get("run")
        candidates = payload.get("candidates")
        if run is None or not isinstance(candidates, list):
            raise ReviewExecutionBlocked("review controller omitted bounded candidates")
        envelope = build_review_envelope(
            review_run_id=run.run_id,
            candidate_digest=run.candidate_digest,
            candidates=[item.model_dump(mode="json") for item in candidates],
            origin_session=f"cron:{run.run_id}",
        )
        try:
            return ArchitectReviewDraft.model_validate(
                gateway.execute_read_only(envelope, output_contract="architect-review-draft-1.0.0")
            )
        except ReviewExecutionBlocked as exc:
            raise controller_blocked(str(exc)) from exc

    preflight_error = controller_blocked(str(gateway_error)) if gateway_error is not None else None
    controller = FailureReviewController(get_store(), execute, preflight_error=preflight_error)
    try:
        result = controller.run_once(
            window_start=moment - timedelta(days=2), window_end=moment, execute=True
        )
    except controller_blocked as exc:
        raise ReviewExecutionBlocked(str(exc)) from exc
    return {
        "status": result.status,
        "ticket_count": result.ticket_count,
        "review_run_id": str(result.run.run_id),
        "source_high_watermark": result.run.source_high_watermark,
    }


def main() -> int:
    try:
        print(json.dumps(run_review(), sort_keys=True))
    except (ReviewExecutionBlocked, ValueError) as exc:
        print(
            json.dumps({"status": "blocked", "error": str(exc)[:512]}, sort_keys=True),
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
