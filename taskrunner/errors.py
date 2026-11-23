"""Domain exceptions for the task runner."""

from __future__ import annotations


class TaskRunnerError(Exception):
    """Base class for every error raised by the task runner."""


class InvalidTaskError(TaskRunnerError):
    """Raised when a task payload fails validation."""

    def __init__(self, field: str, reason: str) -> None:
        self.field = field
        super().__init__(f"field '{field}': {reason}")


class QuotaExceededError(TaskRunnerError):
    """Raised when a user has no quota left for the current day."""

    def __init__(self, user: str) -> None:
        self.user = user
        super().__init__(f"daily quota exhausted for user '{user}'")


class StrategyNotFoundError(TaskRunnerError):
    """Raised when no strategy is registered for an action."""

    def __init__(self, action: str) -> None:
        self.action = action
        super().__init__(f"no strategy registered for action '{action}'")
