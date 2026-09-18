# Structured JSON logging + CloudWatch — design

## 1. Goal

Add JSON structured logging across the FastAPI app and LangGraph agent, with
optional shipping to AWS CloudWatch, per the TDD's observability requirements
(§9/§10: structured logging & CloudWatch). This is sub-project 1 of 3 in that
scope — Langfuse tracing and the LLM eval benchmark are separate follow-on
specs and are explicitly out of scope here.

## 2. Key decisions

| Decision | Choice | Rationale |
|---|---|---|
| CloudWatch activation | Optional, env-gated | `CLOUDWATCH_LOG_GROUP` unset → stdout JSON only. No AWS dependency for local dev or CI. |
| Relationship to Postgres audit log | Additive, not a replacement | `app/audit_log.py` / `app/audit.py` stay exactly as-is; the Approvals/Audit dashboard keeps reading Postgres. Structured logs are a parallel observability stream with richer detail (latency, tokens, request correlation) that Postgres doesn't carry. |
| Request correlation | `ContextVar`-based | Avoids threading `request_id`/`user_id` through every function signature down to the LLM/tool layers. |
| CloudWatch client | `watchtower` (new dependency) | Thin `logging.Handler` over boto3 with built-in batching/retry; avoids hand-rolling `put_log_events` sequence-token handling. |

## 3. Architecture

New package `app/observability/`:

- **`context.py`** — `request_id_var: ContextVar[str | None]`, `user_id_var: ContextVar[str | None]`, both defaulting to `None`.
- **`logging_setup.py`** — exposes `configure_logging() -> None`, called once from `app/main.py` at import time:
  - JSON `logging.Formatter` subclass: emits one JSON object per line with fixed fields (`timestamp`, `level`, `logger`, `message`, `request_id`, `user_id`) plus any `extra=` fields passed to the log call.
  - `logging.Filter` subclass that reads the two contextvars and stamps them onto every `LogRecord` before formatting, so call sites never pass them explicitly.
  - Always attaches a `StreamHandler` (stdout) with the JSON formatter.
  - If `settings.cloudwatch_log_group` is set, also attaches `watchtower.CloudWatchLogHandler(log_group=..., stream_name=settings.cloudwatch_log_stream)` with the same formatter. boto3's default credential chain applies (env vars / instance role) — no new credential plumbing.
  - Sets root logger level from `settings.log_level`.

## 4. Config additions (`app/config.py`)

```python
log_level: str = os.environ.get("LOG_LEVEL", "INFO")
cloudwatch_log_group: str | None = os.environ.get("CLOUDWATCH_LOG_GROUP")
cloudwatch_log_stream: str = os.environ.get("CLOUDWATCH_LOG_STREAM", "shopops-api")
```

## 5. Instrumentation points

- **`app/main.py`** — `configure_logging()` called at module load, before `app = FastAPI(...)`. An `@app.middleware("http")` function:
  1. Generates `request_id = str(uuid.uuid4())`, sets `request_id_var`.
  2. Records start time, calls `await call_next(request)`.
  3. Logs one line (`logging.getLogger("shopops.http")`) with `extra={"method", "path", "status_code", "latency_ms"}`.
  4. Resets both contextvars at the end (via `try/finally` + `.reset(token)`) so state never leaks across requests on a reused worker.

- **`app/auth.py`** (`get_current_user`) — after successful token verification, `user_id_var.set(claims["sub"])`. Runs before the route body and before the middleware's post-`call_next` log line, so that line — and everything the request logs afterward — carries `user_id`.

- **`app/agent/llm.py`** (`call_model`, `stream_model`) — wrap the `litellm.completion` call: log one line per call via `logging.getLogger("shopops.llm")` with `extra={"model", "latency_ms", "prompt_tokens", "completion_tokens", "tools_offered": bool(tools)}`. Token counts read from `response.usage.prompt_tokens` / `.completion_tokens` (absent on stream chunks — stream path logs `tools_offered=False, streamed=True` without token counts, since LiteLLM doesn't surface usage mid-stream in this codebase's current call pattern).

- **`app/agent/nodes.py`** (`execute_tools`) — around each tool dispatch, log one line via `logging.getLogger("shopops.tools")` with `extra={"tool_name", "outcome", "duration_ms", "permission"}`, timed with `time.monotonic()`. This sits alongside the existing `log_audit(...)` calls — neither replaces the other.

## 6. Testing

- `tests/test_logging_setup.py`:
  - JSON formatter produces valid JSON with the fixed fields for a plain `logger.info("msg")` call.
  - `extra={"foo": "bar"}` fields appear in the output.
  - The context filter stamps `request_id`/`user_id` from the contextvars, and stamps `null` when unset.
  - `configure_logging()` does **not** attach a `watchtower` handler when `CLOUDWATCH_LOG_GROUP` is unset (asserted via inspecting `logging.getLogger().handlers`), so CI never needs AWS credentials.
- `tests/test_http_logging.py`: a `TestClient` request against an existing route asserts (via `caplog`) that a `shopops.http` log line is emitted with a non-null `request_id` and the expected `status_code`.

## 7. Explicitly out of scope (this spec)

- Langfuse tracing for LiteLLM/LangGraph turns — separate spec, sub-project 2.
- LLM evaluation benchmark script — separate spec, sub-project 3.
- Replacing or restructuring the Postgres `audit_events` table or the Approvals/Audit dashboard.
- Log-based alerting, CloudWatch metric filters/alarms, or dashboards — only log shipping is in scope here.
