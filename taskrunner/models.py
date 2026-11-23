"""Typed task and execution-result models."""

from __future__ import annotations

import datetime as dt
import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

from .errors import InvalidTaskError

ExecutionStatus = Literal["ok", "failed", "skipped"]
_TIME_PATTERN = re.compile(r"^\d{2}:\d{2}$")


def _empty_params() -> Mapping[str, object]:
    return MappingProxyType({})


@dataclass(frozen=True, slots=True)
class Task:
    """A declarative unit of work scheduled at a specific minute of the day."""

    id: str
    user: str
    at: dt.time
    action: str
    target: str
    params: Mapping[str, object] = field(default_factory=_empty_params)

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> Task:
        """Build a validated task from a raw dictionary payload.

        Raises:
            InvalidTaskError: when a required field is missing or malformed.
        """
        user = _require_non_empty_str(payload, "user")
        action = _require_non_empty_str(payload, "action")
        target = _require_non_empty_str(payload, "target")
        at = _parse_time(payload)
        task_id = _parse_id(payload)
        params = _parse_params(payload)
        return cls(id=task_id, user=user, at=at, action=action, target=target, params=params)


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Outcome of attempting to execute a single task."""

    task_id: str
    status: ExecutionStatus
    detail: str
    duration_ms: float


def _require_non_empty_str(payload: Mapping[str, object], name: str) -> str:
    if name not in payload:
        raise InvalidTaskError(name, "is required")
    value = payload[name]
    if not isinstance(value, str) or not value.strip():
        raise InvalidTaskError(name, "must be a non-empty string")
    return value


def _parse_time(payload: Mapping[str, object]) -> dt.time:
    if "time" not in payload:
        raise InvalidTaskError("time", "is required in HH:MM format")
    raw = payload["time"]
    if not isinstance(raw, str):
        raise InvalidTaskError("time", "must be a string in HH:MM format")
    if not _TIME_PATTERN.match(raw):
        raise InvalidTaskError("time", f"expected zero-padded HH:MM, got {raw!r}")
    try:
        return dt.datetime.strptime(raw, "%H:%M").time()
    except ValueError as exc:
        raise InvalidTaskError("time", f"expected HH:MM, got {raw!r}") from exc


def _parse_id(payload: Mapping[str, object]) -> str:
    raw = payload.get("id")
    if raw is None:
        return str(uuid.uuid4())
    if not isinstance(raw, str) or not raw.strip():
        raise InvalidTaskError("id", "must be a non-empty string")
    return raw


def _parse_params(payload: Mapping[str, object]) -> Mapping[str, object]:
    raw = payload.get("params", {})
    if raw is None:
        return _empty_params()
    if not isinstance(raw, Mapping):
        raise InvalidTaskError("params", "must be a mapping")
    if not all(isinstance(key, str) for key in raw):
        raise InvalidTaskError("params", "keys must be strings")
    return MappingProxyType(dict(raw))
