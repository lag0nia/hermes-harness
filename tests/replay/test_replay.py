import json
from pathlib import Path

from scripts.replay_routing import replay_file


def test_replay_fixture_covers_required_spanish_cases() -> None:
    fixture = Path(__file__).parents[2] / "fixtures/replay/fixtures/spanish_cases.jsonl"
    report = replay_file(fixture)
    assert report["metrics"]["observations"] >= 7
    assert report["metrics"]["policy_violations"] == 0
    categories = {item["category"] for item in report["cases"]}
    assert {
        "errores",
        "multi-intent",
        "followup",
        "cancel",
        "calendario_ambiguo",
        "browser",
        "travel",
        "self-improvement",
    } <= categories


def test_replay_export_contains_only_sanitized_user_text(tmp_path: Path) -> None:
    source = tmp_path / "input.jsonl"
    source.write_text(json.dumps({"id": "x", "text": "Mi token=secret busca un vuelo"}) + "\n")
    report = replay_file(source)
    assert report["cases"][0]["text"] == "Mi [REDACTED] busca un vuelo"
    assert "secret" not in json.dumps(report)
