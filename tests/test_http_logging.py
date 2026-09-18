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
