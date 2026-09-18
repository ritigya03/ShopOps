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
