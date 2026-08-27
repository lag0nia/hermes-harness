from pathlib import Path
from uuid import uuid4

from hermes_harness.control_plane.contracts import Intent, IntentEnvelope, ModelPolicy, RiskClass
from hermes_harness.control_plane.policy import PolicyEngine
from hermes_harness.control_plane.router import Router
from hermes_harness.observability import SQLiteObservabilitySink
from hermes_harness.observability_bridge import ObservabilityBridge


def test_full_mode_accepts_noncommercial_mutation_intents(tmp_path: Path) -> None:
    router = Router(
        {Intent.CALENDAR_CREATE_EVENT: {"profile": "default", "confirmation": "required"}},
        {"default": {}},
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
    bridge = ObservabilityBridge(router, policy, SQLiteObservabilitySink(tmp_path / "events.db"))
    request = IntentEnvelope(
        schema_version="1.0.0",
        job_id=uuid4(),
        trace_id=uuid4(),
        origin_profile="default",
        origin_session="s",
        delivery_target="desktop",
        intent=Intent.CALENDAR_CREATE_EVENT,
        idempotency_key=str(uuid4()),
        risk_class=RiskClass.MEDIUM,
        model_policy=ModelPolicy(provider="openai-codex", model="gpt-5.6-luna", effort="high"),
        context_references=[],
        parameters={},
        source_text="create an event",
    )
    result = bridge.submit_full(request)
    assert result.allowed is True
    assert result.mode == "full"
