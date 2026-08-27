from pathlib import Path
from uuid import uuid4

import pytest

from hermes_harness.control_plane.contracts import Intent, IntentEnvelope
from hermes_harness.control_plane.router import Router, RoutingDenied, normalize_intent_boundary
from tests.contracts.test_intent import envelope

ROOT = Path(__file__).parents[2]


def test_every_closed_intent_has_one_deterministic_route() -> None:
    router = Router.from_files(ROOT / "config/routing.yaml", ROOT / "capabilities/agents")
    assert set(router.configured_intents) == set(Intent)
    for intent in Intent:
        normalized = IntentEnvelope.model_validate(envelope(intent=intent.value))
        first = router.route(normalized)
        second = router.route(normalized)
        assert first == second
        assert bool(first.profile) ^ bool(first.direct_tool)


def test_missing_capability_or_unknown_route_is_denied_by_default(tmp_path: Path) -> None:
    routing = tmp_path / "routing.yaml"
    routing.write_text("version: 1\nroutes:\n  technical.research:\n    profile: missing\n")
    with pytest.raises(RoutingDenied, match="manifest"):
        Router.from_files(routing, ROOT / "capabilities/agents")


def test_multi_intent_dependencies_are_topologically_ordered_and_cycles_denied() -> None:
    router = Router.from_files(ROOT / "config/routing.yaml", ROOT / "capabilities/agents")
    first_id, second_id = uuid4(), uuid4()
    first = IntentEnvelope.model_validate(envelope(job_id=str(first_id), intent="technical.plan"))
    second = IntentEnvelope.model_validate(
        envelope(job_id=str(second_id), intent="technical.change", dependencies=[str(first_id)])
    )
    assert [item.envelope.job_id for item in router.route_many([second, first])] == [
        first_id,
        second_id,
    ]
    cyc_a = first.model_copy(update={"dependencies": [second_id]})
    cyc_b = second.model_copy(update={"dependencies": [first_id]})
    with pytest.raises(RoutingDenied, match="cycle"):
        router.route_many([cyc_a, cyc_b])


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Crea una tarea para mañana", Intent.CALENDAR_CREATE_VTODO),
        ("Mira la salud de la Raspberry Pi", Intent.PI_HEALTH_READ),
        ("Busca vuelos baratos", Intent.TRAVEL_SEARCH_FLIGHTS),
    ],
)
def test_spanish_paraphrases_exist_only_at_normalization_boundary(
    text: str, expected: Intent
) -> None:
    assert normalize_intent_boundary(text) is expected
