from pathlib import Path

from hermes_harness.browser_operator import (
    Action,
    BrowserOperator,
    Outcome,
    Risk,
    Step,
)


class FakeBrowser:
    def __init__(self, states):
        self.states = iter(states)
        self.actions = []
        self.deleted = []

    def observe(self):
        return next(self.states)

    def act(self, action):
        self.actions.append(action)

    def verify(self, action, before, after):
        return after.get("done") is True

    def screenshot(self):
        return "/tmp/temporary-shot.png"

    def delete_screenshot(self, path):
        self.deleted.append(path)


def test_operator_observe_act_verify_invalidates_refs_and_cleans_screenshot(tmp_path):
    browser = FakeBrowser(
        [
            {"refs": {"submit": "r1"}, "done": False},
            {"refs": {"submit": "r2"}, "done": True},
        ]
    )
    op = BrowserOperator(browser, screenshot_dir=tmp_path)
    result = op.run([Step(Action("submit", Risk.REVERSIBLE), confidence=0.9)])
    assert result.outcome is Outcome.SUCCEEDED
    assert browser.actions == [Action("submit", Risk.REVERSIBLE)]
    assert result.invalidated_refs == ("submit",)
    assert browser.deleted and not Path(browser.deleted[0]).exists()
    assert all("password" not in str(event).lower() for event in result.logs)


def test_uncertain_delivery_gets_only_one_equivalent_retry_then_need_input(tmp_path):
    class Uncertain(FakeBrowser):
        def verify(self, action, before, after):
            return False

    browser = Uncertain([{"refs": {"x": "1"}}, {"refs": {"x": "2"}}, {"refs": {"x": "3"}}])
    result = BrowserOperator(browser, screenshot_dir=tmp_path).run(
        [Step(Action("save", Risk.REVERSIBLE), confidence=0.9)]
    )
    assert result.outcome is Outcome.NEED_INPUT
    assert len(browser.actions) == 2
    assert result.error == "verification_failed"


def test_persistent_action_is_not_retried_after_verification_failure(tmp_path):
    class Uncertain(FakeBrowser):
        def verify(self, action, before, after):
            return False

    browser = Uncertain([{"refs": {"x": "1"}}, {"refs": {"x": "2"}}])
    result = BrowserOperator(browser, screenshot_dir=tmp_path).run(
        [Step(Action("submit", Risk.PERSISTENT), confidence=0.9)]
    )
    assert result.outcome is Outcome.NEED_INPUT
    assert len(browser.actions) == 1
    assert result.error == "verification_failed"


def test_low_confidence_and_cycle_are_blocked_without_action(tmp_path):
    browser = FakeBrowser([{"refs": {"x": "1"}}])
    result = BrowserOperator(browser, screenshot_dir=tmp_path, confidence_threshold=0.8).run(
        [Step(Action("danger", Risk.PERSISTENT), confidence=0.5)]
    )
    assert result.outcome is Outcome.NEED_INPUT
    assert browser.actions == []


def test_critical_or_conflicting_visual_state_requests_sol_review(tmp_path):
    browser = FakeBrowser(
        [
            {"refs": {"pay": "1"}, "visual_conflict": True},
            {"refs": {"pay": "2"}, "done": True},
        ]
    )
    result = BrowserOperator(browser, screenshot_dir=tmp_path, sol_review=lambda _: True).run(
        [Step(Action("pay", Risk.CRITICAL), confidence=0.99)]
    )
    assert result.outcome is Outcome.SUCCEEDED
    assert result.sol_reviews == 1


def test_cancel_and_crash_cleanup(tmp_path):
    browser = FakeBrowser([{"refs": {"x": "1"}}])
    result = BrowserOperator(browser, screenshot_dir=tmp_path).run([], cancel=lambda: True)
    assert result.outcome is Outcome.CANCELLED
    assert result.screenshots == ()

    class Crashes(FakeBrowser):
        def act(self, action):
            raise RuntimeError("token=password leaked")

    crashed = BrowserOperator(Crashes([{"refs": {"x": "1"}}]), screenshot_dir=tmp_path).run(
        [Step(Action("x", Risk.REVERSIBLE), confidence=0.9)]
    )
    assert crashed.outcome is Outcome.FAILED
    assert "password" not in str(crashed.logs).lower()


def test_error_redaction_is_case_insensitive_and_removes_secret_value(tmp_path):
    class Crashes(FakeBrowser):
        def act(self, action):
            raise RuntimeError("Password=top-secret")

    crashed = BrowserOperator(Crashes([{"refs": {"x": "1"}}]), screenshot_dir=tmp_path).run(
        [Step(Action("x"), confidence=0.9)]
    )
    assert "top-secret" not in str(crashed.logs)
    assert "password" not in str(crashed.logs).lower()
