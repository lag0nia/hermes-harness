"""Explicit rollout-phase capability policy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .contracts import Intent


class Phase(StrEnum):
    SHADOW = "shadow"
    READ_ONLY = "read_only"
    CONFIRMED_NONCOMMERCIAL = "confirmed_noncommercial"


READ_ONLY_INTENTS = frozenset(
    {
        Intent.GENERAL_ANSWER,
        Intent.GENERAL_CLARIFY,
        Intent.CALENDAR_LIST,
        Intent.PI_HEALTH_READ,
        Intent.PI_JOBS_LIST,
        Intent.BROWSER_RESEARCH,
        Intent.BROWSER_FORM_PREPARE,
        Intent.TRAVEL_PLAN,
        Intent.TRAVEL_SEARCH_FLIGHTS,
        Intent.TRAVEL_SEARCH_STAYS,
        Intent.TECHNICAL_RESEARCH,
        Intent.TECHNICAL_PLAN,
        Intent.TECHNICAL_REVIEW,
        Intent.CODE_PLAN,
        Intent.CODE_REVIEW,
        Intent.DOCS_QUERY,
    }
)

BLOCKED_INTENTS = frozenset(set(Intent) - READ_ONLY_INTENTS)


@dataclass(frozen=True)
class PhaseDecision:
    intent: Intent | str
    phase: Phase
    allowed: bool
    execute: bool
    reason: str


class PhasePolicy:
    """Fail-closed phase gate; shadow records plans but never executes them."""

    read_only_intents = READ_ONLY_INTENTS
    blocked_intents = BLOCKED_INTENTS

    def check(self, intent: Intent | str, phase: Phase | str) -> PhaseDecision:
        try:
            selected_phase = Phase(phase)
        except ValueError:
            return PhaseDecision(intent, Phase.READ_ONLY, False, False, "unknown rollout phase")
        try:
            selected_intent = Intent(intent)
        except ValueError:
            return PhaseDecision(intent, selected_phase, False, False, "unknown intent")
        if selected_phase is Phase.SHADOW:
            return PhaseDecision(
                selected_intent,
                selected_phase,
                True,
                False,
                "shadow records the plan and forbids execution",
            )
        if selected_intent in self.read_only_intents:
            return PhaseDecision(
                selected_intent,
                selected_phase,
                True,
                selected_phase is Phase.READ_ONLY,
                "explicit read-only capability",
            )
        return PhaseDecision(
            selected_intent,
            selected_phase,
            False,
            False,
            "intent is blocked in the initial phase",
        )


__all__ = ["BLOCKED_INTENTS", "READ_ONLY_INTENTS", "Phase", "PhaseDecision", "PhasePolicy"]
