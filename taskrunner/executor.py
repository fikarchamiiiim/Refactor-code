"""Task execution pipeline: validate -> resolve -> quota -> dispatch -> result."""

from __future__ import annotations

import logging
import time
from typing import Protocol

from .errors import InvalidTaskError, QuotaExceededError, StrategyNotFoundError
from .models import ExecutionResult, ExecutionStatus, Task
from .quota import QuotaManager
from .strategies import StrategyRegistry


class ExecutesTasks(Protocol):
    """Structural interface the scheduler depends on."""

    def execute(self, task: Task) -> ExecutionResult: ...


class TaskExecutor:
    """Executes tasks and turns every outcome into an ``ExecutionResult``.

    Task-level failures are never propagated to the caller: they are logged and
    reported as a ``failed`` or ``skipped`` result so a scheduler can continue.
    """

    def __init__(
        self,
        registry: StrategyRegistry,
        quota: QuotaManager,
        logger: logging.Logger | None = None,
    ) -> None:
        self._registry = registry
        self._quota = quota
        self._logger = logger or logging.getLogger(__name__)

    def execute(self, task: Task) -> ExecutionResult:
        """Run ``task`` and return its result without raising task-level errors."""
        started = time.perf_counter()
        try:
            self._validate(task)
            strategy = self._registry.get(task.action)
            self._logger.debug("dispatch %s task=%s", strategy.describe(task), task.id)
            if not self._quota.check(task.user):
                self._logger.warning(
                    "quota exhausted task=%s user=%s action=%s; skipping",
                    task.id,
                    task.user,
                    task.action,
                )
                return self._result(task, "skipped", "daily quota exhausted", started)
            try:
                self._quota.consume(task.user)
            except QuotaExceededError:
                self._logger.warning(
                    "quota exhausted during consume task=%s user=%s; skipping",
                    task.id,
                    task.user,
                )
                return self._result(task, "skipped", "daily quota exhausted", started)
            strategy.execute(task)
        except InvalidTaskError as exc:
            self._logger.error("invalid task task=%s: %s", task.id, exc)
            return self._result(task, "failed", str(exc), started)
        except StrategyNotFoundError as exc:
            self._logger.error(
                "unknown action task=%s user=%s: %s", task.id, task.user, exc
            )
            return self._result(task, "failed", str(exc), started)
        except Exception:
            self._logger.exception(
                "execution failed task=%s user=%s action=%s target=%s",
                task.id,
                task.user,
                task.action,
                task.target,
            )
            return self._result(task, "failed", "execution error", started)

        self._logger.info(
            "executed task=%s user=%s action=%s target=%s duration_ms=%.2f",
            task.id,
            task.user,
            task.action,
            task.target,
            _elapsed_ms(started),
        )
        return self._result(task, "ok", "executed", started)

    def _validate(self, task: Task) -> None:
        if not task.target.strip():
            raise InvalidTaskError("target", "must be a non-empty string")

    def _result(
        self,
        task: Task,
        status: ExecutionStatus,
        detail: str,
        started: float,
    ) -> ExecutionResult:
        return ExecutionResult(
            task_id=task.id,
            status=status,
            detail=detail,
            duration_ms=_elapsed_ms(started),
        )


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000.0
