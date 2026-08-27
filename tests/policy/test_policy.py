from pathlib import Path

import pytest

from hermes_harness.control_plane.policy import PolicyDenied, PolicyEngine
from tests.contracts.test_intent import envelope

ROOT = Path(__file__).parents[2]


def engine() -> PolicyEngine:
    return PolicyEngine.from_directory(ROOT / "config")


def test_provider_sol_and_900k_model_rules_are_enforced() -> None:
    policy = engine()
    with pytest.raises(PolicyDenied, match="provider"):
        policy.evaluate(envelope(model_policy={"provider": "other", "model": "x", "effort": "low"}))
    with pytest.raises(PolicyDenied, match="Sol"):
        policy.evaluate(
            envelope(
                intent="technical.change",
                model_policy={"provider": "openai-codex", "model": "gpt-5.6-sol", "effort": "high"},
            )
        )
    with pytest.raises(PolicyDenied, match="above high"):
        policy.evaluate(
            envelope(
                intent="technical.review",
                model_policy={"provider": "openai-codex", "model": "gpt-5.6-sol", "effort": "max"},
            )
        )
    with pytest.raises(PolicyDenied, match="900k"):
        policy.evaluate(
            envelope(
                intent="technical.research",
                model_policy={
                    "provider": "openai-codex",
                    "model": "gpt-5.6-luna-900k",
                    "effort": "medium",
                },
            )
        )


def test_critical_changes_require_confirmation_but_protected_history_cannot_be_deleted() -> None:
    policy = engine()
    decision = policy.evaluate(
        envelope(
            intent="technical.change", parameters={"change_categories": ["security_permissions"]}
        )
    )
    assert decision.requires_confirmation is True
    with pytest.raises(PolicyDenied, match="protected data"):
        policy.evaluate(
            envelope(intent="technical.change", parameters={"delete": ["conversations"]})
        )


def test_nested_jobs_cannot_bypass_policy() -> None:
    policy = engine()
    outer = envelope(
        intent="technical.plan",
        parameters={
            "nested_jobs": [
                envelope(
                    intent="code.change",
                    model_policy={"provider": "forbidden", "model": "x", "effort": "low"},
                )
            ]
        },
    )
    with pytest.raises(PolicyDenied, match="provider"):
        policy.evaluate(outer)


def test_profile_model_and_effort_allowlist_is_enforced() -> None:
    policy = engine()
    with pytest.raises(PolicyDenied, match="profile"):
        policy.evaluate(
            envelope(
                model_policy={
                    "provider": "openai-codex",
                    "model": "gpt-5.6-luna-900k",
                    "effort": "medium",
                    "context_size_justification": "large corpus",
                },
                intent="technical.research",
                parameters={"requested_profile": "default"},
            )
        )
    with pytest.raises(PolicyDenied, match="effort"):
        policy.evaluate(
            envelope(
                model_policy={
                    "provider": "openai-codex",
                    "model": "gpt-5.6-luna",
                    "effort": "high",
                },
                parameters={"requested_profile": "documentator"},
            )
        )


def test_unknown_profile_is_denied_by_default() -> None:
    with pytest.raises(PolicyDenied, match="profile"):
        engine().evaluate(
            envelope(
                parameters={"requested_profile": "untrusted-profile"},
                model_policy={
                    "provider": "openai-codex",
                    "model": "gpt-5.6-luna",
                    "effort": "medium",
                },
            )
        )
