"""Injectable, deterministic Observe-Decide-Act-Verify-Recover browser operator.

This module deliberately knows nothing about a browser vendor or credentials.  An adapter
supplies sanitized observations and actions, making replay tests safe by construction.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID, uuid4

from hermes_harness.observability import ObservabilitySink, emit_observation


class Risk(StrEnum):
    REVERSIBLE = "reversible"
    PERSISTENT = "persistent"
    CRITICAL = "critical"


class Outcome(StrEnum):
    SUCCEEDED = "succeeded"
    NEED_INPUT = "need_input"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(frozen=True)
class Action:
    name: str
    risk: Risk = Risk.REVERSIBLE
    equivalent_key: str | None = None


@dataclass(frozen=True)
class Step:
    action: Action
    confidence: float = 0.75


@dataclass(frozen=True)
class BrowserResult:
    outcome: Outcome
    invalidated_refs: tuple[str, ...] = ()
    logs: tuple[dict[str, Any], ...] = ()
    screenshots: tuple[str, ...] = ()
    sol_reviews: int = 0
    error: str | None = None


class BrowserAdapter(Protocol):
    def observe(self) -> dict[str, Any]: ...
    def act(self, action: Action) -> None: ...
    def verify(self, action: Action, before: dict[str, Any], after: dict[str, Any]) -> bool: ...
    def screenshot(self) -> str: ...
    def delete_screenshot(self, path: str) -> None: ...


class BrowserOperator:
    def __init__(
        self,
        adapter: BrowserAdapter,
        *,
        screenshot_dir: Path | None = None,
        confidence_threshold: float = 0.8,
        sol_review: Callable[[dict[str, Any]], bool] | None = None,
        observability: ObservabilitySink | None = None,
    ) -> None:
        self.adapter = adapter
        self.screenshot_dir = screenshot_dir
        self.confidence_threshold = confidence_threshold
        self.sol_review = sol_review
        self._observability = observability

    @staticmethod
    def _fingerprint(observation: dict[str, Any]) -> str:
        stable = {k: v for k, v in observation.items() if k not in {"timestamp", "screenshot"}}
        return hashlib.sha256(json.dumps(stable, sort_keys=True, default=str).encode()).hexdigest()

    @staticmethod
    def _safe(value: object) -> str:
        text = str(value)
        text = re.sub(
            r"(?i)\b(password|secret|token|credential|authorization|api[_-]?key)\b\s*[:=]\s*\S+",
            "[REDACTED]",
            text,
        )
        return re.sub(
            r"(?i)\b(password|secret|token|credential|authorization|api[_-]?key)\b",
            "[REDACTED]",
            text,
        )

    def run(
        self,
        steps: list[Step],
        *,
        cancel: Callable[[], bool] | None = None,
        trace_id: UUID | None = None,
    ) -> BrowserResult:
        logs: list[dict[str, Any]] = []
        shots: list[str] = []
        invalidated: set[str] = set()
        sol_reviews = 0
        seen_fingerprints: set[str] = set()
        trace = trace_id or uuid4()
        emit_observation(
            self._observability,
            trace_id=trace,
            event_type="browser.lifecycle",
            component="browser-operator",
            phase="observe",
            status="started",
            summary="Browser operation started",
            metadata={"step_count": len(steps)},
        )
        try:
            if cancel and cancel():
                return BrowserResult(Outcome.CANCELLED, (), tuple(logs), (), sol_reviews)
            for step in steps:
                if cancel and cancel():
                    return BrowserResult(
                        Outcome.CANCELLED, tuple(sorted(invalidated)), tuple(logs), ()
                    )
                before = self.adapter.observe()
                fingerprint = self._fingerprint(before)
                if fingerprint in seen_fingerprints:
                    return BrowserResult(
                        Outcome.NEED_INPUT,
                        tuple(sorted(invalidated)),
                        tuple(logs),
                        (),
                        sol_reviews,
                        "cycle_detected",
                    )
                seen_fingerprints.add(fingerprint)
                logs.append({"phase": "observe", "fingerprint": fingerprint})
                if step.confidence < self.confidence_threshold:
                    return BrowserResult(
                        Outcome.NEED_INPUT,
                        tuple(sorted(invalidated)),
                        tuple(logs),
                        (),
                        sol_reviews,
                        "low_confidence",
                    )
                critical_or_conflict = step.action.risk is Risk.CRITICAL or bool(
                    before.get("visual_conflict")
                )
                if critical_or_conflict:
                    if self.sol_review is None:
                        return BrowserResult(
                            Outcome.NEED_INPUT,
                            tuple(sorted(invalidated)),
                            tuple(logs),
                            (),
                            sol_reviews,
                            "review_required",
                        )
                    sol_reviews += 1
                    if not self.sol_review(before):
                        return BrowserResult(
                            Outcome.NEED_INPUT,
                            tuple(sorted(invalidated)),
                            tuple(logs),
                            (),
                            sol_reviews,
                            "review_rejected",
                        )
                path = self.adapter.screenshot()
                shots.append(path)
                self.adapter.act(step.action)
                invalidated.update(str(k) for k in before.get("refs", {}))
                after = self.adapter.observe()
                logs.append({"phase": "verify", "fingerprint": self._fingerprint(after)})
                if self.adapter.verify(step.action, before, after):
                    continue
                if step.action.risk is not Risk.REVERSIBLE:
                    return BrowserResult(
                        Outcome.NEED_INPUT,
                        tuple(sorted(invalidated)),
                        tuple(logs),
                        (),
                        sol_reviews,
                        "verification_failed",
                    )
                # Exactly one equivalent retry, never an unbounded no-op loop.
                self.adapter.act(
                    Action(
                        step.action.name,
                        step.action.risk,
                        step.action.equivalent_key or step.action.name,
                    )
                )
                invalidated.update(str(k) for k in after.get("refs", {}))
                final = self.adapter.observe()
                if not self.adapter.verify(step.action, after, final):
                    return BrowserResult(
                        Outcome.NEED_INPUT,
                        tuple(sorted(invalidated)),
                        tuple(logs),
                        (),
                        sol_reviews,
                        "verification_failed",
                    )
            return BrowserResult(
                Outcome.SUCCEEDED, tuple(sorted(invalidated)), tuple(logs), (), sol_reviews
            )
        except Exception as exc:
            logs.append({"phase": "recover", "error": self._safe(exc)})
            return BrowserResult(
                Outcome.FAILED,
                tuple(sorted(invalidated)),
                tuple(logs),
                (),
                sol_reviews,
                "adapter_failure",
            )
        finally:
            for path in shots:
                try:
                    self.adapter.delete_screenshot(path)
                    candidate = Path(path)
                    if candidate.exists() and (
                        self.screenshot_dir is None or candidate.parent == self.screenshot_dir
                    ):
                        candidate.unlink()
                except Exception:
                    pass
            emit_observation(
                self._observability,
                trace_id=trace,
                event_type="browser.cleanup",
                component="browser-operator",
                phase="cleanup",
                status="completed",
                summary="Browser screenshots cleaned up",
                metadata={"screenshot_count": len(shots)},
            )
