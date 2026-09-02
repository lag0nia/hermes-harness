import pytest

from hermes_harness.control_plane.message_router import (
    RouteDisposition,
    classify_message,
)


def test_log_diagnosis_routes_to_researcher() -> None:
    decision = classify_message("Mira los logs del servicio y dime por qué fallaron")

    assert decision.disposition is RouteDisposition.SPECIALIST
    assert decision.profile == "researcher"
    assert decision.intent == "technical.research"


def test_mcp_bridge_diagnosis_routes_to_researcher() -> None:
    decision = classify_message("Investiga por qué falla el bridge MCP")

    assert decision.disposition is RouteDisposition.SPECIALIST
    assert decision.profile == "researcher"
    assert decision.intent == "technical.research"


def test_generic_commerce_question_stays_on_default() -> None:
    decision = classify_message("¿Qué es este servicio?")

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


@pytest.mark.parametrize(
    ("message", "profile", "intent"),
    [
        ("crear un plugin para el sistema", "default", "development.coordinate"),
        ("vamos a desarrollar una nueva integración", "default", "development.coordinate"),
        (
            "IMPLEMENTA una integración y revisa los logs",
            "default",
            "development.coordinate",
        ),
        (
            "DISEÑA la arquitectura y el plan técnico del servicio",
            "architect-planner",
            "technical.plan",
        ),
        ("PLANIFICA el código del router", "coder", "code.plan"),
        ("IMPLEMENTA la función de autenticación", "coder", "code.change"),
        ("REVISA el código del router", "coder", "code.review"),
        ("Corrige el bug del router", "engineer", "technical.change"),
        ("Consulta la documentación del README", "documentator", "docs.query"),
        ("Abre el navegador y rellena el formulario", "browser-operator", "browser.form.prepare"),
        ("Planea un viaje a Lisboa", "travel-planner", "travel.plan"),
        ("Pregunto por viajes a Lisboa", "travel-planner", "travel.plan"),
        (
            "Ejecuta una interacción con el navegador",
            "browser-operator",
            "browser.form.prepare",
        ),
        ("Documenta el cambio", "documentator", "docs.reconcile"),
    ],
)
def test_classification_contract_matrix(
    message: str, profile: str, intent: str
) -> None:
    decision = classify_message(message)

    assert decision.disposition is RouteDisposition.SPECIALIST
    assert decision.profile == profile
    assert decision.intent == intent


@pytest.mark.parametrize("message", ["Pregunto por el navegador", "Escribe el cambio"])
def test_generic_question_and_writing_stay_on_default(message: str) -> None:
    decision = classify_message(message)

    assert decision.disposition is RouteDisposition.DEFAULT
    assert decision.profile is None
    assert decision.intent is None


@pytest.mark.parametrize(
    ("message", "intent"),
    [
        ("Planea un viaje a Lisboa con vuelos y alojamiento", "travel.plan"),
        ("SEARCH FLIGHTS to Lisbon", "travel.search_flights"),
        ("Busca ALOJAMIENTO en Lisboa", "travel.search_stays"),
    ],
)
def test_explicit_travel_chooses_the_matching_travel_intent(
    message: str, intent: str
) -> None:
    decision = classify_message(message)

    assert decision.disposition is RouteDisposition.SPECIALIST
    assert decision.profile == "travel-planner"
    assert decision.intent == intent


@pytest.mark.parametrize(
    ("message", "intent"),
    [
        ("Abre el navegador y rellena el formulario", "browser.form.prepare"),
        ("RESEARCH supplier prices in the BROWSER", "browser.research"),
    ],
)
def test_explicit_browser_work_chooses_the_matching_browser_intent(
    message: str, intent: str
) -> None:
    decision = classify_message(message)

    assert decision.disposition is RouteDisposition.SPECIALIST
    assert decision.profile == "browser-operator"
    assert decision.intent == intent


@pytest.mark.parametrize(
    ("message", "intent"),
    [
        ("Actualiza la documentación del README", "docs.reconcile"),
        ("QUERY the API documentation", "docs.query"),
    ],
)
def test_explicit_documentation_work_chooses_the_matching_documentation_intent(
    message: str, intent: str
) -> None:
    decision = classify_message(message)

    assert decision.disposition is RouteDisposition.SPECIALIST
    assert decision.profile == "documentator"
    assert decision.intent == intent
