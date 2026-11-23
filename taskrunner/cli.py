"""Command-line entrypoint wiring the modules together."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
from collections.abc import Callable, Sequence
from pathlib import Path

from .errors import TaskRunnerError
from .executor import TaskExecutor
from .logging_config import configure_logging
from .models import Task
from .quota import QuotaManager
from .scheduler import DailyScheduler
from .strategies import StrategyRegistry

SAMPLE_TASKS: list[dict[str, object]] = [
    {"user": "alice", "time": "12:00", "action": "sync", "target": "/data/x"},
    {"user": "bob", "time": "12:00", "action": "backup", "target": "/srv/y"},
    {"user": "alice", "time": "12:00", "action": "delete", "target": "/tmp/z"},
]
SAMPLE_LIMITS: dict[str, int] = {"alice": 3, "bob": 5}

_logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(description="Run declarative daily tasks.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="run one scheduling pass and exit instead of looping forever",
    )
    parser.add_argument(
        "--tasks",
        metavar="PATH",
        help="JSON file containing an array of task objects (defaults to the sample set)",
    )
    parser.add_argument(
        "--now",
        metavar="HH:MM",
        help="pin the clock to this time today, useful for demos and smoke tests",
    )
    parser.add_argument(
        "--limits",
        metavar="PATH",
        help="JSON object mapping user to daily quota (defaults to the sample limits)",
    )
    parser.add_argument(
        "--tick", type=float, default=60.0, help="seconds between scheduling passes"
    )
    parser.add_argument("--level", default="INFO", help="logging level name")
    parser.add_argument(
        "--json-logs", action="store_true", help="emit structured JSON log lines"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments, wire dependencies, and run the scheduler."""
    args = build_parser().parse_args(argv)
    configure_logging(level=args.level, json_logs=args.json_logs)

    try:
        if args.tick < 0:
            raise ValueError("--tick must be >= 0")
        clock = _build_clock(args.now)
        payload = _load_tasks(args.tasks)
        tasks = [Task.from_dict(item) for item in payload]
        limits = _load_limits(args.limits)
    except (OSError, ValueError, TaskRunnerError) as exc:
        _logger.error("failed to load configuration: %s", exc)
        return 2

    quota = QuotaManager(clock=clock, limits=limits)
    executor = TaskExecutor(StrategyRegistry.default(), quota)
    scheduler = DailyScheduler(tasks, executor, clock=clock, tick=args.tick)

    if args.once:
        results = scheduler.run_once()
        summary = ", ".join(
            f"{status}={sum(1 for result in results if result.status == status)}"
            for status in ("ok", "failed", "skipped")
        )
        _logger.info("run complete tasks=%d (%s)", len(results), summary)
        return 0

    scheduler.run_forever()
    return 0


def _build_clock(now: str | None) -> Callable[[], dt.datetime]:
    if now is None:
        return dt.datetime.now
    parsed = dt.datetime.strptime(now, "%H:%M").time()
    fixed_day = dt.date.today()
    return lambda: dt.datetime.combine(fixed_day, parsed)


def _load_limits(path: str | None) -> dict[str, int]:
    if path is None:
        return dict(SAMPLE_LIMITS)
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("limits file must contain a JSON object")
    limits: dict[str, int] = {}
    for user, limit in raw.items():
        if (
            not isinstance(user, str)
            or isinstance(limit, bool)
            or not isinstance(limit, int)
            or limit < 0
        ):
            raise ValueError(f"invalid quota for {user!r}: expected a non-negative integer")
        limits[user] = limit
    return limits


def _load_tasks(path: str | None) -> list[dict[str, object]]:
    if path is None:
        return [dict(item) for item in SAMPLE_TASKS]
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("tasks file must contain a JSON array")
    items: list[dict[str, object]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"task at index {index} must be a JSON object")
        items.append(dict(item))
    return items


if __name__ == "__main__":
    raise SystemExit(main())
