import pytest

from hermes_harness.control_plane.message_router import (
    RouteDisposition,
    classify_ingress,
    classify_message,
)


def test_log_diagnosis_stays_on_default_without_explicit_delegation() -> None:
    decision = classify_message("Mira los logs del servicio y dime por qué fallaron")

    assert decision.disposition is RouteDisposition.DEFAULT
    assert decision.profile is None
    assert decision.intent is None


def test_mcp_bridge_diagnosis_stays_on_default_without_explicit_delegation() -> None:
    decision = classify_message("Investiga por qué falla el bridge MCP")

    assert decision.disposition is RouteDisposition.DEFAULT
    assert decision.profile is None
    assert decision.intent is None


def test_generic_commerce_question_stays_on_default() -> None:
    decision = classify_message("¿Qué es este servicio?")

    assert decision.disposition is RouteDisposition.DEFAULT
    assert decision.profile is None
    assert decision.intent is None


def test_technical_change_stays_on_default_without_explicit_delegation() -> None:
    decision = classify_message("Corrige el bug del bridge MCP")

    assert decision.disposition is RouteDisposition.DEFAULT
    assert decision.profile is None
    assert decision.intent is None


def test_ambiguous_research_and_change_stays_on_default_without_explicit_delegation() -> None:
    decision = classify_message("Revisa los logs y corrige el código si hace falta")

    assert decision.disposition is RouteDisposition.DEFAULT
    assert decision.profile is None
    assert decision.intent is None


def test_accents_and_case_do_not_change_an_explicit_strong_match() -> None:
    decision = classify_message("Hazlo con Researcher: DIAGNÓSTICA la excepción de la integración")

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
        ("Hazlo con Researcher: mira los logs del servicio", "researcher", "technical.research"),
        (
            "Hazlo con Engineer: IMPLEMENTA una integración",
            "engineer",
            "technical.change",
        ),
        (
            "Hazlo con Researcher: DISEÑA la arquitectura y el plan técnico del servicio",
            "researcher",
            "technical.plan",
        ),
        ("Hazlo con Engineer: PLANIFICA el código del router", "engineer", "code.plan"),
        ("Hazlo con Engineer: IMPLEMENTA la función de autenticación", "engineer", "code.change"),
        ("Hazlo con Engineer: REVISA el código del router", "engineer", "code.review"),
        ("Hazlo con Engineer: Corrige el bug del router", "engineer", "technical.change"),
        (
            "Hazlo con Documentator: Consulta la documentación del README",
            "documentator",
            "docs.query",
        ),
        (
            "Hazlo con Browser Operator: Abre el navegador y rellena el formulario",
            "browser-operator",
            "browser.form.prepare",
        ),
        ("Hazlo con Travel Planner: Planea un viaje a Lisboa", "travel-planner", "travel.plan"),
        ("Hazlo con Travel Planner: Pregunto por viajes a Lisboa", "travel-planner", "travel.plan"),
        (
            "Hazlo con Browser Operator: Ejecuta una interacción con el navegador",
            "browser-operator",
            "browser.form.prepare",
        ),
        ("Hazlo con Documentator: Documenta el cambio", "documentator", "docs.reconcile"),
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
        (
            "Hazlo con Travel Planner: Planea un viaje a Lisboa con vuelos y alojamiento",
            "travel.plan",
        ),
        ("@travel-planner SEARCH FLIGHTS to Lisbon", "travel.search_flights"),
        ("Hazlo con Travel Planner: Busca ALOJAMIENTO en Lisboa", "travel.search_stays"),
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
        (
            "Hazlo con Browser Operator: Abre el navegador y rellena el formulario",
            "browser.form.prepare",
        ),
        ("@browser-operator RESEARCH supplier prices in the BROWSER", "browser.research"),
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
        ("Hazlo con Documentator: Actualiza la documentación del README", "docs.reconcile"),
        ("@documentator QUERY the API documentation", "docs.query"),
    ],
)
def test_explicit_documentation_work_chooses_the_matching_documentation_intent(
    message: str, intent: str
) -> None:
    decision = classify_message(message)

    assert decision.disposition is RouteDisposition.SPECIALIST
    assert decision.profile == "documentator"
    assert decision.intent == intent


def test_explicit_profile_with_an_incompatible_request_fails_closed() -> None:
    decision = classify_message("Hazlo con Travel Planner: implementa el código del router")

    assert decision.disposition is RouteDisposition.AMBIGUOUS
    assert decision.profile is None
    assert decision.intent is None


def test_telegram_travel_request_is_delegated_from_default_without_a_selector() -> None:
    decision = classify_ingress(
        "Quiero viajar en diciembre a Lisboa para dos personas, busca buenas opciones y precio",
        platform="telegram",
        current_profile="default",
    )

    assert decision.disposition is RouteDisposition.SPECIALIST
    assert decision.profile == "travel-planner"
    assert decision.intent == "travel.plan"


def test_desktop_travel_request_stays_on_default_without_a_selector() -> None:
    decision = classify_ingress(
        "Quiero viajar en diciembre a Lisboa para dos personas",
        platform="desktop",
        current_profile="default",
    )

    assert decision.disposition is RouteDisposition.DEFAULT
    assert decision.profile is None
    assert decision.intent is None


def test_telegram_generic_request_stays_on_default() -> None:
    decision = classify_ingress(
        "Explícame cómo funciona Hermes",
        platform="telegram",
        current_profile="default",
    )

    assert decision.disposition is RouteDisposition.DEFAULT
    assert decision.profile is None
    assert decision.intent is None


@pytest.mark.parametrize(
    "message",
    [
        "Corrige el bug del bridge MCP",
        "Abre el navegador y rellena el formulario",
        "Actualiza la documentación del README",
    ],
)
def test_telegram_side_effecting_or_interactive_work_stays_on_default(message: str) -> None:
    decision = classify_ingress(message, platform="telegram", current_profile="default")

    assert decision.disposition is RouteDisposition.DEFAULT
    assert decision.profile is None
    assert decision.intent is None


def test_telegram_ambiguous_request_stays_on_default() -> None:
    decision = classify_ingress(
        "Planea un viaje y además corrige el código del router",
        platform="telegram",
        current_profile="default",
    )

    assert decision.disposition is RouteDisposition.AMBIGUOUS
    assert decision.profile is None
    assert decision.intent is None


def test_specialist_profile_does_not_reclassify_its_own_telegram_message() -> None:
    decision = classify_ingress(
        "Investiga este tema",
        platform="telegram",
        current_profile="researcher",
    )

    assert decision.disposition is RouteDisposition.DEFAULT
    assert decision.profile is None
    assert decision.intent is None
