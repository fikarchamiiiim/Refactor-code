"""Per-user, per-day quota accounting."""

from __future__ import annotations

import datetime as dt
import threading
from collections.abc import Callable, Mapping

from .errors import QuotaExceededError


class QuotaManager:
    """Owns quota policy only: no I/O and no logging of task outcomes.

    Unknown users default to a limit of zero, so they cannot execute tasks.
    Counts reset when the injected clock reports a new calendar day.
    """

    def __init__(
        self,
        clock: Callable[[], dt.datetime],
        limits: Mapping[str, int] | None = None,
    ) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._limits: dict[str, int] = {}
        self._used: dict[str, int] = {}
        self._days: dict[str, dt.date] = {}
        for user, limit in (limits or {}).items():
            self.set_quota(user, limit)

    def set_quota(self, user: str, limit: int) -> None:
        """Set the daily limit for a user, initialising their counters."""
        if limit < 0:
            raise ValueError(f"quota limit must be >= 0, got {limit}")
        with self._lock:
            self._limits[user] = limit
            self._used.setdefault(user, 0)
            self._days.setdefault(user, self._clock().date())

    def check(self, user: str) -> bool:
        """Return True when the user has quota remaining today."""
        with self._lock:
            self._roll_if_new_day(user)
            return self._used.get(user, 0) < self._limits.get(user, 0)

    def consume(self, user: str) -> None:
        """Record one execution, raising when the daily limit is exhausted."""
        with self._lock:
            self._roll_if_new_day(user)
            limit = self._limits.get(user, 0)
            used = self._used.get(user, 0)
            if used >= limit:
                raise QuotaExceededError(user)
            self._used[user] = used + 1

    def remaining(self, user: str) -> int:
        """Return the number of executions left today."""
        with self._lock:
            self._roll_if_new_day(user)
            return max(0, self._limits.get(user, 0) - self._used.get(user, 0))

    def used(self, user: str) -> int:
        """Return the number of executions recorded today."""
        with self._lock:
            self._roll_if_new_day(user)
            return self._used.get(user, 0)

    def _roll_if_new_day(self, user: str) -> None:
        today = self._clock().date()
        if self._days.get(user) != today:
            self._days[user] = today
            self._used[user] = 0
