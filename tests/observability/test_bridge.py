from pathlib import Path
from uuid import uuid4

import pytest

from hermes_harness.control_plane.contracts import Intent, IntentEnvelope, ModelPolicy, RiskClass
from hermes_harness.control_plane.policy import PolicyEngine
from hermes_harness.control_plane.router import Router
from hermes_harness.observability import SQLiteObservabilitySink
from hermes_harness.observability_bridge import BridgeDenied, ObservabilityBridge


@pytest.fixture
def bridge(tmp_path: Path) -> ObservabilityBridge:
    router = Router(
        {Intent.GENERAL_ANSWER: {"profile": "default", "confirmation": "none"}}, {"default": {}}
    )
    policy = PolicyEngine(
        {
            "provider": "openai-codex",
            "profiles": {"default": {"models": ["gpt-5.6-luna"], "efforts": ["high"]}},
            "sol": {"allowed_intents": []},
            "models_900k": {"allowed_profiles": [], "allowed_intents": []},
        },
        set(),
        set(),
    )
    return ObservabilityBridge(router, policy, SQLiteObservabilitySink(tmp_path / "events.db"))


def envelope(intent: Intent) -> IntentEnvelope:
    return IntentEnvelope(
        schema_version="1.0.0",
        job_id=uuid4(),
        trace_id=uuid4(),
        origin_profile="default",
        origin_session="s",
        delivery_target="cli",
        intent=intent,
        idempotency_key=str(uuid4()),
        risk_class=RiskClass.LOW,
        model_policy=ModelPolicy(provider="openai-codex", model="gpt-5.6-luna", effort="high"),
        context_references=[],
        parameters={},
        source_text="safe request",
    )


def test_bridge_accepts_allowlisted_read_only_intent(bridge: ObservabilityBridge) -> None:
    result = bridge.submit_read_only(envelope(Intent.GENERAL_ANSWER))
    assert result.allowed is True
    assert result.mode == "read_only"


def test_bridge_rejects_mutation_before_execution(bridge: ObservabilityBridge) -> None:
    item = envelope(Intent.CALENDAR_CREATE_EVENT)
    with pytest.raises(BridgeDenied):
        bridge.submit_read_only(item)
    assert bridge.trace_context(item.trace_id)["event_count"] == 1
