"""Deterministic routing over normalized intent envelopes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from hermes_harness.control_plane.contracts import Intent, IntentEnvelope
from hermes_harness.observability import ObservabilitySink, emit_observation


class RoutingDenied(ValueError):
    """A route cannot be proven safe and complete."""


@dataclass(frozen=True)
class Route:
    envelope: IntentEnvelope
    profile: str | None
    direct_tool: str | None
    confirmation: str


class Router:
    def __init__(
        self,
        routes: dict[Intent, dict[str, Any]],
        manifests: dict[str, dict[str, Any]],
        observability: ObservabilitySink | None = None,
    ):
        self._routes = routes
        self._manifests = manifests
        self._observability = observability

    @property
    def configured_intents(self) -> tuple[Intent, ...]:
        return tuple(self._routes)

    @classmethod
    def from_files(cls, routing_path: Path, manifest_dir: Path) -> Router:
        raw = yaml.safe_load(routing_path.read_text())
        if (
            not isinstance(raw, dict)
            or raw.get("version") != 1
            or not isinstance(raw.get("routes"), dict)
        ):
            raise RoutingDenied("missing or unsupported routing schema")
        manifests: dict[str, dict[str, Any]] = {}
        for path in manifest_dir.glob("*.yaml"):
            manifest = yaml.safe_load(path.read_text())
            if not isinstance(manifest, dict) or manifest.get("schema_version") != "1.0.0":
                raise RoutingDenied(f"missing capability schema: {path.name}")
            profile = manifest.get("profile")
            if not isinstance(profile, str):
                raise RoutingDenied(f"missing profile in manifest: {path.name}")
            manifests[profile] = manifest
        routes: dict[Intent, dict[str, Any]] = {}
        for key, route in raw["routes"].items():
            try:
                intent = Intent(key)
            except ValueError as exc:
                raise RoutingDenied(f"unknown intent: {key}") from exc
            if not isinstance(route, dict):
                raise RoutingDenied(f"invalid route: {key}")
            profile = route.get("profile") or route.get("capability")
            if profile not in manifests:
                raise RoutingDenied(f"missing capability manifest: {profile}")
            destination_count = int("profile" in route) + int("direct_tool" in route)
            if destination_count != 1:
                raise RoutingDenied(f"route requires exactly one destination: {key}")
            if "direct_tool" in route and route["direct_tool"] not in manifests[profile].get(
                "allowed_tools", []
            ):
                raise RoutingDenied(f"missing tool capability for: {key}")
            routes[intent] = route
        return cls(routes, manifests)

    def route(self, envelope: IntentEnvelope) -> Route:
        try:
            config = self._routes[envelope.intent]
        except KeyError as exc:
            raise RoutingDenied(f"unknown intent: {envelope.intent}") from exc
        result = Route(
            envelope=envelope,
            profile=config.get("profile"),
            direct_tool=config.get("direct_tool"),
            confirmation=config.get("confirmation", "none"),
        )
        emit_observation(
            self._observability,
            trace_id=envelope.trace_id,
            job_id=envelope.job_id,
            session_id=envelope.origin_session,
            profile=envelope.origin_profile,
            event_type="router.decision",
            component="router",
            phase="route",
            status="success",
            summary=f"Route selected for {envelope.intent.value}",
            metadata={"intent": envelope.intent.value, "profile": result.profile},
        )
        return result

    def route_many(self, envelopes: list[IntentEnvelope]) -> list[Route]:
        by_id = {item.job_id: item for item in envelopes}
        if len(by_id) != len(envelopes):
            raise RoutingDenied("duplicate job ID")
        ordered: list[IntentEnvelope] = []
        visiting: set[object] = set()
        visited: set[object] = set()

        def visit(item: IntentEnvelope) -> None:
            if item.job_id in visiting:
                raise RoutingDenied("dependency cycle detected")
            if item.job_id in visited:
                return
            visiting.add(item.job_id)
            for dependency in item.dependencies:
                if dependency in by_id:
                    visit(by_id[dependency])
            visiting.remove(item.job_id)
            visited.add(item.job_id)
            ordered.append(item)

        for envelope in envelopes:
            visit(envelope)
        return [self.route(item) for item in ordered]


def normalize_intent_boundary(text: str) -> Intent:
    """Small deterministic adapter used only to test the normalization boundary."""
    normalized = text.casefold()
    if "tarea" in normalized:
        return Intent.CALENDAR_CREATE_VTODO
    if "salud" in normalized and ("pi" in normalized or "raspberry" in normalized):
        return Intent.PI_HEALTH_READ
    if "vuelo" in normalized:
        return Intent.TRAVEL_SEARCH_FLIGHTS
    raise RoutingDenied("normalization requires clarification")
