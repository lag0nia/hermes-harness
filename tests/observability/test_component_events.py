from pathlib import Path
from uuid import uuid4

from hermes_harness.browser_operator import Action, BrowserOperator, Risk, Step
from hermes_harness.control_plane.confirmations import ConfirmationManager
from hermes_harness.delivery import DeliveryEvent, DeliveryEventType, DeliveryRouter
from hermes_harness.observability import SQLiteObservabilitySink
from hermes_harness.scheduler import AdaptiveScheduler, LoadAverage, ResourceSnapshot
from hermes_harness.shadow import ShadowLogger


def test_scheduler_confirmation_delivery_and_shadow_emit_events(tmp_path: Path) -> None:
    sink = SQLiteObservabilitySink(tmp_path / "events.db")
    scheduler = AdaptiveScheduler(observability=sink)
    scheduler.plan([], ResourceSnapshot(1, 10, LoadAverage(0, 0, 0)))
    manager = ConfirmationManager(tmp_path / "confirm.db", observability=sink)
    job_id = uuid4()
    operation = {
        "operation": "calendar.create",
        "target": "calendar",
        "amount": None,
        "options": {},
        "destination": "local",
        "external_state_version": "v1",
    }
    preview = manager.issue(job_id, operation)
    manager.consume(preview.confirmation_id, preview.digest, operation)
    DeliveryRouter(observability=sink).route(
        [DeliveryEvent("job", "desktop", DeliveryEventType.TERMINAL, "done", terminal=True)]
    )
    shadow = ShadowLogger(tmp_path / "shadow.jsonl", observability=sink)
    shadow.observe("safe", legacy_decider=lambda _: "x", candidate_decider=lambda _: "x")
    assert sink.trace_events(job_id)


def test_browser_operator_emits_a_summary_event(tmp_path: Path) -> None:
    class Adapter:
        def observe(self):
            return {"refs": {}}

        def act(self, action):
            return None

        def verify(self, action, before, after):
            return True

        def screenshot(self):
            return str(tmp_path / "shot.png")

        def delete_screenshot(self, path):
            return None

    trace = uuid4()
    sink = SQLiteObservabilitySink(tmp_path / "events.db")
    operator = BrowserOperator(Adapter(), observability=sink)
    operator.run([Step(Action("inspect", Risk.REVERSIBLE))], trace_id=trace)
    assert sink.trace_events(trace)
