import json
import logging
import time
import uuid
from datetime import datetime, timezone

import watchtower
from fastapi import FastAPI, Request

from app.config import settings
from app.observability.context import request_id_var, user_id_var

_RESERVED_RECORD_ATTRS = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "taskName",
}


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
        return json.dumps(payload, default=str)


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.user_id = user_id_var.get()
        return True


def configure_logging() -> None:
    root = logging.getLogger()
    root.setLevel(settings.log_level)
    root.handlers.clear()

    context_filter = ContextFilter()
    formatter = JsonFormatter()

    stream_handler = logging.StreamHandler()
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


_http_logger = logging.getLogger("shopops.http")


def add_request_logging_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def _log_requests(request: Request, call_next):
        request_token = request_id_var.set(str(uuid.uuid4()))
        start = time.monotonic()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration_ms = (time.monotonic() - start) * 1000
            _http_logger.info(
                "http_request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "latency_ms": duration_ms,
                },
            )
            request_id_var.reset(request_token)
            user_id_var.set(None)
