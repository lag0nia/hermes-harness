"""Export canonical JSON Schemas from the Pydantic contracts."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import TypeAdapter

from hermes_harness.control_plane.contracts import (
    AgentEvent,
    ChangeEvent,
    ConfirmationGrant,
    IntentEnvelope,
    JobRequest,
    JobResult,
    NeedInput,
    TypedError,
)

ROOT = Path(__file__).parents[1]
MODELS = {
    "intent-envelope-1.0.0.schema.json": IntentEnvelope,
    "job-request-1.0.0.schema.json": JobRequest,
    "agent-event-1.0.0.schema.json": AgentEvent,
    "job-result-1.0.0.schema.json": JobResult,
    "need-input-1.0.0.schema.json": NeedInput,
    "confirmation-grant-1.0.0.schema.json": ConfirmationGrant,
    "change-event-1.0.0.schema.json": ChangeEvent,
    "error-1.0.0.schema.json": TypedError,
}


def main() -> None:
    destination = ROOT / "contracts"
    destination.mkdir(exist_ok=True)
    for filename, model in MODELS.items():
        schema = TypeAdapter(model).json_schema(mode="validation")
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        (destination / filename).write_text(
            json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )


if __name__ == "__main__":
    main()
