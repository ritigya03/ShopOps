import logging
from unittest.mock import Mock, patch

import pytest

from app.agent.llm import call_model, stream_model


def test_call_model_passes_model_and_messages():
    fake_response = Mock()
    messages = [{"role": "user", "content": "hi"}]
    with patch("app.agent.llm.litellm.completion", return_value=fake_response) as mock_completion:
        result = call_model(messages)

    mock_completion.assert_called_once()
    _, kwargs = mock_completion.call_args
    assert kwargs["messages"] == messages
    assert kwargs["model"]
    assert result is fake_response


def test_call_model_includes_tools_when_provided():
    tools = [{"type": "function", "function": {"name": "get_order"}}]
    with patch("app.agent.llm.litellm.completion", return_value=Mock()) as mock_completion:
        call_model([{"role": "user", "content": "hi"}], tools=tools)

    _, kwargs = mock_completion.call_args
    assert kwargs["tools"] == tools
    assert kwargs["tool_choice"] == "auto"


def test_call_model_omits_tools_when_not_provided():
    with patch("app.agent.llm.litellm.completion", return_value=Mock()) as mock_completion:
        call_model([{"role": "user", "content": "hi"}])

    _, kwargs = mock_completion.call_args
    assert "tools" not in kwargs
    assert "tool_choice" not in kwargs


def test_call_model_logs_llm_call(caplog):
    fake_response = Mock()
    fake_response.usage = Mock(prompt_tokens=10, completion_tokens=5)
    with (
        patch("app.agent.llm.litellm.completion", return_value=fake_response),
        caplog.at_level("INFO", logger="shopops.llm"),
    ):
        call_model([{"role": "user", "content": "hi"}])

    record = next(r for r in caplog.records if r.name == "shopops.llm")
    assert record.prompt_tokens == 10
    assert record.completion_tokens == 5
    assert record.tools_offered is False
    assert isinstance(record.latency_ms, float)


class FakeChunk:
    def __init__(self, content):
        self.choices = [Mock(delta=Mock(content=content))]


def test_stream_model_logs_llm_call(caplog):
    with (
        patch("app.agent.llm.litellm.completion", return_value=[FakeChunk("hi"), FakeChunk(None)]),
        caplog.at_level("INFO", logger="shopops.llm"),
    ):
        list(stream_model([{"role": "user", "content": "hi"}]))

    record = next(r for r in caplog.records if r.name == "shopops.llm")
    assert record.streamed is True
    assert record.tools_offered is False
    assert record.outcome == "success"
    assert record.levelno == logging.INFO


def test_call_model_logs_success_outcome(caplog):
    with (
        patch("app.agent.llm.litellm.completion", return_value=Mock()),
        caplog.at_level("INFO", logger="shopops.llm"),
    ):
        call_model([{"role": "user", "content": "hi"}])

    record = next(r for r in caplog.records if r.name == "shopops.llm")
    assert record.outcome == "success"


def test_call_model_logs_error_with_traceback_and_reraises(caplog):
    boom = RuntimeError("upstream exploded")
    with (
        patch("app.agent.llm.litellm.completion", side_effect=boom),
        caplog.at_level("INFO", logger="shopops.llm"),
        pytest.raises(RuntimeError, match="upstream exploded"),
    ):
        call_model([{"role": "user", "content": "hi"}], tools=[{"type": "function"}])

    record = next(r for r in caplog.records if r.name == "shopops.llm")
    assert record.levelno == logging.ERROR
    assert record.outcome == "error"
    assert record.prompt_tokens is None
    assert record.completion_tokens is None
    assert record.tools_offered is True
    assert isinstance(record.latency_ms, float)
    # exc_info=True means the real traceback rides along on the record.
    assert record.exc_info is not None
    assert record.exc_info[1] is boom


def test_stream_model_logs_error_when_stream_raises_midway(caplog):
    def exploding_stream():
        yield FakeChunk("partial")
        raise RuntimeError("stream died")

    with (
        patch("app.agent.llm.litellm.completion", return_value=exploding_stream()),
        caplog.at_level("INFO", logger="shopops.llm"),
        pytest.raises(RuntimeError, match="stream died"),
    ):
        list(stream_model([{"role": "user", "content": "hi"}]))

    record = next(r for r in caplog.records if r.name == "shopops.llm")
    assert record.levelno == logging.ERROR
    assert record.outcome == "error"
    assert record.streamed is True
    assert isinstance(record.exc_info[1], RuntimeError)


def test_stream_model_logs_error_when_completion_call_itself_raises(caplog):
    with (
        patch("app.agent.llm.litellm.completion", side_effect=RuntimeError("no stream")),
        caplog.at_level("INFO", logger="shopops.llm"),
        pytest.raises(RuntimeError, match="no stream"),
    ):
        list(stream_model([{"role": "user", "content": "hi"}]))

    record = next(r for r in caplog.records if r.name == "shopops.llm")
    assert record.levelno == logging.ERROR
    assert record.outcome == "error"


def test_stream_model_logs_when_generator_is_abandoned(caplog):
    # Closing a partially-consumed generator throws GeneratorExit at the
    # `yield`. `except BaseException` catches it so the call still produces a
    # log line, and re-raises it (swallowing GeneratorExit is illegal).
    with patch(
        "app.agent.llm.litellm.completion",
        return_value=[FakeChunk("a"), FakeChunk("b"), FakeChunk("c")],
    ), caplog.at_level("INFO", logger="shopops.llm"):
        gen = stream_model([{"role": "user", "content": "hi"}])
        assert next(gen) == "a"
        gen.close()  # raises RuntimeError if GeneratorExit were swallowed

    record = next(r for r in caplog.records if r.name == "shopops.llm")
    assert record.levelno == logging.ERROR
    assert record.outcome == "error"
    assert record.streamed is True
