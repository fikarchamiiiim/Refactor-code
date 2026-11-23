"""Declarative daily task runner with per-user quotas."""

from .errors import (
    InvalidTaskError,
    QuotaExceededError,
    StrategyNotFoundError,
    TaskRunnerError,
)
from .executor import ExecutesTasks, TaskExecutor
from .models import ExecutionResult, ExecutionStatus, Task
from .quota import QuotaManager
from .scheduler import DailyScheduler
from .strategies import (
    ActionStrategy,
    BackupStrategy,
    DeleteStrategy,
    StrategyRegistry,
    SyncStrategy,
)

__all__ = [
    "ActionStrategy",
    "BackupStrategy",
    "DailyScheduler",
    "DeleteStrategy",
    "ExecutionResult",
    "ExecutionStatus",
    "ExecutesTasks",
    "InvalidTaskError",
    "QuotaExceededError",
    "QuotaManager",
    "StrategyNotFoundError",
    "StrategyRegistry",
    "SyncStrategy",
    "Task",
    "TaskExecutor",
    "TaskRunnerError",
]
