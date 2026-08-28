from hermes_harness.control_plane.message_router import (
    RouteDisposition,
    classify_message,
)


def test_log_diagnosis_routes_to_researcher() -> None:
    decision = classify_message("Mira los logs de Uber Eats y dime por qué fallaron")

    assert decision.disposition is RouteDisposition.SPECIALIST
    assert decision.profile == "researcher"
    assert decision.intent == "technical.research"


def test_generic_uber_question_stays_on_default() -> None:
    decision = classify_message("¿Qué es Uber Eats?")

    assert decision.disposition is RouteDisposition.DEFAULT
    assert decision.profile is None
    assert decision.intent is None


def test_technical_change_routes_to_engineer() -> None:
    decision = classify_message("Corrige el bug del bridge MCP")

    assert decision.disposition is RouteDisposition.SPECIALIST
    assert decision.profile == "engineer"
    assert decision.intent == "technical.change"


def test_ambiguous_research_and_change_stays_on_default() -> None:
    decision = classify_message("Revisa los logs y corrige el código si hace falta")

    assert decision.disposition is RouteDisposition.AMBIGUOUS
    assert decision.profile is None
    assert decision.intent is None


def test_accents_and_case_do_not_change_a_strong_match() -> None:
    decision = classify_message("DIAGNÓSTICA la excepción de la integración")

    assert decision.disposition is RouteDisposition.SPECIALIST
    assert decision.profile == "researcher"
    assert decision.intent == "technical.research"


def test_decision_reason_never_contains_the_original_message() -> None:
    message = "Mira los logs con password=super-secret y dime qué pasó"
    decision = classify_message(message)

    assert message not in decision.reason
    assert "super-secret" not in decision.reason
