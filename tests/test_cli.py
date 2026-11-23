"""Tests for the CLI wiring and its error exits."""

from __future__ import annotations

import json
import logging
import pathlib

import pytest

from taskrunner import cli


@pytest.fixture(autouse=True)
def _silence_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "configure_logging", lambda **_: None)


def test_main_once_runs_sample_tasks(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        exit_code = cli.main(["--once", "--now", "12:00"])

    assert exit_code == 0
    assert any("run complete tasks=3" in record.message for record in caplog.records)


def test_main_loads_tasks_from_file(
    tmp_path: pathlib.Path, caplog: pytest.LogCaptureFixture
) -> None:
    tasks_path = tmp_path / "tasks.json"
    tasks_path.write_text(
        json.dumps(
            [{"user": "alice", "time": "12:00", "action": "sync", "target": "/data/x"}]
        ),
        encoding="utf-8",
    )

    with caplog.at_level(logging.INFO):
        exit_code = cli.main(
            ["--once", "--now", "12:00", "--tasks", str(tasks_path)]
        )

    assert exit_code == 0
    assert any("run complete tasks=1" in record.message for record in caplog.records)


def test_main_returns_2_for_invalid_now(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR):
        exit_code = cli.main(["--once", "--now", "noon"])

    assert exit_code == 2
    assert any("failed to load configuration" in record.message for record in caplog.records)


def test_main_returns_2_for_invalid_task_payload(
    tmp_path: pathlib.Path, caplog: pytest.LogCaptureFixture
) -> None:
    tasks_path = tmp_path / "invalid_task.json"
    tasks_path.write_text(
        json.dumps([{"user": "alice", "action": "sync", "target": "/data/x"}]),
        encoding="utf-8",
    )

    with caplog.at_level(logging.ERROR):
        exit_code = cli.main(["--once", "--now", "12:00", "--tasks", str(tasks_path)])

    assert exit_code == 2
    assert any("failed to load configuration" in record.message for record in caplog.records)


def test_main_returns_2_for_negative_tick() -> None:
    assert cli.main(["--once", "--tick", "-1"]) == 2


def test_main_honours_limits_file(
    tmp_path: pathlib.Path, caplog: pytest.LogCaptureFixture
) -> None:
    tasks_path = tmp_path / "tasks.json"
    tasks_path.write_text(
        json.dumps(
            [
                {"user": "alice", "time": "12:00", "action": "sync", "target": "/a"},
                {"user": "alice", "time": "12:00", "action": "sync", "target": "/b"},
            ]
        ),
        encoding="utf-8",
    )
    limits_path = tmp_path / "limits.json"
    limits_path.write_text(json.dumps({"alice": 1}), encoding="utf-8")

    with caplog.at_level(logging.INFO):
        exit_code = cli.main(
            [
                "--once",
                "--now",
                "12:00",
                "--tasks",
                str(tasks_path),
                "--limits",
                str(limits_path),
            ]
        )

    assert exit_code == 0
    assert any(
        "tasks=2 (ok=1, failed=0, skipped=1)" in record.message
        for record in caplog.records
    )


def test_main_returns_2_for_invalid_limits(
    tmp_path: pathlib.Path, caplog: pytest.LogCaptureFixture
) -> None:
    limits_path = tmp_path / "limits.json"
    limits_path.write_text(json.dumps({"alice": -1}), encoding="utf-8")

    with caplog.at_level(logging.ERROR):
        exit_code = cli.main(["--once", "--limits", str(limits_path)])

    assert exit_code == 2
    assert any("failed to load configuration" in record.message for record in caplog.records)


def test_main_returns_2_for_invalid_json(
    tmp_path: pathlib.Path, caplog: pytest.LogCaptureFixture
) -> None:
    bad_path = tmp_path / "bad.json"
    bad_path.write_text("{not json", encoding="utf-8")

    with caplog.at_level(logging.ERROR):
        exit_code = cli.main(["--once", "--tasks", str(bad_path)])

    assert exit_code == 2
    assert any("failed to load configuration" in record.message for record in caplog.records)


def test_main_returns_2_for_non_array_payload(tmp_path: pathlib.Path) -> None:
    bad_path = tmp_path / "object.json"
    bad_path.write_text("{}", encoding="utf-8")

    assert cli.main(["--once", "--tasks", str(bad_path)]) == 2


def test_main_returns_2_for_non_object_task(tmp_path: pathlib.Path) -> None:
    bad_path = tmp_path / "scalar.json"
    bad_path.write_text("[1]", encoding="utf-8")

    assert cli.main(["--once", "--tasks", str(bad_path)]) == 2


def test_main_runs_forever_without_once_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    started: dict[str, bool] = {}

    class StubScheduler:
        def __init__(self, *args: object, **kwargs: object) -> None:
            pass

        def run_forever(self) -> None:
            started["ran"] = True

    monkeypatch.setattr(cli, "DailyScheduler", StubScheduler)

    assert cli.main([]) == 0
    assert started["ran"] is True
