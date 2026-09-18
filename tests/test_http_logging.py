import logging

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.observability.context import request_id_var, user_id_var
from app.observability.logging_setup import (
    ContextFilter,
    add_request_logging_middleware,
)


def _build_test_app() -> FastAPI:
    test_app = FastAPI()
    add_request_logging_middleware(test_app)

    @test_app.get("/ping")
    def ping():
        return {"ok": True}

    @test_app.get("/whoami")
    def whoami():
        return {"request_id": request_id_var.get()}

    @test_app.get("/boom")
    def boom():
        raise RuntimeError("kaboom")

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
    assert record.levelno == logging.INFO


def test_middleware_sets_request_id_during_request():
    client = TestClient(_build_test_app())
    resp = client.get("/whoami")
    assert resp.json()["request_id"] is not None


def test_middleware_logs_server_error_at_error_level(caplog):
    client = TestClient(_build_test_app(), raise_server_exceptions=False)
    with caplog.at_level("INFO", logger="shopops.http"):
        resp = client.get("/boom")

    assert resp.status_code == 500
    record = next(r for r in caplog.records if r.name == "shopops.http")
    assert record.status_code == 500
    assert record.levelno == logging.ERROR


def test_middleware_passes_non_http_scopes_through_untouched(caplog):
    # Starlette runs the middleware stack for *every* scope type, lifespan
    # included. A lifespan pass must produce no http_request line (and must not
    # blow up on the absent scope["method"]).
    app = _build_test_app()
    with (
        caplog.at_level("INFO", logger="shopops.http"),
        TestClient(app) as client,  # entering/exiting runs the lifespan
    ):
        assert not [r for r in caplog.records if r.name == "shopops.http"]
        assert client.get("/ping").status_code == 200

    http_records = [r for r in caplog.records if r.name == "shopops.http"]
    assert len(http_records) == 1  # the GET only — nothing from lifespan
    assert http_records[0].path == "/ping"


@pytest.fixture
def context_stamped_http_logger():
    """Attach a ContextFilter to shopops.http so emitted records carry user_id.

    In production the filter lives on the handlers configure_logging() installs;
    caplog's own handler has none, so add it at logger level for these tests —
    logger-level filters run before handlers, stamping the record exactly the
    way the JSON handler would see it.
    """
    filt = ContextFilter()
    logger = logging.getLogger("shopops.http")
    logger.addFilter(filt)
    yield
    logger.removeFilter(filt)


def test_user_id_set_by_async_dependency_reaches_http_log_record(
    caplog, context_stamped_http_logger
):
    """End-to-end pin for the user_id correlation mechanism.

    This is the test a direct unit call to get_current_user() can never be: it
    proves an *async* dependency's `user_id_var.set()` is still visible to the
    request-logging middleware when the request finishes. It fails if
    get_current_user reverts to a sync `def` (run_in_threadpool copies the
    context) or if the middleware goes back to BaseHTTPMiddleware (which runs
    the app in a `start_soon` child task, so child->parent context never flows).
    """
    test_app = FastAPI()
    add_request_logging_middleware(test_app)

    async def fake_current_user() -> str:
        # Mirrors what the real app.auth.get_current_user now does.
        user_id_var.set("user-xyz")
        return "user-xyz"

    @test_app.get("/secure")
    def secure(current_user: str = Depends(fake_current_user)):
        return {"user": current_user}

    client = TestClient(test_app)
    with caplog.at_level("INFO", logger="shopops.http"):
        resp = client.get("/secure")

    assert resp.status_code == 200
    record = next(r for r in caplog.records if r.name == "shopops.http")
    assert record.path == "/secure"
    assert record.user_id == "user-xyz"
    assert record.request_id is not None
    assert user_id_var.get() is None  # middleware cleared it after logging
