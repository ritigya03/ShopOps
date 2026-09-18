import logging
import time
from collections.abc import Iterator

import litellm

from app.config import settings

logger = logging.getLogger("shopops.llm")


def call_model(messages: list[dict], tools: list[dict] | None = None):
    kwargs: dict = {
        "model": settings.agent_model,
        "messages": messages,
        "api_key": settings.gemini_api_key,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    start = time.monotonic()
    response = litellm.completion(**kwargs)
    duration_ms = (time.monotonic() - start) * 1000

    usage = getattr(response, "usage", None)
    logger.info(
        "llm_call",
        extra={
            "model": settings.agent_model,
            "latency_ms": duration_ms,
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "tools_offered": bool(tools),
        },
    )
    return response


def stream_model(messages: list[dict]) -> Iterator[str]:
    start = time.monotonic()
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
    duration_ms = (time.monotonic() - start) * 1000
    logger.info(
        "llm_call",
        extra={
            "model": settings.agent_model,
            "latency_ms": duration_ms,
            "prompt_tokens": None,
            "completion_tokens": None,
            "tools_offered": False,
            "streamed": True,
        },
    )
