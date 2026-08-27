"""Pure outbound delivery policy and in-memory surface adapter."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Surface(StrEnum):
    DESKTOP = "desktop"
    TELEGRAM = "telegram"


class DeliveryEventType(StrEnum):
    START = "start"
    BLOCKED = "blocked"
    MILESTONE = "milestone"
    TERMINAL = "terminal"
    STATUS = "status"


@dataclass(frozen=True)
class DeliveryEvent:
    job_id: str
    origin: str
    event_type: DeliveryEventType
    text: str
    event_id: str | None = None
    critical: bool = False
    terminal: bool = False
    reveal_id: bool = False


@dataclass(frozen=True)
class OutboundMessage:
    target: str
    text: str
    role: str = "assistant"
    job_id: str = ""


class DeliveryRouter:
    """Routes notifications without network I/O; callers send OutboundMessage later."""

    def __init__(self, *, telegram_extra_target: str = "telegram") -> None:
        self.telegram_extra_target = telegram_extra_target
        self._seen: set[str] = set()
        self._connected: dict[str, bool] = {}
        self._history: dict[str, list[OutboundMessage]] = {}
        self._turn: dict[str, int] = {}

    def set_connected(self, target: str, connected: bool) -> None:
        self._connected[target] = connected

    @staticmethod
    def _short_id(job_id: str) -> str:
        return job_id[:7]

    def _message(self, event: DeliveryEvent, target: str) -> OutboundMessage:
        text = event.text
        if event.reveal_id:
            text = f"[{self._short_id(event.job_id)}] {text}"
        role = "assistant" if self._turn.get(target, 0) % 2 == 0 else "user"
        self._turn[target] = self._turn.get(target, 0) + 1
        return OutboundMessage(target, text, role, event.job_id)

    def route(self, events: list[DeliveryEvent]) -> list[OutboundMessage]:
        messages: list[OutboundMessage] = []
        for event in events:
            key = event.event_id or f"{event.job_id}:{event.event_type}:{event.text}"
            if key in self._seen:
                continue
            self._seen.add(key)
            targets = [event.origin]
            if (
                event.critical or event.event_type is DeliveryEventType.BLOCKED
            ) and not event.origin.startswith("telegram:"):
                targets.append(self.telegram_extra_target)
            for target in targets:
                message = self._message(event, target)
                self._history.setdefault(event.job_id, []).append(message)
                if self._connected.get(target, True):
                    messages.append(message)
        return messages

    def status(self, job_id: str, target: str) -> OutboundMessage:
        history = self._history.get(job_id, [])
        text = history[-1].text if history else "No hay estado disponible"
        return self._message(
            DeliveryEvent(job_id, target, DeliveryEventType.STATUS, text, reveal_id=True), target
        )
