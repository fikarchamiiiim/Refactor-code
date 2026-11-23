"""Tests for minute-based dispatch and scheduler resilience."""

from __future__ import annotations

import asyncio
import datetime as dt
from collections.abc import Callable

from conftest import FakeClock

from taskrunner.executor import TaskExecutor
from taskrunner.models import ExecutionResult, Task
from taskrunner.quota import QuotaManager
from taskrunner.scheduler import DailyScheduler
from taskrunner.strategies import ActionStrategy, StrategyRegistry

TaskFactory = Callable[..., Task]


class FailingStrategy(ActionStrategy):
    name = "boom"

    def execute(self, task: Task) -> None:
        raise RuntimeError("strategy exploded")


class ExplodingExecutor:
    """Executor stub that always raises, to test scheduler containment."""

    def __init__(self) -> None:
        self.calls = 0

    def execute(self, task: Task) -> ExecutionResult:
        self.calls += 1
        raise RuntimeError("dispatch exploded")


def _scheduler(
    clock: FakeClock, tasks: list[Task], limits: dict[str, int]
) -> tuple[DailyScheduler, QuotaManager]:
    registry = StrategyRegistry.default()
    registry.register(FailingStrategy())
    quota = QuotaManager(clock, limits)
    executor = TaskExecutor(registry, quota)
    return DailyScheduler(tasks, executor, clock=clock), quota


def test_run_once_executes_due_task(clock: FakeClock, task_factory: TaskFactory) -> None:
    scheduler, quota = _scheduler(clock, [task_factory()], {"alice": 3})

    results = scheduler.run_once()

    assert [result.status for result in results] == ["ok"]
    assert quota.used("alice") == 1


def test_run_once_skips_non_due_tasks(clock: FakeClock, task_factory: TaskFactory) -> None:
    scheduler, quota = _scheduler(clock, [task_factory(time="13:00")], {"alice": 3})

    assert scheduler.run_once() == []
    assert quota.used("alice") == 0


def test_multiple_tasks_for_one_user_share_quota_in_one_tick(
    clock: FakeClock, task_factory: TaskFactory
) -> None:
    tasks = [task_factory(id="a"), task_factory(id="b"), task_factory(id="c")]
    scheduler, quota = _scheduler(clock, tasks, {"alice": 3})

    results = scheduler.run_once()

    assert [result.status for result in results] == ["ok", "ok", "ok"]
    assert quota.used("alice") == 3


def test_failing_task_does_not_stop_scheduler(
    clock: FakeClock, task_factory: TaskFactory
) -> None:
    tasks = [task_factory(id="bad", action="boom"), task_factory(id="good")]
    scheduler, quota = _scheduler(clock, tasks, {"alice": 3})

    results = scheduler.run_once()

    assert [result.status for result in results] == ["failed", "ok"]
    assert quota.used("alice") == 2


def test_run_once_is_idempotent_within_a_minute(
    clock: FakeClock, task_factory: TaskFactory
) -> None:
    scheduler, quota = _scheduler(clock, [task_factory()], {"alice": 3})

    assert len(scheduler.run_once()) == 1
    assert scheduler.run_once() == []
    assert quota.used("alice") == 1


def test_dispatch_async_seam_delegates(
    clock: FakeClock, task_factory: TaskFactory
) -> None:
    scheduler, quota = _scheduler(clock, [], {"alice": 3})

    results = asyncio.run(scheduler._dispatch_async([task_factory()]))

    assert [result.status for result in results] == ["ok"]
    assert quota.used("alice") == 1


def test_run_forever_exits_cleanly_on_interrupt(
    clock: FakeClock, task_factory: TaskFactory
) -> None:
    scheduler, _ = _scheduler(clock, [task_factory()], {"alice": 3})
    calls = {"n": 0}

    def interrupting_clock() -> dt.datetime:
        calls["n"] += 1
        if calls["n"] > 1:
            raise KeyboardInterrupt
        return clock()

    scheduler._clock = interrupting_clock
    scheduler._tick = 0.0

    scheduler.run_forever()

    assert calls["n"] == 2


def test_executor_crash_is_contained(
    clock: FakeClock, task_factory: TaskFactory
) -> None:
    exploding = ExplodingExecutor()
    tasks = [task_factory(id="a"), task_factory(id="b")]
    scheduler = DailyScheduler(tasks, exploding, clock=clock)

    results = scheduler.run_once()

    assert results == []
    assert exploding.calls == 2
