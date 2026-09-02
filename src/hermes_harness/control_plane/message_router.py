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
    r"\bbridge mcp\b",
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
_DEVELOPMENT_COORDINATE_ACTIONS = (
    r"\bcrea\w*\b",
    r"\bdesarrolla\w*\b",
    r"\bimplementa\w*\b",
)
_DEVELOPMENT_COORDINATE_CONTEXT = (
    r"\bintegracion(?:es)?\b",
    r"\bplugin(?:s)?\b",
    r"\bsistema(?:s)?\b",
)
_ARCHITECT_PLAN_ACTIONS = (
    r"\bcrea\w*\b",
    r"\bdisena\w*\b",
    r"\bplanifica\w*\b",
    r"\bplan\w*\b",
    r"\bdefine\w*\b",
)
_ARCHITECT_PLAN_CONTEXT = (
    r"\barquitectura\w*\b",
    r"\bplan tecnico\w*\b",
)
_CODE_PLAN_ACTIONS = (r"\bplanifica\w*\b", r"\bplan\w*\b")
_CODE_CHANGE_ACTIONS = (r"\bimplementa\w*\b",)
_CODE_REVIEW_ACTIONS = (
    r"\brevisa\w*\b",
    r"\baudita\w*\b",
    r"\binspecciona\w*\b",
    r"\bevalua\w*\b",
)
_CODE_CONTEXT = (
    r"\bcodigo\b",
    r"\bfuncion(?:es)?\b",
    r"\bclase(?:s)?\b",
    r"\bmodulo(?:s)?\b",
    r"\barchivo(?:s)?\b",
    r"\brouter\b",
    r"\bscript(?:s)?\b",
)
_TRAVEL_PLAN_ACTIONS = (
    r"\bplanea\w*\b",
    r"\bplanifica\w*\b",
    r"\borganiza\w*\b",
    r"\bprepara\w*\b",
    r"\bplan\w*\b",
    r"\bpregunt\w*\s+por\b",
    r"\borganize\w*\b",
)
_TRAVEL_SEARCH_ACTIONS = (
    r"\bbusca\w*\b",
    r"\bencuentra\w*\b",
    r"\bsearch\w*\b",
    r"\bfind\w*\b",
)
_TRAVEL_CONTEXT = (
    r"\bviaje\w*\b",
    r"\bvuelos?\b",
    r"\bflights?\b",
    r"\balojamiento\b",
    r"\bhoteles?\b",
    r"\bhotels?\b",
    r"\baccommodation\b",
    r"\bstays?\b",
)
_TRAVEL_FLIGHT_CONTEXT = (r"\bvuelos?\b", r"\bflights?\b")
_TRAVEL_STAY_CONTEXT = (
    r"\balojamiento\b",
    r"\bhoteles?\b",
    r"\bhotels?\b",
    r"\baccommodation\b",
    r"\bstays?\b",
)
_BROWSER_ACTIONS = (
    r"\babre\w*\b",
    r"\bejecuta\w*\b",
    r"\binteractua\w*\b",
    r"\brellena\w*\b",
    r"\benvia\w*\b",
    r"\bnaveg(?:a|ar|ando)\b",
    r"\bopen\w*\b",
    r"\binteract\w*\b",
    r"\bfill\w*\b",
    r"\bsubmit\w*\b",
    r"\bnavigate\w*\b",
    r"\bclick\w*\b",
)
_BROWSER_RESEARCH_ACTIONS = (
    r"\binvestiga\w*\b",
    r"\banaliza\w*\b",
    r"\bcompara\w*\b",
    r"\bresearch\w*\b",
    r"\bsearch\w*\b",
    r"\bcompare\w*\b",
    r"\blook up\b",
)
_BROWSER_CONTEXT = (
    r"\bnavegador\b",
    r"\bbrowser\b",
    r"\bformulario\b",
    r"\bforms?\b",
    r"\bpagina web\b",
    r"\bsitio web\b",
    r"\bweb page\b",
    r"\bwebsite\b",
)
_DOCUMENTATION_ACTIONS = (
    r"\bactualiza\w*\b",
    r"\bdocumenta\w*\b",
    r"\bescribe\w*\b",
    r"\breconcilia\w*\b",
    r"\bupdate\w*\b",
    r"\bdocument\w*\b",
    r"\bwrite\w*\b",
    r"\breconcile\w*\b",
)
_DOCUMENTATION_CHANGE_REQUESTS = (r"\bdocumenta\w*\s+(?:el\s+)?cambio\w*\b",)
_DOCUMENTATION_QUERY_ACTIONS = (
    r"\bconsulta\w*\b",
    r"\bquery\w*\b",
    r"\bbusca\w*\b",
    r"\bsearch\w*\b",
    r"\bencuentra\w*\b",
    r"\bfind\w*\b",
    r"\bpregunta\w*\b",
    r"\bask\w*\b",
)
_DOCUMENTATION_CONTEXT = (
    r"\bdocumentacion\b",
    r"\bdocumentation\b",
    r"\bdocs?\b",
    r"\breadme\b",
    r"\bguia\b",
    r"\bmanual\b",
)


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", without_accents.casefold()).strip()


def _matches(text: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(pattern, text) for pattern in patterns)


def _architect_intent(text: str) -> str | None:
    if _matches(text, _ARCHITECT_PLAN_ACTIONS) and _matches(text, _ARCHITECT_PLAN_CONTEXT):
        return "technical.plan"
    return None


def _code_intent(text: str) -> str | None:
    if not _matches(text, _CODE_CONTEXT):
        return None
    if _matches(text, _CODE_CHANGE_ACTIONS):
        return "code.change"
    if _matches(text, _CODE_REVIEW_ACTIONS):
        return "code.review"
    if _matches(text, _CODE_PLAN_ACTIONS):
        return "code.plan"
    return None


def _travel_intent(text: str) -> str | None:
    if _matches(text, _TRAVEL_PLAN_ACTIONS) and _matches(text, _TRAVEL_CONTEXT):
        return "travel.plan"
    if not _matches(text, _TRAVEL_SEARCH_ACTIONS):
        return None
    has_flights = _matches(text, _TRAVEL_FLIGHT_CONTEXT)
    has_stays = _matches(text, _TRAVEL_STAY_CONTEXT)
    if has_flights and has_stays:
        return "travel.plan"
    if has_flights:
        return "travel.search_flights"
    if has_stays:
        return "travel.search_stays"
    return None


def classify_message(text: str) -> MessageRouteDecision:
    """Choose one specialist only when exactly one closed rule matches."""
    normalized = _normalize(text)

    if _matches(normalized, _DEVELOPMENT_COORDINATE_ACTIONS) and _matches(
        normalized, _DEVELOPMENT_COORDINATE_CONTEXT
    ):
        return MessageRouteDecision(
            RouteDisposition.SPECIALIST,
            "default",
            "development.coordinate",
            "one deterministic specialist rule matched",
        )

    candidates: list[tuple[str, str]] = []

    if _matches(normalized, _RESEARCH_ACTIONS) and _matches(normalized, _RESEARCH_EVIDENCE):
        candidates.append(("researcher", "technical.research"))

    if architect_intent := _architect_intent(normalized):
        candidates.append(("architect-planner", architect_intent))

    code_intent = _code_intent(normalized)
    if code_intent:
        candidates.append(("coder", code_intent))

    if travel_intent := _travel_intent(normalized):
        candidates.append(("travel-planner", travel_intent))

    if _matches(normalized, _BROWSER_ACTIONS) and _matches(normalized, _BROWSER_CONTEXT):
        candidates.append(("browser-operator", "browser.form.prepare"))
    elif _matches(normalized, _BROWSER_RESEARCH_ACTIONS) and _matches(
        normalized, _BROWSER_CONTEXT
    ):
        candidates.append(("browser-operator", "browser.research"))

    if _matches(normalized, _DOCUMENTATION_QUERY_ACTIONS) and _matches(
        normalized, _DOCUMENTATION_CONTEXT
    ):
        candidates.append(("documentator", "docs.query"))
    elif (
        _matches(normalized, _DOCUMENTATION_ACTIONS)
        and _matches(normalized, _DOCUMENTATION_CONTEXT)
    ) or _matches(normalized, _DOCUMENTATION_CHANGE_REQUESTS):
        candidates.append(("documentator", "docs.reconcile"))

    engineer_action = _matches(normalized, _ENGINEER_CHANGE_ACTIONS) or (
        _matches(normalized, _ENGINEER_REVIEW_ACTIONS)
        and _matches(normalized, _ENGINEER_CONTEXT)
    )
    if code_intent is None and engineer_action and _matches(normalized, _ENGINEER_CONTEXT):
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
