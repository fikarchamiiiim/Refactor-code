"""Tests for action strategies and the registry."""

from __future__ import annotations

import logging
from collections.abc import Callable

import pytest

from taskrunner.errors import StrategyNotFoundError
from taskrunner.models import Task
from taskrunner.strategies import DeleteStrategy, StrategyRegistry, SyncStrategy

TaskFactory = Callable[..., Task]


def test_default_registry_resolves_builtins() -> None:
    registry = StrategyRegistry.default()

    assert set(registry.actions()) == {"sync", "backup", "delete"}
    assert isinstance(registry.get("sync"), SyncStrategy)


def test_unknown_action_raises() -> None:
    with pytest.raises(StrategyNotFoundError, match="missing"):
        StrategyRegistry.default().get("missing")


def test_describe_includes_name_and_target(task_factory: TaskFactory) -> None:
    assert SyncStrategy().describe(task_factory()) == "sync /data/x"


def test_sync_honours_dry_run_param(
    task_factory: TaskFactory, caplog: pytest.LogCaptureFixture
) -> None:
    task = task_factory(params={"dry_run": True})

    with caplog.at_level(logging.INFO):
        SyncStrategy().execute(task)

    assert any("dry-run sync" in record.message for record in caplog.records)


def test_delete_logs_recursive_flag(
    task_factory: TaskFactory, caplog: pytest.LogCaptureFixture
) -> None:
    task = task_factory(action="delete", params={"recursive": True})

    with caplog.at_level(logging.WARNING):
        DeleteStrategy().execute(task)

    assert any("recursive=True" in record.message for record in caplog.records)
