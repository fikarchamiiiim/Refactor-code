"""Tests for task payload validation and parsing."""

from __future__ import annotations

import datetime as dt

import pytest

from taskrunner.errors import InvalidTaskError
from taskrunner.models import Task


def test_from_dict_parses_time_and_generates_id() -> None:
    task = Task.from_dict(
        {"user": "alice", "time": "12:05", "action": "sync", "target": "/data/x"}
    )

    assert task.at == dt.time(12, 5)
    assert task.id
    assert task.params == {}


def test_from_dict_uses_supplied_id() -> None:
    task = Task.from_dict(
        {
            "id": "abc",
            "user": "alice",
            "time": "12:05",
            "action": "sync",
            "target": "/data/x",
        }
    )

    assert task.id == "abc"


def test_from_dict_missing_field_names_the_offender() -> None:
    with pytest.raises(InvalidTaskError, match="user"):
        Task.from_dict({"time": "12:05", "action": "sync", "target": "/data/x"})


def test_from_dict_rejects_bad_time_format() -> None:
    with pytest.raises(InvalidTaskError, match="time"):
        Task.from_dict(
            {"user": "alice", "time": "noon", "action": "sync", "target": "/data/x"}
        )


def test_from_dict_rejects_non_padded_time() -> None:
    with pytest.raises(InvalidTaskError, match="time"):
        Task.from_dict(
            {"user": "alice", "time": "1:5", "action": "sync", "target": "/data/x"}
        )


def test_from_dict_rejects_non_mapping_params() -> None:
    with pytest.raises(InvalidTaskError, match="params"):
        Task.from_dict(
            {
                "user": "alice",
                "time": "12:05",
                "action": "sync",
                "target": "/data/x",
                "params": [1, 2],
            }
        )


def test_from_dict_preserves_params() -> None:
    task = Task.from_dict(
        {
            "user": "alice",
            "time": "12:05",
            "action": "sync",
            "target": "/data/x",
            "params": {"dry_run": True},
        }
    )

    assert task.params == {"dry_run": True}


def test_from_dict_rejects_non_string_param_keys() -> None:
    with pytest.raises(InvalidTaskError, match="params"):
        Task.from_dict(
            {
                "user": "alice",
                "time": "12:05",
                "action": "sync",
                "target": "/data/x",
                "params": {1: "value"},
            }
        )


def test_params_are_read_only() -> None:
    task = Task.from_dict(
        {
            "user": "alice",
            "time": "12:05",
            "action": "sync",
            "target": "/data/x",
            "params": {"dry_run": True},
        }
    )

    with pytest.raises(TypeError):
        task.params["extra"] = "value"  # type: ignore[index]


def test_from_dict_treats_null_params_as_empty() -> None:
    task = Task.from_dict(
        {
            "user": "alice",
            "time": "12:05",
            "action": "sync",
            "target": "/data/x",
            "params": None,
        }
    )

    assert task.params == {}
