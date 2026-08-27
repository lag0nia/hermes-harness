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


def test_seven_specialist_souls_exist() -> None:
    souls = sorted((ROOT / "profiles").glob("*/SOUL.md"))
    assert len(souls) == 7
    assert {p.parent.name for p in souls} == {
        "browser-operator",
        "researcher",
        "architect-planner",
        "engineer",
        "coder",
        "documentator",
        "travel-planner",
    }
