from unittest.mock import Mock, patch

from app.agent.llm import call_model


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
    with patch("app.agent.llm.litellm.completion", return_value=fake_response):
        with caplog.at_level("INFO", logger="shopops.llm"):
            call_model([{"role": "user", "content": "hi"}])

    record = next(r for r in caplog.records if r.name == "shopops.llm")
    assert record.prompt_tokens == 10
    assert record.completion_tokens == 5
    assert record.tools_offered is False
    assert isinstance(record.latency_ms, float)


def test_stream_model_logs_llm_call(caplog):
    from app.agent.llm import stream_model

    class FakeChunk:
        def __init__(self, content):
            self.choices = [Mock(delta=Mock(content=content))]

    with patch("app.agent.llm.litellm.completion", return_value=[FakeChunk("hi"), FakeChunk(None)]):
        with caplog.at_level("INFO", logger="shopops.llm"):
            list(stream_model([{"role": "user", "content": "hi"}]))

    record = next(r for r in caplog.records if r.name == "shopops.llm")
    assert record.streamed is True
    assert record.tools_offered is False
