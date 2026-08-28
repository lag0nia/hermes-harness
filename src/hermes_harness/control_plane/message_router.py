"""Conservative deterministic routing for inbound user messages."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum


class RouteDisposition(StrEnum):
    """What the ingress router should do with a message."""

    DEFAULT = "default"
    SPECIALIST = "specialist"
    AMBIGUOUS = "ambiguous"


@dataclass(frozen=True)
class MessageRouteDecision:
    """Sanitized routing decision; it deliberately does not retain user text."""

    disposition: RouteDisposition
    profile: str | None
    intent: str | None
    reason: str


_RESEARCH_ACTIONS = (
    r"\bmira\b",
    r"\brevisa\b",
    r"\binvestiga\w*\b",
    r"\banaliza\w*\b",
    r"\bdiagnostica\w*\b",
    r"\bcomprueba\w*\b",
    r"\baverigua\w*\b",
    r"\bexplica\w*\b",
    r"\bpor que\b",
    r"\bque paso\b",
    r"\bque ha pasado\b",
)
_RESEARCH_EVIDENCE = (
    r"\blogs?\b",
    r"\bregistros?\b",
    r"\btrazas?\b",
    r"\berror(?:es)?\b",
    r"\bfallo(?:s)?\b",
    r"\bexcepcion(?:es)?\b",
    r"\bstack trace\b",
    r"\bcrash(?:es)?\b",
)
_ENGINEER_CHANGE_ACTIONS = (
    r"\bcorrige\w*\b",
    r"\barregla\w*\b",
    r"\bimplementa\w*\b",
    r"\bmodifica\w*\b",
    r"\bcambia\w*\b",
    r"\bconfigura\w*\b",
    r"\brepara\w*\b",
)
_ENGINEER_REVIEW_ACTIONS = (
    r"\brevisa\w*\b",
    r"\baudita\w*\b",
    r"\binspecciona\w*\b",
    r"\bevalua\w*\b",
)
_ENGINEER_CONTEXT = (
    r"\bcodigo\b",
    r"\bimplementacion\b",
    r"\bconfiguracion\b",
    r"\bbridge\b",
    r"\brouter\b",
    r"\bmcp\b",
    r"\bplugin(?:s)?\b",
    r"\btest(?:s)?\b",
    r"\bintegracion\b",
    r"\bsistema\b",
    r"\bbug\b",
)


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", without_accents.casefold()).strip()


def _matches(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def classify_message(text: str) -> MessageRouteDecision:
    """Choose one specialist only when exactly one closed rule matches."""
    normalized = _normalize(text)
    candidates: list[tuple[str, str]] = []

    if _matches(normalized, _RESEARCH_ACTIONS) and _matches(normalized, _RESEARCH_EVIDENCE):
        candidates.append(("researcher", "technical.research"))

    engineer_action = _matches(normalized, _ENGINEER_CHANGE_ACTIONS) or (
        _matches(normalized, _ENGINEER_REVIEW_ACTIONS)
        and _matches(normalized, _ENGINEER_CONTEXT)
    )
    if engineer_action and _matches(normalized, _ENGINEER_CONTEXT):
        candidates.append(("engineer", "technical.change"))

    if not candidates:
        return MessageRouteDecision(
            RouteDisposition.DEFAULT,
            None,
            None,
            "no unique specialist rule matched",
        )
    if len(candidates) > 1:
        return MessageRouteDecision(
            RouteDisposition.AMBIGUOUS,
            None,
            None,
            "multiple specialist rules matched",
        )
    profile, intent = candidates[0]
    return MessageRouteDecision(
        RouteDisposition.SPECIALIST,
        profile,
        intent,
        "one deterministic specialist rule matched",
    )


__all__ = ["MessageRouteDecision", "RouteDisposition", "classify_message"]
