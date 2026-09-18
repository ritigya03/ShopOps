import json
import logging
import sys

import pytest

from app.config import settings as app_settings
from app.observability.context import request_id_var, user_id_var
from app.observability.logging_setup import (
    ContextFilter,
    JsonFormatter,
    configure_logging,
)


@pytest.fixture
def restore_logging():
    """configure_logging() mutates global logger state — put it back afterwards.

    Without this, the JSON stream handler it installs on the root logger (and
    the uvicorn propagate flips) leak into every later test in the session.
    """
    root = logging.getLogger()
    saved_root_handlers = list(root.handlers)
    saved_root_level = root.level
    uvicorn_names = ("uvicorn", "uvicorn.access", "uvicorn.error")
    saved_uvicorn = {
        name: (list(logging.getLogger(name).handlers), logging.getLogger(name).propagate)
        for name in uvicorn_names
    }
    yield
    root.handlers[:] = saved_root_handlers
    root.setLevel(saved_root_level)
    for name, (handlers, propagate) in saved_uvicorn.items():
        lg = logging.getLogger(name)
        lg.handlers[:] = handlers
        lg.propagate = propagate


def _make_record(extra=None):
    record = logging.LogRecord(
        name="shopops.test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="hello", args=(), exc_info=None,
    )
    for key, value in (extra or {}).items():
        setattr(record, key, value)
    return record


def test_json_formatter_produces_valid_json_with_fixed_fields():
    payload = json.loads(JsonFormatter().format(_make_record()))
    assert payload["level"] == "INFO"
    assert payload["logger"] == "shopops.test"
    assert payload["message"] == "hello"
    assert "timestamp" in payload
    assert payload["request_id"] is None
    assert payload["user_id"] is None


def test_json_formatter_includes_extra_fields():
    payload = json.loads(JsonFormatter().format(_make_record(extra={"foo": "bar"})))
    assert payload["foo"] == "bar"


def test_context_filter_stamps_request_and_user_id():
    record = _make_record()
    token_r = request_id_var.set("req-42")
    token_u = user_id_var.set("user-7")
    try:
        ContextFilter().filter(record)
    finally:
        request_id_var.reset(token_r)
        user_id_var.reset(token_u)
    assert record.request_id == "req-42"
    assert record.user_id == "user-7"


def test_context_filter_stamps_none_when_unset():
    record = _make_record()
    ContextFilter().filter(record)
    assert record.request_id is None
    assert record.user_id is None


def test_configure_logging_skips_cloudwatch_when_group_unset(monkeypatch, restore_logging):
    monkeypatch.setattr(app_settings, "cloudwatch_log_group", None)
    configure_logging()
    handler_types = [type(h).__name__ for h in logging.getLogger().handlers]
    assert "CloudWatchLogHandler" not in handler_types


def test_json_formatter_includes_exception_traceback():
    try:
        raise ValueError("boom")
    except ValueError:
        record = _make_record()
        record.exc_info = sys.exc_info()

    payload = json.loads(JsonFormatter().format(record))
    assert "ValueError: boom" in payload["exception"]
    assert "Traceback (most recent call last)" in payload["exception"]


def test_json_formatter_includes_stack_info():
    record = _make_record()
    record.stack_info = "Stack (most recent call last):\n  fake frame"
    payload = json.loads(JsonFormatter().format(record))
    assert "fake frame" in payload["stack_info"]


def test_json_formatter_omits_exception_keys_when_absent():
    payload = json.loads(JsonFormatter().format(_make_record()))
    assert "exception" not in payload
    assert "stack_info" not in payload


def test_configure_logging_streams_to_stdout(monkeypatch, restore_logging):
    monkeypatch.setattr(app_settings, "cloudwatch_log_group", None)
    configure_logging()
    stream_handlers = [
        h for h in logging.getLogger().handlers if isinstance(h, logging.StreamHandler)
    ]
    assert stream_handlers
    assert all(h.stream is sys.stdout for h in stream_handlers)


def test_configure_logging_routes_uvicorn_loggers_through_root(monkeypatch, restore_logging):
    monkeypatch.setattr(app_settings, "cloudwatch_log_group", None)
    # Simulate uvicorn having installed its own handlers with propagate=False.
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers = [logging.StreamHandler()]
        lg.propagate = False

    configure_logging()

    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        lg = logging.getLogger(name)
        assert lg.handlers == []
        assert lg.propagate is True


def test_configure_logging_falls_back_to_info_on_invalid_log_level(monkeypatch, restore_logging):
    # configure_logging() runs at app.main import time; an invalid LOG_LEVEL
    # must not take the whole process down before the app object exists.
    monkeypatch.setattr(app_settings, "cloudwatch_log_group", None)
    monkeypatch.setattr(app_settings, "log_level", "NOT_A_LEVEL")
    configure_logging()
    assert logging.getLogger().level == logging.INFO


def test_configure_logging_honors_valid_log_level(monkeypatch, restore_logging):
    monkeypatch.setattr(app_settings, "cloudwatch_log_group", None)
    monkeypatch.setattr(app_settings, "log_level", "DEBUG")
    configure_logging()
    assert logging.getLogger().level == logging.DEBUG
