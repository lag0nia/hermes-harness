"""Pure, injectable resource scheduling decisions for Hermes workers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class LoadAverage:
    one: float
    five: float
    fifteen: float


@dataclass(frozen=True)
class WorkerInventory:
    active: int = 0
    queued: int = 0
    active_capacity_units: int | None = None


@dataclass(frozen=True)
class BrowserSessionState:
    active: bool = False
    session_id: str | None = None


@dataclass(frozen=True)
class ResourceSnapshot:
    cgroup_current_bytes: int
    cgroup_max_bytes: int
    load: LoadAverage
    inventory: WorkerInventory = field(default_factory=WorkerInventory)
    browser: BrowserSessionState = field(default_factory=BrowserSessionState)

    @property
    def memory_ratio(self) -> float:
        return self.cgroup_current_bytes / self.cgroup_max_bytes if self.cgroup_max_bytes else 1.0


class ResourceAdapter(Protocol):
    def snapshot(self) -> ResourceSnapshot: ...


@dataclass(frozen=True)
class JobSpec:
    job_id: str
    kind: str = "remote"
    priority: int = 0
    critical: bool = False
    units: int | None = None

    @property
    def capacity(self) -> int:
        if self.units is not None:
            return self.units
        return {"engineer": 2, "coder": 2, "browser": 3}.get(self.kind, 1)


@dataclass(frozen=True)
class ScheduleDecision:
    admitted: list[JobSpec] = field(default_factory=list)
    paused: list[str] = field(default_factory=list)
    resumed: list[str] = field(default_factory=list)
    rejected: dict[str, str] = field(default_factory=dict)
    snapshot: ResourceSnapshot | None = None


class AdaptiveScheduler:
    """A deterministic scheduler; it emits decisions and never starts/stops workers."""

    def __init__(
        self,
        *,
        capacity_units: int = 4,
        max_jobs: int = 5,
        reserve_units: int = 1,
        admission_memory_ratio: float = 0.75,
        pause_memory_ratio: float = 0.85,
        admission_load: float = 2.5,
        pause_load: float = 3.5,
        resume_memory_ratio: float = 0.70,
        resume_load: float = 3.0,
    ) -> None:
        self.capacity_units, self.max_jobs, self.reserve_units = (
            capacity_units,
            max_jobs,
            reserve_units,
        )
        self.admission_memory_ratio, self.pause_memory_ratio = (
            admission_memory_ratio,
            pause_memory_ratio,
        )
        self.admission_load, self.pause_load = admission_load, pause_load
        self.resume_memory_ratio, self.resume_load = resume_memory_ratio, resume_load
        self._paused: dict[str, JobSpec] = {}

    def observe(self, snapshot: ResourceSnapshot) -> ResourceSnapshot:
        return snapshot

    def plan(self, jobs: list[JobSpec], snapshot: ResourceSnapshot) -> ScheduleDecision:
        ordered = sorted(jobs, key=lambda job: (-job.priority, job.job_id))
        pressure = (
            snapshot.memory_ratio >= self.pause_memory_ratio or snapshot.load.one > self.pause_load
        )
        active_capacity = snapshot.inventory.active_capacity_units
        if active_capacity is None:
            active_capacity = snapshot.inventory.active
        if snapshot.browser.active and snapshot.inventory.active_capacity_units is None:
            active_capacity += 3
        active_jobs = snapshot.inventory.active + int(snapshot.browser.active)
        available = max(0, self.capacity_units - self.reserve_units - active_capacity)
        job_slots = max(0, self.max_jobs - active_jobs)
        admitted: list[JobSpec] = []
        rejected: dict[str, str] = {}
        browser_taken = snapshot.browser.active
        for job in ordered:
            if len(admitted) >= job_slots:
                rejected[job.job_id] = "max_jobs"
            elif job.kind == "browser" and browser_taken:
                rejected[job.job_id] = "browser_singleton"
            elif job.capacity > available:
                rejected[job.job_id] = "capacity"
            else:
                admitted.append(job)
                available -= job.capacity
                browser_taken |= job.kind == "browser"
        paused: list[str] = list(self._paused)
        if pressure:
            for job in admitted:
                if not job.critical and job.job_id not in self._paused:
                    paused.append(job.job_id)
                    self._paused[job.job_id] = job
            admitted = [job for job in admitted if job.critical]
        can_resume = (
            snapshot.memory_ratio <= self.resume_memory_ratio
            and snapshot.load.one <= self.resume_load
        )
        resumed: list[str] = []
        if can_resume:
            for job_id in list(self._paused):
                job = self._paused.pop(job_id)
                resumed.append(job_id)
        return ScheduleDecision(admitted, paused, resumed, rejected, snapshot)


class LinuxResourceAdapter:
    """Collect a snapshot through injectable readers (safe to use in tests)."""

    def __init__(
        self,
        *,
        current_path: str | Path = "/sys/fs/cgroup/memory.current",
        max_path: str | Path = "/sys/fs/cgroup/memory.max",
        load_reader: Callable[[], LoadAverage] | None = None,
        inventory_reader: Callable[[], WorkerInventory] | None = None,
        browser_reader: Callable[[], BrowserSessionState] | None = None,
    ) -> None:
        self.current_path, self.max_path = Path(current_path), Path(max_path)
        self.load_reader = load_reader or (lambda: LoadAverage(*__import__("os").getloadavg()))
        self.inventory_reader = inventory_reader or (lambda: WorkerInventory())
        self.browser_reader = browser_reader or (lambda: BrowserSessionState())

    def snapshot(self) -> ResourceSnapshot:
        current = read_cgroup_value(self.current_path) or 0
        maximum = read_cgroup_value(self.max_path) or current
        return ResourceSnapshot(
            current, maximum, self.load_reader(), self.inventory_reader(), self.browser_reader()
        )


def read_cgroup_value(path: str | Path) -> int | None:
    """Read cgroup v2 values, treating ``max`` as unlimited."""
    value = Path(path).read_text().strip()
    return None if value == "max" else int(value)
