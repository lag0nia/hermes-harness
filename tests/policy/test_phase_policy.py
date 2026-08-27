from hermes_harness.control_plane.contracts import Intent
from hermes_harness.control_plane.phase_policy import Phase, PhasePolicy


def test_every_known_intent_has_explicit_phase_decision() -> None:
    policy = PhasePolicy()
    for intent in Intent:
        decision = policy.check(intent, Phase.READ_ONLY)
        assert decision.reason
        assert decision.allowed is (intent in policy.read_only_intents)


def test_shadow_never_allows_external_execution() -> None:
    policy = PhasePolicy()
    for intent in Intent:
        decision = policy.check(intent, Phase.SHADOW)
        assert decision.allowed
        assert not decision.execute


def test_unknown_intent_fails_closed() -> None:
    policy = PhasePolicy()
    decision = policy.check("future.unknown", Phase.READ_ONLY)
    assert not decision.allowed
    assert not decision.execute
