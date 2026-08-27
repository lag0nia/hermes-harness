from hermes_harness.scheduler import (
    AdaptiveScheduler,
    BrowserSessionState,
    JobSpec,
    LoadAverage,
    ResourceSnapshot,
    WorkerInventory,
)


def snapshot(*, current=900, maximum=2048, load=1.0, browser=False):
    return ResourceSnapshot(
        cgroup_current_bytes=current * 1024 * 1024,
        cgroup_max_bytes=maximum * 1024 * 1024,
        load=LoadAverage(one=load, five=load, fifteen=load),
        inventory=WorkerInventory(active=0, queued=0),
        browser=BrowserSessionState(active=browser),
    )


def test_capacity_units_and_browser_singleton_are_enforced():
    scheduler = AdaptiveScheduler(capacity_units=4, max_jobs=5, reserve_units=1)
    jobs = [
        JobSpec(f"j{i}", kind, priority=0)
        for i, kind in enumerate(["remote", "research", "documentator", "engineer", "browser"])
    ]
    decision = scheduler.plan(jobs, snapshot())
    assert [j.job_id for j in decision.admitted] == ["j0", "j1", "j2"]
    assert decision.rejected["j3"] == "capacity"
    assert decision.rejected["j4"] == "capacity"


def test_browser_session_is_singleton_even_when_capacity_is_available():
    scheduler = AdaptiveScheduler(capacity_units=10, max_jobs=5, reserve_units=0)
    jobs = [JobSpec("a", "browser", priority=10), JobSpec("b", "browser", priority=1)]
    decision = scheduler.plan(jobs, snapshot(maximum=4096))
    assert [j.job_id for j in decision.admitted] == ["a"]
    assert decision.rejected["b"] == "browser_singleton"


def test_pressure_pauses_noncritical_and_hysteresis_prevents_flapping():
    scheduler = AdaptiveScheduler()
    jobs = [
        JobSpec("critical", "remote", priority=100, critical=True),
        JobSpec("normal", "remote", priority=1),
    ]
    pressure = snapshot(current=1800, load=4.0)
    first = scheduler.plan(jobs, pressure)
    assert first.paused == ["normal"]
    relaxed = snapshot(current=1500, load=2.0)
    assert scheduler.plan(jobs, relaxed).paused == ["normal"]
    assert scheduler.plan(jobs, snapshot(current=1200, load=1.0)).resumed == ["normal"]


def test_worker_inventory_and_resume_are_observable_without_side_effects():
    scheduler = AdaptiveScheduler()
    state = snapshot()
    state = ResourceSnapshot(**{**state.__dict__, "inventory": WorkerInventory(active=2, queued=3)})
    report = scheduler.observe(state)
    assert report.inventory.active == 2
    assert report.inventory.queued == 3


def test_active_workers_consume_capacity_and_job_slots():
    scheduler = AdaptiveScheduler(capacity_units=4, max_jobs=5, reserve_units=1)
    state = snapshot()
    state = ResourceSnapshot(**{**state.__dict__, "inventory": WorkerInventory(active=3)})
    decision = scheduler.plan([JobSpec("new")], state)
    assert decision.admitted == []
    assert decision.rejected["new"] in {"capacity", "max_jobs"}


def test_active_browser_worker_consumes_browser_units():
    scheduler = AdaptiveScheduler(capacity_units=4, max_jobs=5, reserve_units=1)
    state = snapshot()
    state = ResourceSnapshot(
        **{
            **state.__dict__,
            "inventory": WorkerInventory(active=1, active_capacity_units=3),
        }
    )
    decision = scheduler.plan([JobSpec("new", "engineer")], state)
    assert decision.admitted == []
    assert decision.rejected["new"] == "capacity"
