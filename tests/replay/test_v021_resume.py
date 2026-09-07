import json
from pathlib import Path

import pytest

from scripts.replay_routing import replay_v021

ROOT = Path(__file__).parents[2]
EXPECTATIONS = ROOT / "fixtures/replay/v021-routing-expectations.jsonl"
EVENTS = ROOT / "fixtures/replay/v021-events.jsonl"


def test_v021_replay_matches_independent_expectations_and_preserves_identity() -> None:
    report = replay_v021(EXPECTATIONS, EVENTS)

    assert report["metrics"] == {
        "observations": 8,
        "matches": 8,
        "divergences": 0,
        "policy_violations": 0,
    }
    assert report["has_more"] is False
    assert report["cursor"] is None
    assert report["next_cursor"] == "cur-008"
    assert [(item["event_id"], item["cursor"]) for item in report["cases"]] == [
        ("evt-generic-1", "cur-001"),
        ("evt-ambiguous-1", "cur-002"),
        ("evt-research-1", "cur-003"),
        ("evt-explicit-1", "cur-004"),
        ("evt-bot-chat-1", "cur-005"),
        ("evt-cron-1", "cur-006"),
        ("evt-unsupported-1", "cur-007"),
        ("evt-resume-1", "cur-008"),
    ]


def test_v021_replay_resumes_after_a_cursor_without_replaying_prior_events() -> None:
    report = replay_v021(EXPECTATIONS, EVENTS, after_cursor="cur-003", limit=2)

    assert report["cursor"] == "cur-003"
    assert report["has_more"] is True
    assert report["next_cursor"] == "cur-005"
    assert [item["id"] for item in report["cases"]] == ["explicit-profile-1", "bot-chat-1"]
    assert report["metrics"]["observations"] == 2


def test_v021_replay_reports_a_real_route_violation_without_exposing_text(tmp_path: Path) -> None:
    expectations = tmp_path / "expectations.jsonl"
    expectations.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "route-mismatch",
                "event_id": "evt-route-mismatch",
                "cursor": "cur-100",
                "expected": {
                    "status": "routed",
                    "profile": "researcher",
                    "intent": "technical.change",
                    "reason_code": "unique_specialist",
                },
            }
        )
        + "\n"
    )
    events = tmp_path / "events.jsonl"
    events.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "route-mismatch",
                "event_id": "evt-route-mismatch",
                "cursor": "cur-100",
                "origin": {"kind": "telegram", "profile": "default", "routing_eligible": True},
                "text": "Analiza los logs con token=secret",
            }
        )
        + "\n"
    )

    report = replay_v021(expectations, events)

    assert report["metrics"]["divergences"] == 1
    assert report["metrics"]["policy_violations"] == 1
    assert report["policy_violations"][0]["event_id"] == "evt-route-mismatch"
    assert "secret" not in json.dumps(report)
    assert "text" not in report["policy_violations"][0]


def test_v021_replay_rejects_unknown_event_schema_version(tmp_path: Path) -> None:
    expectations = tmp_path / "expectations.jsonl"
    expectations.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "unknown-version",
                "event_id": "evt-unknown-version",
                "cursor": "cur-200",
                "expected": {"status": "default", "profile": "default", "intent": None},
            }
        )
        + "\n"
    )
    events = tmp_path / "events.jsonl"
    events.write_text(
        json.dumps(
            {
                "schema_version": 99,
                "id": "unknown-version",
                "event_id": "evt-unknown-version",
                "cursor": "cur-200",
                "origin": {"kind": "telegram", "profile": "default", "routing_eligible": True},
                "text": "Hola",
            }
        )
        + "\n"
    )

    with pytest.raises(ValueError, match="unsupported event schema_version=99"):
        replay_v021(expectations, events)
