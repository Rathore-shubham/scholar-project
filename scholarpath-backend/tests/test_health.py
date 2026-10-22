"""Health endpoints, docs, CORS - all without a real database."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app import __version__
from app.main import create_app
from app.services.health import check_database
from tests.conftest import make_settings


def test_health_ok_without_any_database(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok", "service": "ScholarPath API", "version": __version__, "environment": "development",
    }


def test_health_never_touches_the_database_even_if_it_is_unreachable() -> None:
    # Port 1 refuses connections; /health must still answer instantly and succeed.
    settings = make_settings(database_url="postgresql+psycopg://u:p@127.0.0.1:1/db")
    started = time.monotonic()
    response = TestClient(create_app(settings)).get("/health")
    assert response.status_code == 200 and response.json()["status"] == "ok"
    assert time.monotonic() - started < 2


def test_db_health_reports_not_configured(client: TestClient) -> None:
    response = client.get("/health/db")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_configured" and "DATABASE_URL" in body["detail"]


def test_db_health_reports_unreachable_database_without_leaking_credentials() -> None:
    settings = make_settings(
        database_url="postgresql+psycopg://leaky_user:leaky_password@127.0.0.1:1/leaky_db", db_connect_timeout_seconds=1
    )
    response = TestClient(create_app(settings)).get("/health/db")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable" and "OperationalError" in body["detail"]
    text = response.text
    assert "leaky_password" not in text and "leaky_user" not in text and "leaky_db" not in text and "127.0.0.1" not in text


def test_check_database_ok_with_a_working_engine() -> None:
    # The service accepts any SQLAlchemy engine; an in-memory SQLite engine proves the success path.
    assert check_database(create_engine("sqlite://")).model_dump() == {"status": "ok", "detail": None}


def test_swagger_ui_and_openapi_are_enabled(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200
    assert "swagger" in client.get("/docs").text.lower()
    spec = client.get("/openapi.json").json()
    assert spec["info"]["title"] == "ScholarPath API" and spec["info"]["version"] == __version__
    assert {"/health", "/health/db"} <= set(spec["paths"])


def test_cors_allows_configured_origin_only() -> None:
    client = TestClient(create_app(make_settings(cors_origins="http://localhost:3000")))
    allowed = client.options(
        "/health", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "GET"}
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
    denied = client.options(
        "/health", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"}
    )
    assert "access-control-allow-origin" not in denied.headers
    simple = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert simple.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_cors_is_configurable_from_settings() -> None:
    client = TestClient(create_app(make_settings(cors_origins="https://scholarpath.example.org")))
    response = client.get("/health", headers={"Origin": "https://scholarpath.example.org"})
    assert response.headers["access-control-allow-origin"] == "https://scholarpath.example.org"
    assert "access-control-allow-origin" not in client.get("/health", headers={"Origin": "http://localhost:3000"}).headers


def test_unknown_route_is_a_json_404(client: TestClient) -> None:
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404 and response.json() == {"detail": "Not Found"}
