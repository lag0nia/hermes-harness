from pathlib import Path

from hermes_harness.control_plane.readiness import check_readiness

ROOT = Path(__file__).parents[2]


def test_readiness_validates_named_tools_skills_versions_and_hashes_without_secrets() -> None:
    report = check_readiness(
        ROOT / "config/routing.yaml",
        ROOT / "capabilities/agents",
        available_tools={"pi_health": "1.0.0", "nextcloud_put_item": "1.0.0"},
        available_skills={"orchestrator-control": "sha256:known"},
    )
    rendered = report.safe_text()
    assert report.ready is False
    assert "missing" in rendered.lower()
    assert "token" not in rendered.lower()
    assert "secret" not in rendered.lower()
