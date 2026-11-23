"""Action strategies and their explicit registry."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import ClassVar

from .errors import StrategyNotFoundError
from .models import Task


class ActionStrategy(ABC):
    """Contract for a single task action.

    Each concrete strategy takes a fully validated ``Task`` and performs the
    action, raising on failure so the executor can record the outcome.
    """

    name: ClassVar[str]

    @abstractmethod
    def execute(self, task: Task) -> None:
        """Perform the action described by ``task``."""

    def describe(self, task: Task) -> str:
        """Return a short human-readable description for logging."""
        return f"{self.name} {task.target}"


class SyncStrategy(ActionStrategy):
    """Simulates syncing a target directory."""

    name = "sync"

    def execute(self, task: Task) -> None:
        dry_run = bool(task.params.get("dry_run", False))
        mode = "dry-run sync" if dry_run else "sync"
        logging.getLogger(__name__).info("%s source=%s", mode, task.target)


class BackupStrategy(ActionStrategy):
    """Simulates archiving a target directory."""

    name = "backup"

    def execute(self, task: Task) -> None:
        archive = task.params.get("archive", f"{task.target}.tar")
        logging.getLogger(__name__).info("backup source=%s archive=%s", task.target, archive)


class DeleteStrategy(ActionStrategy):
    """Simulates deleting a target path."""

    name = "delete"

    def execute(self, task: Task) -> None:
        recursive = bool(task.params.get("recursive", False))
        logging.getLogger(__name__).warning(
            "delete path=%s recursive=%s", task.target, recursive
        )


class StrategyRegistry:
    """Maps action names to strategies; registration is explicit."""

    def __init__(self) -> None:
        self._strategies: dict[str, ActionStrategy] = {}

    def register(self, strategy: ActionStrategy) -> None:
        """Register a strategy under its ``name``, replacing any existing one."""
        self._strategies[strategy.name] = strategy

    def get(self, action: str) -> ActionStrategy:
        """Return the strategy for ``action``, or raise ``StrategyNotFoundError``."""
        try:
            return self._strategies[action]
        except KeyError as exc:
            raise StrategyNotFoundError(action) from exc

    def actions(self) -> tuple[str, ...]:
        """Return the registered action names, sorted."""
        return tuple(sorted(self._strategies))

    @classmethod
    def default(cls) -> StrategyRegistry:
        """Build a registry with the built-in strategies registered explicitly."""
        registry = cls()
        for strategy in (SyncStrategy(), BackupStrategy(), DeleteStrategy()):
            registry.register(strategy)
        return registry
