"""Test fixtures.

Safety rules for this suite:
* No test reads a developer's real ``.env`` or environment: every test runs in an empty temp directory with the
  relevant variables removed, and Settings objects are built with ``_env_file=None``.
* No test connects to PostgreSQL or to the network. SQL is exercised on in-memory SQLite (a test harness only;
  the real schema is verified separately through the offline Alembic SQL, see test_migration.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import create_app

ENV_VARS = ("DATABASE_URL", "CORS_ORIGINS", "ENVIRONMENT", "APP_NAME", "API_V1_PREFIX", "DB_CONNECT_TIMEOUT_SECONDS")


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)  # a stray Settings() cannot find the developer's backend/.env
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def make_settings(**overrides: object) -> Settings:
    return Settings(_env_file=None, **overrides)  # type: ignore[arg-type]


@pytest.fixture()
def settings() -> Settings:
    return make_settings()


@pytest.fixture()
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))
