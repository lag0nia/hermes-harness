from pathlib import Path

import yaml

from hermes_harness.control_plane.contracts import Intent
from hermes_harness.control_plane.router import Router

ROOT = Path(__file__).parents[2]
MANIFEST_DIR = ROOT / "capabilities" / "agents"
PROFILE_NAMES = {
    "default",
    "researcher",
    "engineer",
    "browser-operator",
    "travel-planner",
    "documentator",
}
COMMON_BASELINE = {
    "answer",
    "clarify",
    "summarize",
    "session_context",
    "skills",
}
HIGH_IMPACT = {
    "file_write",
    "terminal_execution",
    "code_execution",
    "browser_interaction",
    "profile_delegation",
    "schedule_jobs",
    "kanban_mutation",
    "external_mcp",
}
DENIED = {
    "credential_entry",
    "payment",
    "purchase_submission",
    "booking_submission",
    "conversation_deletion",
}


def manifests() -> dict[str, dict]:
    result: dict[str, dict] = {}
    for path in MANIFEST_DIR.glob("*.yaml"):
        result[path.stem] = yaml.safe_load(path.read_text())
    return result


def test_profile_contracts_have_roles_descriptions_and_shared_baseline() -> None:
    profiles = manifests()

    assert set(profiles) == PROFILE_NAMES
    for profile, manifest in profiles.items():
        assert manifest["profile"] == profile
        assert manifest["role"].strip()
        assert manifest["description"].strip()
        assert manifest["description"].endswith(".")
        assert manifest["mode"].strip()
        assert manifest["activation_policy"] == "control_plane"
        assert "forbidden_effects" in manifest["role_constraints"]
        capabilities = manifest["capabilities"]
        assert set(capabilities["baseline"]) >= COMMON_BASELINE
        assert set(capabilities["conditional"]) >= HIGH_IMPACT
        assert set(capabilities["denied"]) >= DENIED
        groups = [set(values) for values in capabilities.values()]
        assert not any(
            groups[index] & groups[other]
            for index in range(len(groups))
            for other in range(index)
        )


def test_supported_intents_are_closed_and_auto_safe_is_a_subset() -> None:
    profiles = manifests()
    known_intents = {intent.value for intent in Intent}

    for manifest in profiles.values():
        supported = set(manifest["supported_intents"])
        auto_safe = set(manifest["auto_safe_intents"])
        assert supported <= known_intents
        assert auto_safe <= supported
        policy = manifest["tool_policy"]
        assert set(policy["permanent_tools"]) >= set(manifest["allowed_tools"])
        assert {
            "terminal_execution",
            "browser_interaction",
            "profile_delegation",
            "schedule_jobs",
        } <= set(policy["confirmation_required"])


def test_routing_routes_only_to_profiles_that_declare_the_intent() -> None:
    router = Router.from_files(ROOT / "config" / "routing.yaml", MANIFEST_DIR)
    profiles = manifests()
    routing = yaml.safe_load((ROOT / "config" / "routing.yaml").read_text())

    for intent, route in routing["routes"].items():
        profile = route.get("profile") or route.get("capability")
        assert intent in profiles[profile]["supported_intents"]
        if "direct_tool" in route:
            assert route["direct_tool"] in profiles[profile]["allowed_tools"]

    assert set(router.configured_intents) == set(Intent)


def test_router_rejects_a_route_outside_the_profile_contract(tmp_path: Path) -> None:
    routing = tmp_path / "routing.yaml"
    text = (ROOT / "config" / "routing.yaml").read_text()
    routing.write_text(
        text.replace(
            "technical.research: {profile: researcher}",
            "technical.research: {profile: travel-planner}",
        )
    )

    try:
        Router.from_files(routing, MANIFEST_DIR)
    except ValueError as exc:
        assert "does not support intent" in str(exc)
    else:
        raise AssertionError("Router accepted an unsupported profile intent")


def test_external_commit_and_sensitive_actions_are_never_manifest_tools() -> None:
    for manifest in manifests().values():
        tools = set(manifest["allowed_tools"]) | set(manifest["tool_policy"]["permanent_tools"])
        assert "uber_checkout_confirm" not in tools
        assert "uber_checkout_confirm" in manifest["tool_policy"]["blocked_tools"]
        assert "credential_entry" in manifest["capabilities"]["denied"]
        assert "payment" in manifest["capabilities"]["denied"]
        assert "booking_submission" in manifest["capabilities"]["denied"]
