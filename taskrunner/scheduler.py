"""Clock-driven scheduler that dispatches tasks due in the current minute."""

from __future__ import annotations

import datetime as dt
import logging
import time
from collections.abc import Callable, Sequence

from .executor import ExecutesTasks
from .models import ExecutionResult, Task


class DailyScheduler:
    """Dispatches tasks whose time matches the current minute.

    A synchronous implementation is provided, but dispatch is isolated in
    ``_dispatch`` and ``_dispatch_async`` so an async or queue-backed version can
    override it without changing ``run_once``.
    """

    def __init__(
        self,
        tasks: Sequence[Task],
        executor: ExecutesTasks,
        clock: Callable[[], dt.datetime],
        tick: float = 60.0,
        logger: logging.Logger | None = None,
    ) -> None:
        self._tasks = list(tasks)
        self._executor = executor
        self._clock = clock
        self._tick = tick
        self._logger = logger or logging.getLogger(__name__)
        self._processed: set[tuple[dt.date, int, int]] = set()

    def run_once(self) -> list[ExecutionResult]:
        """Execute all tasks due at the current minute and return their results.

        Calling ``run_once`` twice within the same minute is a no-op the second
        time, so a fast loop cannot double-execute tasks.
        """
        now = self._clock()
        minute = (now.date(), now.hour, now.minute)
        self._processed = {entry for entry in self._processed if entry[0] == now.date()}
        if minute in self._processed:
            self._logger.debug(
                "minute %02d:%02d already processed; skipping", now.hour, now.minute
            )
            return []
        self._processed.add(minute)

        due = [
            task
            for task in self._tasks
            if task.at.hour == now.hour and task.at.minute == now.minute
        ]
        if not due:
            self._logger.debug("no due tasks at %02d:%02d", now.hour, now.minute)
            return []
        self._logger.info(
            "dispatching %d task(s) due at %02d:%02d", len(due), now.hour, now.minute
        )
        return self._dispatch(due)

    async def _dispatch_async(self, tasks: Sequence[Task]) -> list[ExecutionResult]:
        """Async seam for future queue-backed dispatch."""
        return self._dispatch(tasks)

    def _dispatch(self, tasks: Sequence[Task]) -> list[ExecutionResult]:
        results: list[ExecutionResult] = []
        for task in tasks:
            try:
                results.append(self._executor.execute(task))
            except Exception:
                self._logger.exception(
                    "dispatch failed task=%s user=%s", task.id, task.user
                )
        return results

    def run_forever(self) -> None:
        """Poll on ``tick`` seconds until interrupted."""
        self._logger.info("scheduler started tick=%.0fs", self._tick)
        try:
            while True:
                self.run_once()
                time.sleep(self._tick)
        except KeyboardInterrupt:
            self._logger.info("scheduler stopped")
