"""Safe startup readiness checks for routes and capabilities."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from hermes_harness.control_plane.router import Router, RoutingDenied


@dataclass(frozen=True)
class ReadinessReport:
    ready: bool
    missing_tools: tuple[str, ...]
    missing_skills: tuple[str, ...]
    invalid_entries: tuple[str, ...]

    def safe_text(self) -> str:
        parts = [f"ready={str(self.ready).lower()}"]
        if self.missing_tools:
            parts.append("missing tools: " + ", ".join(self.missing_tools))
        if self.missing_skills:
            parts.append("missing skills: " + ", ".join(self.missing_skills))
        if self.invalid_entries:
            parts.append("invalid metadata: " + ", ".join(self.invalid_entries))
        return "\n".join(parts)


def check_readiness(
    routing_path: Path,
    manifest_dir: Path,
    *,
    available_tools: dict[str, str],
    available_skills: dict[str, str],
) -> ReadinessReport:
    invalid: list[str] = []
    try:
        Router.from_files(routing_path, manifest_dir)
    except RoutingDenied:
        invalid.append("routing")
    required_tools: set[str] = set()
    required_skills: set[str] = set()
    for path in manifest_dir.glob("*.yaml"):
        manifest = yaml.safe_load(path.read_text())
        if not isinstance(manifest, dict):
            invalid.append(path.name)
            continue
        required_tools.update(str(value) for value in manifest.get("allowed_tools", []))
        required_skills.update(str(value) for value in manifest.get("required_skills", []))
    missing_tools = tuple(sorted(required_tools - available_tools.keys()))
    missing_skills = tuple(sorted(required_skills - available_skills.keys()))
    for name, version in available_tools.items():
        if name in required_tools and not version:
            invalid.append(f"tool:{name}")
    for name, digest in available_skills.items():
        if name in required_skills and not digest.startswith("sha256:"):
            invalid.append(f"skill:{name}")
    return ReadinessReport(
        ready=not (missing_tools or missing_skills or invalid),
        missing_tools=missing_tools,
        missing_skills=missing_skills,
        invalid_entries=tuple(sorted(invalid)),
    )
