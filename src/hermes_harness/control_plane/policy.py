"""Fail-closed model, risk, and retention policy engine."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import yaml

from hermes_harness.observability import ObservabilitySink, emit_observation


class PolicyDenied(ValueError):
    """The requested operation violates a non-bypassable policy."""


@dataclass(frozen=True)
class PolicyDecision:
    requires_confirmation: bool
    reasons: tuple[str, ...]


class PolicyEngine:
    def __init__(
        self,
        model_policy: dict[str, Any],
        critical: set[str],
        protected: set[str],
        observability: ObservabilitySink | None = None,
    ) -> None:
        self._models = model_policy
        self._critical = critical
        self._protected = protected
        self._observability = observability

    @classmethod
    def from_directory(cls, directory: Path) -> PolicyEngine:
        def load(name: str) -> dict[str, Any]:
            value = yaml.safe_load((directory / name).read_text())
            if not isinstance(value, dict) or value.get("version") != 1:
                raise PolicyDenied(f"invalid policy schema: {name}")
            return value

        models = load("model-policy.yaml")
        critical = load("critical-changes.yaml")
        retention = load("retention-policy.yaml")
        return cls(
            models,
            {str(item) for item in critical.get("requires_confirmation", [])},
            {str(item) for item in retention.get("protected_from_deletion", [])},
        )

    def evaluate(self, payload: dict[str, Any]) -> PolicyDecision:
        reasons: set[str] = set()
        try:
            self._evaluate_job(payload, reasons)
        except PolicyDenied as exc:
            trace = _payload_uuid(payload, "trace_id")
            if trace is not None:
                emit_observation(
                    self._observability,
                    trace_id=trace,
                    event_type="policy.denied",
                    component="policy",
                    phase="authorize",
                    status="denied",
                    summary="Policy denied the operation",
                    metadata={"reason_code": type(exc).__name__},
                )
            raise
        decision = PolicyDecision(bool(reasons), tuple(sorted(reasons)))
        trace = _payload_uuid(payload, "trace_id")
        if trace is not None:
            emit_observation(
                self._observability,
                trace_id=trace,
                event_type="policy.evaluated",
                component="policy",
                phase="authorize",
                status="confirmation_required" if decision.requires_confirmation else "allowed",
                summary="Policy evaluation completed",
                metadata={"requires_confirmation": decision.requires_confirmation},
            )
        return decision

    def _evaluate_job(self, job: dict[str, Any], reasons: set[str]) -> None:
        intent = str(job.get("intent", ""))
        model = job.get("model_policy")
        if not isinstance(model, dict):
            raise PolicyDenied("missing model policy")
        if model.get("provider") != self._models.get("provider"):
            raise PolicyDenied("provider must be openai-codex")
        model_name = str(model.get("model", ""))
        effort = str(model.get("effort", ""))
        parameters = job.get("parameters", {})
        requested_profile = (
            (parameters.get("requested_profile") if isinstance(parameters, dict) else None)
            or job.get("requested_profile")
            or job.get("origin_profile")
        )
        profiles = self._models.get("profiles", {})
        if isinstance(profiles, dict) and str(requested_profile) not in profiles:
            raise PolicyDenied("profile is not in the allowlist")
        profile_policy = profiles.get(str(requested_profile))
        if isinstance(profile_policy, dict) and "sol" not in model_name.casefold():
            if (
                model_name not in profile_policy.get("models", [])
                and "900k" not in model_name.casefold()
            ):
                raise PolicyDenied("model is not allowed for profile")
            if effort not in profile_policy.get("efforts", []):
                raise PolicyDenied("effort is not allowed for profile")
        if "sol" in model_name.casefold():
            allowed = self._models["sol"]["allowed_intents"]
            if intent not in allowed:
                raise PolicyDenied("Sol is allowed only for independent review or escalation")
            if effort not in {"low", "medium", "high"}:
                raise PolicyDenied("Sol effort above high is prohibited")
        if "900k" in model_name.casefold():
            policy = self._models["models_900k"]
            if str(requested_profile) not in policy["allowed_profiles"]:
                raise PolicyDenied("900k model is not allowed for profile")
            if intent not in policy["allowed_intents"]:
                raise PolicyDenied("900k model is outside its allowlist")
            if not model.get("context_size_justification"):
                raise PolicyDenied("900k model requires explicit context-size justification")

        self._inspect_operation(parameters, reasons)
        if isinstance(parameters, dict):
            nested = parameters.get("nested_jobs", [])
            if isinstance(nested, list):
                for child in nested:
                    if not isinstance(child, dict):
                        raise PolicyDenied("nested job must be an object")
                    self._evaluate_job(child, reasons)

    def _inspect_operation(self, value: object, reasons: set[str]) -> None:
        if isinstance(value, dict):
            categories = value.get("change_categories", [])
            if isinstance(categories, list):
                reasons.update(str(item) for item in categories if str(item) in self._critical)
            deletion = value.get("delete", [])
            deletion_values = (
                {str(deletion)}
                if isinstance(deletion, str)
                else {str(item) for item in deletion if isinstance(deletion, list)}
            )
            if deletion_values & self._protected:
                raise PolicyDenied("deletion of protected data is prohibited")
            for nested in value.values():
                self._inspect_operation(nested, reasons)
        elif isinstance(value, list):
            for nested in value:
                self._inspect_operation(nested, reasons)


def _payload_uuid(payload: dict[str, Any], key: str) -> UUID | None:
    value = payload.get(key)
    try:
        return UUID(str(value)) if value else None
    except (ValueError, AttributeError):
        return None
