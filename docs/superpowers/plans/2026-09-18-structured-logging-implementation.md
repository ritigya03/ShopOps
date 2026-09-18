# Structured JSON Logging + CloudWatch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add JSON structured logging across the FastAPI app and LangGraph agent, with optional AWS CloudWatch shipping, without touching the existing Postgres audit trail.

**Architecture:** A new `app/observability/` package holds two small modules — `context.py` (two `ContextVar`s for request/user correlation) and `logging_setup.py` (JSON formatter, a filter that stamps the contextvars onto every log record, `configure_logging()`, and an HTTP middleware factory). Existing modules (`main.py`, `auth.py`, `agent/llm.py`, `agent/nodes.py`) get small additive instrumentation calls; none of their existing behavior changes.

**Tech Stack:** Python stdlib `logging`, `watchtower` (new dependency — boto3-based `logging.Handler` for CloudWatch), `contextvars`, FastAPI middleware.

**Spec:** `docs/superpowers/specs/2026-09-18-structured-logging-design.md`

## Global Constraints

- CloudWatch handler attaches only when `CLOUDWATCH_LOG_GROUP` is set — no AWS credentials required to run tests or CI.
- The existing Postgres `audit_events` table and `log_audit()` calls are unchanged — this plan is purely additive.
- New dependency: `watchtower` (added to `requirements.txt`).
- All new logger calls use `logging.getLogger("shopops.<area>")` naming (`shopops.http`, `shopops.llm`, `shopops.tools`) so log volume/level can be tuned per area later.
- Follow existing repo conventions: `unittest.mock` for mocking, `caplog` for log assertions, no new test markers (these are unit tests, not `@pytest.mark.integration`).

---

### Task 1: Config additions + watchtower dependency

**Files:**
- Modify: `requirements.txt`
- Modify: `app/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `settings.log_level: str` (default `"INFO"`), `settings.cloudwatch_log_group: str | None` (default `None`), `settings.cloudwatch_log_stream: str` (default `"shopops-api"`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config.py`:

```python
def test_log_level_setting_is_a_non_empty_string():
    assert isinstance(settings.log_level, str)
    assert settings.log_level


def test_cloudwatch_log_stream_setting_is_a_non_empty_string():
    assert isinstance(settings.cloudwatch_log_stream, str)
    assert settings.cloudwatch_log_stream


def test_cloudwatch_log_group_setting_is_optional():
    assert settings.cloudwatch_log_group is None or isinstance(settings.cloudwatch_log_group, str)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: FAIL with `AttributeError: 'Settings' object has no attribute 'log_level'`

- [ ] **Step 3: Add the settings fields**

In `app/config.py`, add these three lines inside the `Settings` class, after the existing `cors_origins` line:

```python
    log_level: str = os.environ.get("LOG_LEVEL", "INFO")
    cloudwatch_log_group: str | None = os.environ.get("CLOUDWATCH_LOG_GROUP")
    cloudwatch_log_stream: str = os.environ.get("CLOUDWATCH_LOG_STREAM", "shopops-api")
```

- [ ] **Step 4: Add the dependency**

In `requirements.txt`, add a line after `langgraph>=0.2`:

```
watchtower>=3.0
```

Run: `.venv/bin/pip install -r requirements.txt`

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add requirements.txt app/config.py tests/test_config.py
git commit -m "feat: add logging/CloudWatch config settings and watchtower dependency"
```

---

### Task 2: Request/user correlation context vars

**Files:**
- Create: `app/observability/__init__.py`
- Create: `app/observability/context.py`
- Test: `tests/test_observability_context.py`

**Interfaces:**
- Produces: `request_id_var: ContextVar[str | None]`, `user_id_var: ContextVar[str | None]` — both importable from `app.observability.context`, both default to `None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_observability_context.py`:

```python
from app.observability.context import request_id_var, user_id_var


def test_request_id_var_defaults_to_none():
    assert request_id_var.get() is None


def test_user_id_var_defaults_to_none():
    assert user_id_var.get() is None


def test_request_id_var_can_be_set_and_reset():
    token = request_id_var.set("req-1")
    assert request_id_var.get() == "req-1"
    request_id_var.reset(token)
    assert request_id_var.get() is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_observability_context.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.observability'`

- [ ] **Step 3: Create the package and context vars**

Create `app/observability/__init__.py` (empty file).

Create `app/observability/context.py`:

```python
from contextvars import ContextVar

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_var: ContextVar[str | None] = ContextVar("user_id", default=None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_observability_context.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/observability/__init__.py app/observability/context.py tests/test_observability_context.py
git commit -m "feat: add request/user correlation context vars"
```

---

### Task 3: JSON formatter, context filter, configure_logging()

**Files:**
- Modify: `app/observability/logging_setup.py` (create)
- Test: `tests/test_logging_setup.py`

**Interfaces:**
- Consumes: `app.observability.context.request_id_var`, `user_id_var` (Task 2); `app.config.settings.log_level`, `.cloudwatch_log_group`, `.cloudwatch_log_stream` (Task 1).
- Produces: `JsonFormatter` (class, `logging.Formatter` subclass), `ContextFilter` (class, `logging.Filter` subclass), `configure_logging() -> None`. All importable from `app.observability.logging_setup`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_logging_setup.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_logging_setup.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.observability.logging_setup'`

- [ ] **Step 3: Implement the formatter, filter, and configure_logging()**

Create `app/observability/logging_setup.py`:

```python
import json
import logging
from datetime import datetime, timezone

import watchtower

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_logging_setup.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/observability/logging_setup.py tests/test_logging_setup.py
git commit -m "feat: add JSON log formatter, context filter, and configure_logging()"
```

---

### Task 4: Wire logging into main.py, add HTTP request-logging middleware, stamp user_id in auth

**Files:**
- Modify: `app/observability/logging_setup.py:1-` (add middleware factory)
- Modify: `app/main.py`
- Modify: `app/auth.py`
- Test: `tests/test_http_logging.py` (create)
- Test: `tests/test_auth.py` (add one test)

**Interfaces:**
- Consumes: `request_id_var`, `user_id_var` (Task 2); `configure_logging()` (Task 3).
- Produces: `add_request_logging_middleware(app: FastAPI) -> None`, importable from `app.observability.logging_setup`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_http_logging.py`:

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.observability.context import request_id_var
from app.observability.logging_setup import add_request_logging_middleware


def _build_test_app() -> FastAPI:
    test_app = FastAPI()
    add_request_logging_middleware(test_app)

    @test_app.get("/ping")
    def ping():
        return {"ok": True}

    @test_app.get("/whoami")
    def whoami():
        return {"request_id": request_id_var.get()}

    return test_app


def test_middleware_logs_request_with_status_and_latency(caplog):
    client = TestClient(_build_test_app())
    with caplog.at_level("INFO", logger="shopops.http"):
        resp = client.get("/ping")

    assert resp.status_code == 200
    record = next(r for r in caplog.records if r.name == "shopops.http")
    assert record.method == "GET"
    assert record.path == "/ping"
    assert record.status_code == 200
    assert isinstance(record.latency_ms, float)


def test_middleware_sets_request_id_during_request():
    client = TestClient(_build_test_app())
    resp = client.get("/whoami")
    assert resp.json()["request_id"] is not None
```

Append to `tests/test_auth.py`:

```python
def test_get_current_user_sets_user_id_context(monkeypatch):
    from app.observability.context import user_id_var

    fake_user = CurrentUser(sub="user-123", email="u@example.com", role="Viewer")
    monkeypatch.setattr("app.auth.decode_cognito_token", lambda token: fake_user)

    result = get_current_user(authorization="Bearer sometoken")

    assert result is fake_user
    assert user_id_var.get() == "user-123"
```

(This uses `CurrentUser`, already imported at the top of `tests/test_auth.py` — add it to the existing `from app.auth import decode_cognito_token, get_current_user` import line: `from app.auth import CurrentUser, decode_cognito_token, get_current_user`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_http_logging.py tests/test_auth.py -v`
Expected: FAIL — `test_http_logging.py` with `ImportError: cannot import name 'add_request_logging_middleware'`; the new auth test with `AssertionError` (user_id_var still `None`).

- [ ] **Step 3: Implement the middleware factory**

Append to `app/observability/logging_setup.py`:

```python
import time
import uuid

from fastapi import FastAPI, Request

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
```

Move the `import time`, `import uuid`, and `from fastapi import FastAPI, Request` lines to the top of the file with the other imports (Python requires imports before use, but style-wise keep all imports grouped at the top rather than mid-file).

- [ ] **Step 4: Wire into main.py**

Replace the full contents of `app/main.py`:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.observability.logging_setup import add_request_logging_middleware, configure_logging
from app.routes import router

configure_logging()

app = FastAPI(title="ShopOps AI Backend")
add_request_logging_middleware(app)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(router)
```

- [ ] **Step 5: Stamp user_id in auth.py**

In `app/auth.py`, add the import and one line inside `get_current_user`:

```python
from app.observability.context import user_id_var
```

(add this import after `from app.config import settings`)

```python
def get_current_user(authorization: str | None = Header(default=None)) -> CurrentUser:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing Bearer token")
    token = authorization.removeprefix("Bearer ")
    try:
        user = decode_cognito_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")
    user_id_var.set(user.sub)
    return user
```

(This replaces the existing `try: return decode_cognito_token(token) except ...` block.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_http_logging.py tests/test_auth.py -v`
Expected: PASS

- [ ] **Step 7: Run the full non-integration suite to confirm nothing broke**

Run: `.venv/bin/pytest -m "not integration" -v`
Expected: PASS (all previously-passing tests still pass)

- [ ] **Step 8: Commit**

```bash
git add app/observability/logging_setup.py app/main.py app/auth.py tests/test_http_logging.py tests/test_auth.py
git commit -m "feat: wire structured request logging into FastAPI app and auth"
```

---

### Task 5: LLM call logging

**Files:**
- Modify: `app/agent/llm.py`
- Test: `tests/test_agent_llm.py`

**Interfaces:**
- No new public interfaces — `call_model` and `stream_model` keep their existing signatures and return values; this task only adds a `logging.getLogger("shopops.llm")` call inside each.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_agent_llm.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_agent_llm.py -v`
Expected: FAIL — `StopIteration` from `next(...)` (no `shopops.llm` record emitted yet)

- [ ] **Step 3: Instrument llm.py**

Replace the full contents of `app/agent/llm.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_agent_llm.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/agent/llm.py tests/test_agent_llm.py
git commit -m "feat: log latency and token usage for LiteLLM calls"
```

---

### Task 6: Tool dispatch logging

**Files:**
- Modify: `app/agent/nodes.py`
- Test: `tests/test_agent_nodes.py` (create)

**Interfaces:**
- No new public interfaces — `execute_tools` keeps its existing signature and return value; this task adds a `logging.getLogger("shopops.tools")` call per tool dispatch.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_agent_nodes.py`:

```python
from unittest.mock import Mock, patch

from app.agent.nodes import execute_tools
from app.auth import CurrentUser


def _state(pending_tool_calls, role="OperationsManager"):
    return {
        "user": CurrentUser(sub="u1", email="u1@example.com", role=role),
        "tool_results": [],
        "evidence": [],
        "messages": [],
        "pending_tool_calls": pending_tool_calls,
        "loop_count": 0,
    }


def test_execute_tools_logs_successful_dispatch(caplog):
    fake_fn = Mock(return_value=None)
    with (
        patch.dict("app.agent.nodes.TOOL_DISPATCH", {"get_order": (fake_fn, "can_view_order")}),
        patch("app.agent.nodes.log_audit"),
        caplog.at_level("INFO", logger="shopops.tools"),
    ):
        execute_tools(_state([{"id": "call1", "name": "get_order", "args": {"order_id": "x"}}]))

    record = next(r for r in caplog.records if r.name == "shopops.tools")
    assert record.tool_name == "get_order"
    assert record.outcome == "not_found"
    assert record.permission == "can_view_order"
    assert isinstance(record.duration_ms, float)


def test_execute_tools_logs_permission_denied(caplog):
    fake_fn = Mock(return_value=None)
    with (
        patch.dict("app.agent.nodes.TOOL_DISPATCH", {"get_seller_metrics": (fake_fn, "can_view_seller_metrics")}),
        patch("app.agent.nodes.log_audit"),
        caplog.at_level("INFO", logger="shopops.tools"),
    ):
        execute_tools(_state(
            [{"id": "call1", "name": "get_seller_metrics", "args": {"seller_id": "s1"}}],
            role="Viewer",
        ))

    record = next(r for r in caplog.records if r.name == "shopops.tools")
    assert record.outcome == "denied"
    fake_fn.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_agent_nodes.py -v`
Expected: FAIL with `StopIteration` (no `shopops.tools` record emitted yet)

- [ ] **Step 3: Instrument execute_tools**

In `app/agent/nodes.py`, add `import logging` and `import time` to the top imports, add `logger = logging.getLogger("shopops.tools")` after the existing imports, and replace the `execute_tools` function body:

```python
import logging
import time
```

(add these two lines to the top of the existing import block, alongside `import hashlib`, `import json`, `import uuid`)

```python
logger = logging.getLogger("shopops.tools")
```

(add this line after the imports, before `def route_or_tools`)

```python
def execute_tools(state: AgentState) -> AgentState:
    user = state["user"]
    tool_results = list(state["tool_results"])
    tool_messages: list[dict] = []
    new_evidence = list(state["evidence"])

    for call in state["pending_tool_calls"]:
        name, args = call["name"], call["args"]
        fn, permission = TOOL_DISPATCH[name]
        start = time.monotonic()

        if permission not in PERMISSIONS.get(user.role, set()):
            outcome = "denied"
            log_audit(user, name, outcome)
            tool_results.append({"tool_name": name, "args": args, "result": None, "error": "permission_denied"})
            content = f"Permission denied: role '{user.role}' cannot use tool '{name}'."
        else:
            result = fn(**args)
            outcome = "success" if result is not None else "not_found"
            log_audit(user, name, outcome)
            if result is None:
                tool_results.append({"tool_name": name, "args": args, "result": None, "error": "not_found"})
                content = f"No data found for {name}({args})."
            elif isinstance(result, list):
                dumped = [item.model_dump(mode="json") for item in result]
                tool_results.append({"tool_name": name, "args": args, "result": dumped, "error": None})
                content = json.dumps(dumped)
                if name == "search_policy":
                    new_evidence.extend(result)
            else:
                dumped = result.model_dump(mode="json")
                tool_results.append({"tool_name": name, "args": args, "result": dumped, "error": None})
                content = json.dumps(dumped)

        duration_ms = (time.monotonic() - start) * 1000
        logger.info(
            "tool_call",
            extra={"tool_name": name, "outcome": outcome, "duration_ms": duration_ms, "permission": permission},
        )
        tool_messages.append({"role": "tool", "tool_call_id": call["id"], "name": name, "content": content})

    state["tool_results"] = tool_results
    state["evidence"] = new_evidence
    state["messages"] = [*state["messages"], *tool_messages]
    state["loop_count"] = state["loop_count"] + 1
    state["pending_tool_calls"] = []
    return state
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_agent_nodes.py -v`
Expected: PASS

- [ ] **Step 5: Run the full non-integration suite**

Run: `.venv/bin/pytest -m "not integration" -v`
Expected: PASS (all tests, including every test from Tasks 1-6)

- [ ] **Step 6: Commit**

```bash
git add app/agent/nodes.py tests/test_agent_nodes.py
git commit -m "feat: log latency and outcome for each tool dispatch"
```
