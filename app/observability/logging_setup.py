import json
import logging
import sys
import time
import uuid
from datetime import datetime, timezone

import watchtower
from fastapi import FastAPI

from app.config import settings
from app.observability.context import request_id_var, user_id_var

_RESERVED_RECORD_ATTRS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "taskName",
}

# uvicorn installs its own handlers on these and sets propagate=False, which
# would keep their records out of the root JSON pipeline entirely (mixed
# plain-text/JSON output plus duplicate access logging).
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.access", "uvicorn.error")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
            "user_id": getattr(record, "user_id", None),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED_RECORD_ATTRS and key not in payload:
                payload[key] = value
        # exc_info/stack_info are excluded from the generic loop above because
        # they aren't JSON-serializable; render them to strings explicitly so
        # tracebacks aren't silently dropped.
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack_info"] = self.formatStack(record.stack_info)
        return json.dumps(payload, default=str)


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.user_id = user_id_var.get()
        return True


def configure_logging() -> None:
    root = logging.getLogger()
    try:
        root.setLevel(settings.log_level)
    except (ValueError, TypeError):
        # configure_logging() runs at app.main import time, before the app
        # object exists — a typo'd LOG_LEVEL must not take the process down.
        root.setLevel("INFO")
    root.handlers.clear()

    context_filter = ContextFilter()
    formatter = JsonFormatter()

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(context_filter)
    root.addHandler(stream_handler)

    if settings.cloudwatch_log_group:
        cloudwatch_handler = watchtower.CloudWatchLogHandler(
            log_group=settings.cloudwatch_log_group,
            stream_name=settings.cloudwatch_log_stream,
        )
        cloudwatch_handler.setFormatter(formatter)
        cloudwatch_handler.addFilter(context_filter)
        root.addHandler(cloudwatch_handler)

    for name in _UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True


_http_logger = logging.getLogger("shopops.http")


class RequestLoggingMiddleware:
    """Pure ASGI request logger.

    Deliberately *not* BaseHTTPMiddleware: BaseHTTPMiddleware runs the
    downstream app in a task spawned with `start_soon`, which gets a *copy*
    of the current context. ContextVars set downstream (e.g. `user_id_var`
    inside a FastAPI dependency) would therefore be invisible here, so every
    log line would carry `user_id: null`. Running the app in this same task
    keeps downstream `.set()` calls visible.

    It also means `await self.app(...)` only returns once the entire response
    body has been sent, so streaming responses get a truthful latency number.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            # Starlette runs the middleware stack for lifespan and websocket
            # scopes too; those have no method/status and must pass through.
            await self.app(scope, receive, send)
            return

        request_token = request_id_var.set(str(uuid.uuid4()))
        start = time.monotonic()
        status_code = 500

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = (time.monotonic() - start) * 1000
            level = logging.ERROR if status_code >= 500 else logging.INFO
            _http_logger.log(
                level,
                "http_request",
                extra={
                    "method": scope.get("method"),
                    "path": scope.get("path"),
                    "status_code": status_code,
                    "latency_ms": duration_ms,
                },
            )
            request_id_var.reset(request_token)
            user_id_var.set(None)


def add_request_logging_middleware(app: FastAPI) -> None:
    app.add_middleware(RequestLoggingMiddleware)
