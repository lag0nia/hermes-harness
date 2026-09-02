"""Typed Control Plane bridge for shadow and read-only operation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Any
from uuid import UUID

from hermes_harness.control_plane.contracts import IntentEnvelope
from hermes_harness.control_plane.phase_policy import Phase, PhasePolicy
from hermes_harness.control_plane.policy import PolicyDenied, PolicyEngine
from hermes_harness.control_plane.router import Router, RoutingDenied
from hermes_harness.dispatcher import Dispatcher
from hermes_harness.observability import Observation, SQLiteObservabilitySink

READ_ONLY_INTENTS = PhasePolicy.read_only_intents


class BridgeDenied(ValueError):
    pass


@dataclass(frozen=True)
class BridgePlan:
    trace_id: UUID
    job_id: UUID
    intent: str
    profile: str | None
    direct_tool: str | None
    confirmation: str
    mode: str
    allowed: bool
    reason: str | None = None
    dispatch: BridgeDispatch | None = None


@dataclass(frozen=True)
class BridgeDispatchChild:
    job_id: UUID
    kanban_task_id: str


@dataclass(frozen=True)
class BridgeDispatch:
    job_id: UUID
    direct: bool
    kanban_task_id: str | None
    children: tuple[BridgeDispatchChild, ...] = ()


class ObservabilityBridge:
    def __init__(
        self,
        router: Router,
        policy: PolicyEngine,
        sink: SQLiteObservabilitySink,
        phase_policy: PhasePolicy | None = None,
        dispatcher: Dispatcher | None = None,
    ) -> None:
        self.router = router
        self.policy = policy
        self.sink = sink
        self.phase_policy = phase_policy or PhasePolicy()
        self.dispatcher = dispatcher

    def plan(self, envelope: IntentEnvelope, *, mode: str = "shadow") -> BridgePlan:
        if mode not in {"shadow", "read_only", "full"}:
            raise BridgeDenied("bridge mode must be shadow, read_only, or full")
        trace = envelope.trace_id
        try:
            route = self.router.route(envelope)
            self.policy.evaluate(envelope.model_dump(mode="json"))
        except (RoutingDenied, PolicyDenied) as exc:
            self._event(envelope, "bridge.denied", "denied", str(exc), mode=mode)
            return BridgePlan(
                trace,
                envelope.job_id,
                envelope.intent.value,
                None,
                None,
                "denied",
                mode,
                False,
                str(exc),
            )
        if mode == "full":
            allowed = True
            reason = None
        else:
            phase = Phase.SHADOW if mode == "shadow" else Phase.READ_ONLY
            phase_decision = self.phase_policy.check(envelope.intent, phase)
            allowed = phase_decision.allowed
            reason = None if allowed else phase_decision.reason
        self._event(
            envelope,
            "bridge.plan",
            "success" if allowed else "denied",
            reason or f"{mode} plan",
            mode=mode,
        )
        return BridgePlan(
            trace,
            envelope.job_id,
            envelope.intent.value,
            route.profile,
            route.direct_tool,
            route.confirmation,
            mode,
            allowed,
            reason,
        )

    def submit_read_only(self, envelope: IntentEnvelope) -> BridgePlan:
        result = self.plan(envelope, mode="read_only")
        if not result.allowed:
            raise BridgeDenied(result.reason or "read-only operation denied")
        return result

    def submit_full(self, envelope: IntentEnvelope) -> BridgePlan:
        result = self.plan(envelope, mode="full")
        if not result.allowed:
            raise BridgeDenied(result.reason or "operation denied")
        if self.dispatcher is None:
            return result
        dispatch = self.dispatcher.dispatch(envelope)
        return replace(
            result,
            dispatch=BridgeDispatch(
                job_id=dispatch.job_id,
                direct=dispatch.direct,
                kanban_task_id=dispatch.kanban_task_id,
                children=tuple(
                    BridgeDispatchChild(
                        job_id=child.envelope.job_id,
                        kanban_task_id=child.kanban_task_id,
                    )
                    for child in dispatch.children
                ),
            ),
        )

    def trace_context(self, trace_id: UUID) -> dict[str, Any]:
        events = self.sink.trace_events(trace_id)
        return {
            "trace_id": str(trace_id),
            "event_count": len(events),
            "event_ids": [row["event_id"] for row in events],
        }

    def _event(
        self,
        envelope: IntentEnvelope,
        event_type: str,
        status: str,
        summary: str,
        *,
        mode: str,
    ) -> None:
        self.sink.emit_normal(
            Observation(
                trace_id=envelope.trace_id,
                span_id=UUID(int=(envelope.job_id.int ^ envelope.trace_id.int) or 1),
                event_type=event_type,
                component="control-plane-bridge",
                phase="route",
                status=status,
                summary=summary[:160],
                metadata={"intent": envelope.intent.value, "mode": mode},
                occurred_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
                job_id=envelope.job_id,
                profile=envelope.origin_profile,
                session_id=envelope.origin_session,
            )
        )


def build_stdio_server(bridge: ObservabilityBridge) -> Any:
    """Build an MCP 2.x server when the optional SDK is installed."""
    try:
        from mcp.server import MCPServer
    except ImportError as exc:
        raise RuntimeError("MCP SDK 2.x is required for the bridge") from exc
    server = MCPServer("Hermes Control Plane Observability Bridge", version="1.0.0")

    def parse_envelope(value: dict[str, Any]) -> IntentEnvelope:
        if not isinstance(value, dict):
            raise BridgeDenied("envelope must be an object")
        return IntentEnvelope.model_validate(value)

    def plan_result(plan: BridgePlan) -> dict[str, Any]:
        result = asdict(plan)
        result.pop("dispatch")
        result["trace_id"] = str(plan.trace_id)
        result["job_id"] = str(plan.job_id)
        return result

    def dispatch_result(dispatch: BridgeDispatch) -> dict[str, Any]:
        return {
            "job_id": str(dispatch.job_id),
            "direct": dispatch.direct,
            "kanban_task_id": dispatch.kanban_task_id,
            "children": [
                {
                    "job_id": str(child.job_id),
                    "kanban_task_id": child.kanban_task_id,
                }
                for child in dispatch.children
            ],
        }

    @server.tool(name="harness_plan_intent", structured_output=True)
    def harness_plan_intent(envelope: dict[str, Any]) -> dict[str, Any]:
        try:
            return plan_result(bridge.plan(parse_envelope(envelope)))
        except Exception as exc:
            return {"allowed": False, "error": str(exc)[:512]}

    @server.tool(name="harness_submit_read_only", structured_output=True)
    def harness_submit_read_only(envelope: dict[str, Any]) -> dict[str, Any]:
        try:
            return {
                "ok": True,
                "plan": plan_result(bridge.submit_read_only(parse_envelope(envelope))),
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:512]}

    @server.tool(name="harness_submit", structured_output=True)
    def harness_submit(envelope: dict[str, Any]) -> dict[str, Any]:
        try:
            result = bridge.submit_full(parse_envelope(envelope))
            if result.dispatch is None:
                raise BridgeDenied("full submission requires an attached dispatcher")
            return {
                "ok": True,
                "plan": plan_result(result),
                "dispatch": dispatch_result(result.dispatch),
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:512]}

    @server.tool(name="harness_job_status", structured_output=True)
    def harness_job_status(job_id: str) -> dict[str, Any]:
        try:
            parsed = UUID(job_id)
            events = bridge.sink.job_events(parsed)
            return {
                "job_id": job_id,
                "event_count": len(events),
                "event_ids": [row["event_id"] for row in events],
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:512]}

    @server.tool()
    def harness_trace_context(trace_id: str) -> dict[str, Any]:
        return bridge.trace_context(UUID(trace_id))

    return server
