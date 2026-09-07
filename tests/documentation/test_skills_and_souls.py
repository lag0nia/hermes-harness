from pathlib import Path

import yaml

ROOT = Path(__file__).parents[2]


def test_four_harness_skills_have_valid_frontmatter() -> None:
    for path in sorted((ROOT / "skills").glob("*/SKILL.md")):
        text = path.read_text()
        assert text.startswith("---\n")
        _, frontmatter, body = text.split("---\n", 2)
        metadata = yaml.safe_load(frontmatter)
        assert metadata["name"] == path.parent.name
        assert metadata["description"].endswith(".")
        assert len(metadata["description"]) <= 60
        assert body.strip()


def test_five_specialist_souls_exist_after_profile_consolidation() -> None:
    souls = sorted((ROOT / "profiles").glob("*/SOUL.md"))
    assert len(souls) == 5
    assert {p.parent.name for p in souls} == {
        "browser-operator",
        "researcher",
        "engineer",
        "documentator",
        "travel-planner",
    }


def test_default_capability_declares_coordinator_ownership() -> None:
    capability = yaml.safe_load(
        (ROOT / "capabilities" / "agents" / "default.yaml").read_text()
    )

    assert capability["profile"] == "default"
    assert "orchestrator-control" in capability["required_skills"]
    assert "orchestrator_answer" in capability["allowed_tools"]
    assert "orchestrator_clarify" in capability["allowed_tools"]
    assert capability["confirmation_policy"] == "policy"
