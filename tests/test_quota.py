"""Tests for per-user daily quota accounting."""

from __future__ import annotations

import pytest
from conftest import FakeClock

from taskrunner.errors import QuotaExceededError
from taskrunner.quota import QuotaManager


def test_consume_decrements_remaining(clock: FakeClock) -> None:
    quota = QuotaManager(clock, {"alice": 2})

    quota.consume("alice")

    assert quota.used("alice") == 1
    assert quota.remaining("alice") == 1


def test_consume_raises_when_daily_quota_exhausted(clock: FakeClock) -> None:
    quota = QuotaManager(clock, {"alice": 1})
    quota.consume("alice")

    with pytest.raises(QuotaExceededError, match="alice"):
        quota.consume("alice")


def test_check_is_false_when_quota_exhausted(clock: FakeClock) -> None:
    quota = QuotaManager(clock, {"alice": 1})

    assert quota.check("alice") is True
    quota.consume("alice")

    assert quota.check("alice") is False


def test_daily_reset_restores_quota(clock: FakeClock) -> None:
    quota = QuotaManager(clock, {"alice": 1})
    quota.consume("alice")

    clock.advance(days=1)

    assert quota.check("alice") is True
    assert quota.used("alice") == 0
    assert quota.remaining("alice") == 1


def test_unknown_user_has_no_quota(clock: FakeClock) -> None:
    quota = QuotaManager(clock)

    assert quota.check("ghost") is False
    assert quota.remaining("ghost") == 0
    with pytest.raises(QuotaExceededError):
        quota.consume("ghost")


def test_negative_limit_is_rejected(clock: FakeClock) -> None:
    quota = QuotaManager(clock)

    with pytest.raises(ValueError, match=">= 0"):
        quota.set_quota("alice", -1)
