from pathlib import Path

from hermes_harness.shadow import KillSwitch, ShadowLogger, sanitize_user_text


def test_sanitize_user_text_keeps_only_safe_user_text() -> None:
    text = "Mi token=abc123; crea una tarea para mañana."
    assert sanitize_user_text(text) == "Mi [REDACTED]; crea una tarea para mañana."


def test_shadow_log_keeps_legacy_authoritative_and_records_divergence(tmp_path: Path) -> None:
    logger = ShadowLogger(tmp_path / "shadow.jsonl")
    decision = logger.observe(
        "Busca vuelos a Madrid",
        legacy_decider=lambda text: {"intent": "travel.search_flights"},
        candidate_decider=lambda text: {"intent": "general.clarify"},
    )
    assert decision.authoritative_path == "legacy"
    assert decision.outcome == "divergence"
    assert logger.metrics == {
        "observations": 1,
        "matches": 0,
        "divergences": 1,
        "policy_violations": 0,
    }
    line = (tmp_path / "shadow.jsonl").read_text()
    assert "Busca vuelos a Madrid" in line
    assert "token" not in line


def test_kill_switch_is_single_gate_and_rolls_back_in_stages() -> None:
    switch = KillSwitch()
    assert switch.allows("shadow")
    switch.rollback_to("read_only")
    assert not switch.allows("promotion")
    assert switch.allows("read_only")
    switch.trip("divergencia de routing")
    assert switch.tripped
    assert not switch.allows("read_only")
    assert switch.reason == "divergencia de routing"


def test_shadow_logger_never_emits_policy_violation_for_sanitized_text(tmp_path: Path) -> None:
    logger = ShadowLogger(tmp_path / "shadow.jsonl")
    logger.observe(
        "Mi contraseña: supersecret; necesito ayuda",
        legacy_decider=lambda text: "legacy",
        candidate_decider=lambda text: "legacy",
    )
    assert logger.metrics["policy_violations"] == 0
    assert "supersecret" not in (tmp_path / "shadow.jsonl").read_text()
