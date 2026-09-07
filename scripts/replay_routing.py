#!/usr/bin/env python3
"""Replay sanitized user-text fixtures without touching live sessions or config."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from hermes_harness.shadow import ShadowLogger, sanitize_user_text

_V021_SCHEMA_VERSION = 1
_SUPPORTED_PROFILES = frozenset(
    {"default", "browser-operator", "documentator", "engineer", "researcher", "travel-planner"}
)
_V021_ROUTE_FIELDS = ("status", "profile", "intent", "reason_code")


def classify_user_text(text: str) -> dict[str, str]:
    """Small deterministic baseline used by the offline replay harness."""
    lowered = text.casefold()
    if any(word in lowered for word in ("error", "falló", "falla", "no funciona")):
        category, intent = "errores", "general.clarify"
    elif "tarea" in lowered and any(word in lowered for word in ("y", ",", "también")):
        category, intent = "multi-intent", "calendar.create_vtodo"
    elif "vuelo" in lowered or "viaje" in lowered:
        category, intent = "travel", "travel.search_flights"
    elif any(word in lowered for word in ("navegador", "browser", "web")):
        category, intent = "browser", "browser.research"
    elif any(word in lowered for word in ("mejora", "aprende", "auto-mejora")):
        category, intent = "self-improvement", "technical.plan"
    elif any(word in lowered for word in ("cancela", "cancelar", "anula")):
        category, intent = "cancel", "pi.jobs.cancel"
    elif "tarea" in lowered and any(
        word in lowered for word in ("qué día", "cuando", "cuándo", "mañana")
    ):
        category, intent = "calendario_ambiguo", "general.clarify"
    elif any(word in lowered for word in ("también", "seguimiento", "antes")):
        category, intent = "followup", "general.answer"
    else:
        category, intent = "general", "general.answer"
    return {"category": category, "intent": intent}


def _auto_router_decision(text: str) -> Any:
    """Load the pure auto-router classifier without enabling its gateway hook."""
    try:
        from hermes_auto_routing.router import classify_message
    except ModuleNotFoundError:
        plugin_src = Path(__file__).resolve().parents[2] / "plugin-src/hermes-auto-routing/src"
        if not plugin_src.is_dir():
            return None
        sys.path.insert(0, str(plugin_src))
        from hermes_auto_routing.router import classify_message  # type: ignore[import-not-found]

    return classify_message(text)


def _candidate_advisory(text: str) -> dict[str, str] | None:
    decision = _auto_router_decision(text)
    if decision is None:
        return None
    disposition = getattr(getattr(decision, "disposition", None), "value", None)
    profile = getattr(decision, "profile", None)
    intent = getattr(decision, "intent", None)
    if disposition != "specialist" or not isinstance(profile, str) or not isinstance(intent, str):
        return None
    if profile == "default":
        return None
    return {
        "profile": profile,
        "intent": intent,
        "reason": "one deterministic specialist rule matched",
    }


def _candidate_shadow_decision(text: str) -> dict[str, str]:
    decision = _auto_router_decision(text)
    disposition = getattr(getattr(decision, "disposition", None), "value", None)
    if disposition == "ambiguous":
        return {"category": "ambiguous", "intent": "general.clarify"}
    advisory = _candidate_advisory(text)
    if advisory is not None:
        return {"category": advisory["profile"], "intent": advisory["intent"]}
    return {"category": "default", "intent": "general.answer"}


def replay_file(path: Path, log_path: Path | None = None) -> dict[str, Any]:
    """Replay JSONL fixture records; input records are never modified."""
    logger = ShadowLogger(log_path or Path(os.devnull))
    cases: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        record = json.loads(line)
        if not isinstance(record, dict) or not isinstance(record.get("text"), str):
            raise ValueError(f"line {line_number}: expected an object with text")
        safe_text = sanitize_user_text(record["text"])
        decision = logger.observe(
            safe_text,
            legacy_decider=classify_user_text,
            candidate_decider=_candidate_shadow_decision,
        )
        baseline = classify_user_text(safe_text)
        cases.append(
            {
                "id": str(record.get("id", line_number)),
                "text": safe_text,
                "category": str(record.get("category", baseline["category"])),
                "outcome": decision.outcome,
                "authoritative_path": decision.authoritative_path,
            }
        )
    return {"metrics": logger.metrics, "cases": cases, "policy_violations": []}


def _read_jsonl(path: Path, kind: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        raw = json.loads(line)
        if not isinstance(raw, dict):
            raise ValueError(f"{kind} line {line_number}: expected a JSON object")
        record = {str(key): value for key, value in raw.items()}
        if record.get("schema_version") != _V021_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported {kind} schema_version={record.get('schema_version')!r} "
                f"at line {line_number}; expected {_V021_SCHEMA_VERSION}"
            )
        records.append(record)
    return records


def _required_string(record: dict[str, Any], field: str, kind: str) -> str:
    value = record.get(field)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{kind} requires non-empty string field {field!r}")
    return value


def _actual_v021_decision(event: dict[str, Any]) -> dict[str, str | None]:
    origin = event.get("origin")
    if not isinstance(origin, dict):
        raise ValueError(f"event {event.get('id')!r} requires an origin object")
    profile = origin.get("profile", "default")
    if not isinstance(profile, str):
        raise ValueError(f"event {event.get('id')!r} has a non-string origin profile")
    if profile not in _SUPPORTED_PROFILES:
        return {
            "status": "blocked",
            "profile": "default",
            "intent": None,
            "reason_code": "unsupported_profile",
        }

    if event.get("event_type") == "kanban_dependency_resume":
        if event.get("dependency_state") != "done" or event.get("restart_recovered") is not True:
            return {
                "status": "blocked",
                "profile": profile,
                "intent": None,
                "reason_code": "dependency_not_resumable",
            }
        return {
            "status": "resumed",
            "profile": profile,
            "intent": None,
            "reason_code": "dependency_complete",
        }

    if profile != "default":
        return {
            "status": "unchanged",
            "profile": profile,
            "intent": None,
            "reason_code": "existing_profile_stamp",
        }

    if origin.get("routing_eligible") is not True:
        return {
            "status": "unchanged",
            "profile": "default",
            "intent": None,
            "reason_code": "origin_not_eligible",
        }

    text = event.get("text")
    if not isinstance(text, str):
        raise ValueError(f"event {event.get('id')!r} requires string field 'text'")
    decision = _auto_router_decision(sanitize_user_text(text))
    disposition = getattr(getattr(decision, "disposition", None), "value", None)
    reason_code = "ambiguous_specialist" if disposition == "ambiguous" else "no_unique_specialist"
    advisory = _candidate_advisory(sanitize_user_text(text))
    if advisory is None:
        return {
            "status": "default",
            "profile": "default",
            "intent": None,
            "reason_code": reason_code,
        }
    if advisory["profile"] not in _SUPPORTED_PROFILES:
        return {
            "status": "blocked",
            "profile": "default",
            "intent": None,
            "reason_code": "unsupported_profile",
        }
    return {
        "status": "routed",
        "profile": advisory["profile"],
        "intent": advisory["intent"],
        "reason_code": "unique_specialist",
    }


def _route_violations(
    expectation: dict[str, Any], event: dict[str, Any], actual: dict[str, str | None]
) -> list[dict[str, Any]]:
    expected = expectation.get("expected")
    if not isinstance(expected, dict):
        raise ValueError(f"expectation {expectation.get('id')!r} requires an expected object")
    violations: list[dict[str, Any]] = []
    for field in _V021_ROUTE_FIELDS:
        if field not in expected:
            continue
        if expected[field] != actual.get(field):
            violations.append(
                {
                    "id": expectation["id"],
                    "event_id": event["event_id"],
                    "cursor": event["cursor"],
                    "kind": "route_mismatch",
                    "field": field,
                    "expected": expected[field],
                    "actual": actual.get(field),
                }
            )
    return violations


def replay_v021(
    expectations_path: Path,
    events_path: Path,
    *,
    log_path: Path | None = None,
    after_cursor: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Compare v0.21 event decisions to an independent, versioned oracle."""
    expectations = _read_jsonl(expectations_path, "expectation")
    events = _read_jsonl(events_path, "event")
    if limit is not None and limit < 1:
        raise ValueError("limit must be positive")

    event_by_id: dict[str, dict[str, Any]] = {}
    for event in events:
        event_id = _required_string(event, "id", "event")
        if event_id in event_by_id:
            raise ValueError(f"duplicate event id {event_id!r}")
        event_by_id[event_id] = event

    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    seen_expectations: set[str] = set()
    for expectation in expectations:
        case_id = _required_string(expectation, "id", "expectation")
        if case_id in seen_expectations:
            raise ValueError(f"duplicate expectation id {case_id!r}")
        seen_expectations.add(case_id)
        matched_event = event_by_id.get(case_id)
        if matched_event is None:
            raise ValueError(f"expectation {case_id!r} has no matching event")
        if expectation.get("event_id") != matched_event.get("event_id"):
            raise ValueError(f"expectation {case_id!r} event_id does not match its event")
        if expectation.get("cursor") != matched_event.get("cursor"):
            raise ValueError(f"expectation {case_id!r} cursor does not match its event")
        _required_string(matched_event, "event_id", "event")
        _required_string(matched_event, "cursor", "event")
        pairs.append((expectation, matched_event))

    start = 0
    if after_cursor is not None:
        cursors = [event["cursor"] for _, event in pairs]
        if after_cursor not in cursors:
            raise ValueError(f"after_cursor {after_cursor!r} is not present in the event stream")
        start = cursors.index(after_cursor) + 1
    end = len(pairs) if limit is None else min(start + limit, len(pairs))
    selected = pairs[start:end]

    cases: list[dict[str, Any]] = []
    policy_violations: list[dict[str, Any]] = []
    for expectation, event in selected:
        text = event.get("text")
        if not isinstance(text, str):
            raise ValueError(f"event {event['id']!r} requires string field 'text'")
        actual = _actual_v021_decision(event)
        policy_violations.extend(_route_violations(expectation, event, actual))
        cases.append(
            {
                "id": expectation["id"],
                "event_id": event["event_id"],
                "cursor": event["cursor"],
                "text": sanitize_user_text(text),
                **actual,
            }
        )

    divergences = len(policy_violations)
    metrics = {
        "observations": len(cases),
        "matches": len(cases) - divergences,
        "divergences": divergences,
        "policy_violations": len(policy_violations),
    }
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as stream:
            for case in cases:
                stream.write(json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n")
    return {
        "schema_version": _V021_SCHEMA_VERSION,
        "cursor": after_cursor,
        "next_cursor": selected[-1][1]["cursor"] if selected else after_cursor,
        "has_more": end < len(pairs),
        "metrics": metrics,
        "cases": cases,
        "policy_violations": policy_violations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--log", type=Path, default=Path(".replay-shadow.jsonl"))
    parser.add_argument("--events", type=Path)
    parser.add_argument("--after-cursor")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    events_path = args.events or args.fixture.with_name("v021-events.jsonl")
    if args.events is not None or args.fixture.name == "v021-routing-expectations.jsonl":
        report = replay_v021(
            args.fixture,
            events_path,
            log_path=args.log,
            after_cursor=args.after_cursor,
            limit=args.limit,
        )
    else:
        report = replay_file(args.fixture, args.log)
    print(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
