"""Shared test fixtures: a controllable clock and task factory."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

import pytest

from taskrunner.models import Task


class FakeClock:
    """Deterministic clock that tests can move at will."""

    def __init__(self, moment: dt.datetime) -> None:
        self._moment = moment

    def __call__(self) -> dt.datetime:
        return self._moment

    def set(self, moment: dt.datetime) -> None:
        self._moment = moment

    def advance(self, **kwargs: float) -> None:
        self._moment += dt.timedelta(**kwargs)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(dt.datetime(2026, 1, 2, 12, 0))


@pytest.fixture
def task_factory() -> Callable[..., Task]:
    def factory(**overrides: object) -> Task:
        payload: dict[str, object] = {
            "id": "t1",
            "user": "alice",
            "time": "12:00",
            "action": "sync",
            "target": "/data/x",
        }
        payload.update(overrides)
        return Task.from_dict(payload)

    return factory
