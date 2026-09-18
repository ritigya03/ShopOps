from collections.abc import Iterator

import litellm

from app.config import settings


def call_model(messages: list[dict], tools: list[dict] | None = None):
    kwargs: dict = {
        "model": settings.agent_model,
        "messages": messages,
        "api_key": settings.gemini_api_key,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    return litellm.completion(**kwargs)


def stream_model(messages: list[dict]) -> Iterator[str]:
    response = litellm.completion(
        model=settings.agent_model,
        messages=messages,
        api_key=settings.gemini_api_key,
        stream=True,
    )
    for chunk in response:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta
