"""MCP 2.x stdio entry point for the read-only harness bridge."""

from __future__ import annotations

from typing import Any

from .observability_bridge import ObservabilityBridge, build_stdio_server


def create_server(bridge: ObservabilityBridge) -> Any:
    return build_stdio_server(bridge)


__all__ = ["create_server"]
