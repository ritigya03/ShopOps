import json
import logging

from app.config import settings as app_settings
from app.observability.context import request_id_var, user_id_var
from app.observability.logging_setup import ContextFilter, JsonFormatter, configure_logging


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


def test_configure_logging_skips_cloudwatch_when_group_unset(monkeypatch):
    monkeypatch.setattr(app_settings, "cloudwatch_log_group", None)
    configure_logging()
    handler_types = [type(h).__name__ for h in logging.getLogger().handlers]
    assert "CloudWatchLogHandler" not in handler_types
