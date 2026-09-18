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
        "num_retries": 3,
    }
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"

    start = time.monotonic()
    try:
        response = litellm.completion(**kwargs)
    except Exception:
        duration_ms = (time.monotonic() - start) * 1000
        # G201 suppressed: the explicit .error(..., exc_info=True) form is kept
        # over .exception() so the success and failure log calls read as the
        # same shape, with only the level and outcome differing.
        logger.error(  # noqa: G201
            "llm_call",
            extra={
                "model": settings.agent_model,
                "latency_ms": duration_ms,
                "prompt_tokens": None,
                "completion_tokens": None,
                "tools_offered": bool(tools),
                "outcome": "error",
            },
            exc_info=True,
        )
        raise
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
            "outcome": "success",
        },
    )
    return response


def stream_model(messages: list[dict]) -> Iterator[str]:
    start = time.monotonic()
    outcome = "success"
    try:
        response = litellm.completion(
            model=settings.agent_model,
            messages=messages,
            api_key=settings.gemini_api_key,
            stream=True,
            num_retries=3,
        )
        for chunk in response:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    except BaseException:
        # BaseException, not Exception: an abandoned generator is closed with
        # GeneratorExit thrown at the `yield`, and that exit path deserves a
        # log line too. GeneratorExit is re-raised, never swallowed.
        outcome = "error"
        raise
    finally:
        # Logged once here rather than duplicated across the three exit paths.
        duration_ms = (time.monotonic() - start) * 1000
        extra = {
            "model": settings.agent_model,
            "latency_ms": duration_ms,
            "prompt_tokens": None,
            "completion_tokens": None,
            "tools_offered": False,
            "streamed": True,
            "outcome": outcome,
        }
        if outcome == "error":
            # LOG014 suppressed: this `finally` *is* on an exception path
            # (outcome is only "error" when the except block re-raised), so
            # sys.exc_info() is still populated; ruff can't see that statically.
            logger.error("llm_call", extra=extra, exc_info=True)  # noqa: LOG014
        else:
            logger.info("llm_call", extra=extra)
