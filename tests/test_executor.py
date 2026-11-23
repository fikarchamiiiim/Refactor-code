"""Tests for the execution pipeline and its failure handling."""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Callable

import pytest
from conftest import FakeClock

from taskrunner.executor import TaskExecutor
from taskrunner.models import Task
from taskrunner.quota import QuotaManager
from taskrunner.strategies import ActionStrategy, StrategyRegistry

TaskFactory = Callable[..., Task]


class FailingStrategy(ActionStrategy):
    name = "boom"

    def execute(self, task: Task) -> None:
        raise RuntimeError("strategy exploded")


def _build(clock: FakeClock, limits: dict[str, int]) -> tuple[TaskExecutor, QuotaManager]:
    registry = StrategyRegistry.default()
    registry.register(FailingStrategy())
    quota = QuotaManager(clock, limits)
    return TaskExecutor(registry, quota), quota


def test_execute_returns_ok_and_consumes_quota(
    clock: FakeClock, task_factory: TaskFactory
) -> None:
    executor, quota = _build(clock, {"alice": 3})

    result = executor.execute(task_factory())

    assert result.status == "ok"
    assert result.task_id == "t1"
    assert result.duration_ms >= 0
    assert quota.used("alice") == 1


def test_unknown_action_returns_failed(clock: FakeClock, task_factory: TaskFactory) -> None:
    executor, _ = _build(clock, {"alice": 3})

    result = executor.execute(task_factory(action="archive"))

    assert result.status == "failed"
    assert "no strategy registered" in result.detail


def test_exhausted_quota_returns_skipped_with_warning(
    clock: FakeClock, task_factory: TaskFactory, caplog: pytest.LogCaptureFixture
) -> None:
    executor, _ = _build(clock, {"alice": 0})

    with caplog.at_level(logging.WARNING):
        result = executor.execute(task_factory())

    assert result.status == "skipped"
    assert any(
        "quota exhausted" in record.message and record.levelno == logging.WARNING
        for record in caplog.records
    )


def test_strategy_exception_returns_failed_and_logs(
    clock: FakeClock, task_factory: TaskFactory, caplog: pytest.LogCaptureFixture
) -> None:
    executor, quota = _build(clock, {"alice": 3})

    with caplog.at_level(logging.ERROR):
        result = executor.execute(task_factory(action="boom"))

    assert result.status == "failed"
    assert any(record.exc_info is not None for record in caplog.records)
    assert quota.used("alice") == 1


def test_blank_target_returns_failed(clock: FakeClock) -> None:
    executor, quota = _build(clock, {"alice": 3})
    task = Task(id="t1", user="alice", at=dt.time(12, 0), action="sync", target="   ")

    result = executor.execute(task)

    assert result.status == "failed"
    assert "target" in result.detail
    assert quota.used("alice") == 0


def test_two_tasks_for_same_user_share_quota(
    clock: FakeClock, task_factory: TaskFactory
) -> None:
    executor, quota = _build(clock, {"alice": 1})

    first = executor.execute(task_factory(id="a"))
    second = executor.execute(task_factory(id="b"))

    assert first.status == "ok"
    assert second.status == "skipped"
    assert quota.used("alice") == 1


def test_params_reach_the_strategy(
    clock: FakeClock, task_factory: TaskFactory, caplog: pytest.LogCaptureFixture
) -> None:
    executor, _ = _build(clock, {"alice": 3})

    with caplog.at_level(logging.INFO):
        executor.execute(task_factory(params={"dry_run": True}))

    assert any("dry-run sync" in record.message for record in caplog.records)
