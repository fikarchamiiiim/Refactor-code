"""Tests for logging setup and the JSON formatter."""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Iterator

import pytest

from taskrunner.logging_config import JsonFormatter, configure_logging


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


def test_configure_logging_installs_text_handler() -> None:
    configure_logging("DEBUG")

    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert len(root.handlers) == 1
    assert not isinstance(root.handlers[0].formatter, JsonFormatter)


def test_configure_logging_installs_json_handler() -> None:
    configure_logging("INFO", json_logs=True)

    formatter = logging.getLogger().handlers[0].formatter
    assert isinstance(formatter, JsonFormatter)


def test_json_formatter_emits_structured_record() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        "taskrunner.test", logging.INFO, __file__, 1, "hello %s", ("world",), None
    )

    payload = json.loads(formatter.format(record))

    assert payload["level"] == "INFO"
    assert payload["logger"] == "taskrunner.test"
    assert payload["message"] == "hello world"


def test_json_formatter_includes_exception() -> None:
    formatter = JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord(
            "taskrunner.test", logging.ERROR, __file__, 1, "failed", (), sys.exc_info()
        )

    payload = json.loads(formatter.format(record))

    assert "ValueError: boom" in payload["exception"]
