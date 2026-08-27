"""Safe shadow observations with one authoritative legacy gate.

This module is deliberately side-effect free with respect to live sessions: it writes
only an append-only observation log containing sanitized user text and small decisions.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:token|password|contraseña|secret|clave|api[_ -]?key)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)\b(?:authorization|bearer)\s*[:=]?\s*[^\s,;]+"),
    re.compile(r"\b\d{12,19}\b"),
)
_STAGES = {"shadow": 0, "read_only": 1, "promotion": 2}


def sanitize_user_text(text: str) -> str:
    """Remove secret-shaped values without retaining the original value."""
    if not isinstance(text, str):
        raise TypeError("user text must be a string")
    result = text
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub("[REDACTED]", result)
    return result


class KillSwitch:
    """The sole promotion gate; tripping it is fail-closed and irreversible."""

    def __init__(self) -> None:
        self._stage = _STAGES["promotion"]
        self._reason: str | None = None

    @property
    def tripped(self) -> bool:
        return self._reason is not None

    @property
    def reason(self) -> str | None:
        return self._reason

    @property
    def stage(self) -> str:
        return next(name for name, value in _STAGES.items() if value == self._stage)

    def allows(self, stage: str) -> bool:
        if stage not in _STAGES:
            raise ValueError(f"unknown rollout stage: {stage}")
        return not self.tripped and _STAGES[stage] <= self._stage

    def rollback_to(self, stage: str) -> None:
        if stage not in _STAGES:
            raise ValueError(f"unknown rollout stage: {stage}")
        self._stage = min(self._stage, _STAGES[stage])

    def trip(self, reason: str) -> None:
        if not reason.strip():
            raise ValueError("kill switch reason is required")
        self._reason = reason


@dataclass(frozen=True)
class ShadowDecision:
    user_text: str
    legacy_decision: Any
    candidate_decision: Any
    authoritative_path: str
    outcome: str
    policy_violations: int = 0


class ShadowLogger:
    """Compare candidate routing while legacy remains authoritative."""

    def __init__(self, path: Path, kill_switch: KillSwitch | None = None) -> None:
        self.path = path
        self.kill_switch = kill_switch or KillSwitch()
        self._metrics = {"observations": 0, "matches": 0, "divergences": 0, "policy_violations": 0}

    @property
    def metrics(self) -> dict[str, int]:
        return dict(self._metrics)

    def observe(
        self,
        user_text: str,
        *,
        legacy_decider: Callable[[str], Any],
        candidate_decider: Callable[[str], Any],
    ) -> ShadowDecision:
        if not self.kill_switch.allows("shadow"):
            raise RuntimeError("shadow logging disabled by kill switch")
        safe_text = sanitize_user_text(user_text)
        legacy = legacy_decider(safe_text)
        candidate = candidate_decider(safe_text)
        outcome = "match" if legacy == candidate else "divergence"
        decision = ShadowDecision(
            safe_text, _safe_summary(legacy), _safe_summary(candidate), "legacy", outcome
        )
        self._metrics["observations"] += 1
        self._metrics["matches" if outcome == "match" else "divergences"] += 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(asdict(decision), ensure_ascii=False, sort_keys=True) + "\n")
        return decision


def _safe_summary(value: Any) -> Any:
    if isinstance(value, dict):
        allowed = {key: value[key] for key in ("intent", "category", "status") if key in value}
        return {str(key): _safe_summary(item) for key, item in allowed.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value if not isinstance(value, str) else sanitize_user_text(value)
    if isinstance(value, list):
        return [_safe_summary(item) for item in value[:20]]
    return str(type(value).__name__)
