"""Database problems surface as honest, structured 503s - never as dummy data, never leaking secrets."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import InterfaceError, OperationalError, ProgrammingError

from app.api.deps import get_repository
from app.main import create_app
from tests.conftest import make_settings

DATA_ENDPOINTS = [
    ("GET", "/api/v1/scholarships", None),
    ("GET", "/api/v1/scholarships/SP-X", None),
    ("GET", "/api/v1/meta/filters", None),
    ("POST", "/api/v1/eligibility/check", {"profile": {}, "scholarship_ids": ["SP-X"]}),
]


def call(client: TestClient, method: str, path: str, body):
    return client.request(method, path, json=body)


@pytest.mark.parametrize("method, path, body", DATA_ENDPOINTS)
def test_without_a_configured_database_every_data_endpoint_says_so(method: str, path: str, body) -> None:
    client = TestClient(create_app(make_settings()))
    response = call(client, method, path, body)
    assert response.status_code == 503
    assert response.json()["code"] == "database_not_configured" and "DATABASE_URL" in response.json()["detail"]
    assert "items" not in response.json() and "results" not in response.json()  # no placeholder data


def test_health_still_works_without_a_database() -> None:
    client = TestClient(create_app(make_settings()))
    assert client.get("/health").status_code == 200
    db = client.get("/health/db")
    assert db.status_code == 503 and db.json()["status"] == "not_configured"


class RaisingRepository:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def search(self, query):  # noqa: ANN001
        raise self.error

    get = get_many = filter_options = search


def client_raising(error: Exception) -> TestClient:
    app = create_app(make_settings())
    app.dependency_overrides[get_repository] = lambda: RaisingRepository(error)
    return TestClient(app, raise_server_exceptions=False)


class FakeDriverError(Exception):
    def __init__(self, message: str, sqlstate: str | None = None) -> None:
        super().__init__(message)
        self.sqlstate = sqlstate


@pytest.mark.parametrize("error_type", [OperationalError, InterfaceError])
def test_connection_failures_become_database_unavailable_without_leaking_details(error_type) -> None:
    secret = FakeDriverError("connection to server at 'secret-host' failed: password authentication failed for user 'leaky_user' password=hunter2")
    response = client_raising(error_type("SELECT 1", {}, secret)).get("/api/v1/scholarships")
    assert response.status_code == 503 and response.json()["code"] == "database_unavailable"
    for leaked in ("secret-host", "leaky_user", "hunter2", "SELECT 1"):
        assert leaked not in response.text


@pytest.mark.parametrize("sqlstate", ["42P01", "42703"])
def test_missing_tables_or_columns_become_database_not_migrated(sqlstate: str) -> None:
    error = ProgrammingError("SELECT * FROM scholarships", {}, FakeDriverError('relation "scholarships" does not exist', sqlstate))
    response = client_raising(error).get("/api/v1/scholarships")
    assert response.status_code == 503 and response.json()["code"] == "database_not_migrated"
    assert "alembic upgrade head" in response.json()["detail"] and "scholarships" not in response.json()["detail"].replace("alembic", "")


def test_other_programming_errors_are_not_disguised_as_a_database_outage() -> None:
    error = ProgrammingError("SELECT oops", {}, FakeDriverError("syntax error", "42601"))
    assert client_raising(error).get("/api/v1/scholarships").status_code == 500


def test_eligibility_endpoint_uses_the_same_error_mapping() -> None:
    client = client_raising(OperationalError("x", {}, FakeDriverError("down")))
    response = client.post("/api/v1/eligibility/check", json={"profile": {}, "scholarship_ids": ["SP-X"]})
    assert response.status_code == 503 and response.json()["code"] == "database_unavailable"


def test_unreachable_database_through_the_real_stack_is_unavailable() -> None:
    # real engine + real session dependency, pointed at a closed port: must be a clean 503, no traceback, no secrets
    settings = make_settings(database_url="postgresql+psycopg://leaky_user:hunter2@127.0.0.1:1/leaky_db", db_connect_timeout_seconds=1)
    response = TestClient(create_app(settings), raise_server_exceptions=False).get("/api/v1/scholarships")
    assert response.status_code == 503 and response.json()["code"] == "database_unavailable"
    for leaked in ("hunter2", "leaky_user", "leaky_db", "127.0.0.1"):
        assert leaked not in response.text
