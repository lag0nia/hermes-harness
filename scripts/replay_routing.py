#!/usr/bin/env python3
"""Replay sanitized user-text fixtures without touching live sessions or config."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from hermes_harness.shadow import ShadowLogger, sanitize_user_text


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
            candidate_decider=classify_user_text,
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--log", type=Path, default=Path(".replay-shadow.jsonl"))
    args = parser.parse_args()
    print(
        json.dumps(
            replay_file(args.fixture, args.log), ensure_ascii=False, indent=2, sort_keys=True
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
