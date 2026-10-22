"""Settings parsing and validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import DEFAULT_CORS_ORIGINS, Settings
from tests.conftest import make_settings


def test_defaults_need_no_database_and_allow_local_next_js() -> None:
    s = make_settings()
    assert s.database_url is None and s.database_configured is False
    assert s.cors_origins == DEFAULT_CORS_ORIGINS == ["http://localhost:3000", "http://127.0.0.1:3000"]
    assert s.api_v1_prefix == "/api/v1"


def test_cors_origins_from_comma_separated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", " http://localhost:3000/ , https://app.example.org,http://localhost:3000 ,")
    assert Settings(_env_file=None).cors_origins == ["http://localhost:3000", "https://app.example.org"]


@pytest.mark.parametrize("bad", ["*", "localhost:3000", "ftp://x.org", "http://x.org/path", "http://x.org?q=1", "http://"])
def test_invalid_cors_origins_are_rejected(bad: str) -> None:
    with pytest.raises(ValidationError, match="Invalid CORS origin"):
        make_settings(cors_origins=bad)


def test_database_url_is_normalized_to_psycopg3_and_kept_secret() -> None:
    s = make_settings(database_url="postgresql://scholarpath_app:s3cret@localhost:5432/scholarpath")
    assert s.database_url is not None
    assert s.database_url.get_secret_value() == "postgresql+psycopg://scholarpath_app:s3cret@localhost:5432/scholarpath"
    assert "s3cret" not in repr(s) and "s3cret" not in str(s)
    assert s.database_configured is True
    assert make_settings(database_url="postgres://u:p@h/db").database_url.get_secret_value().startswith("postgresql+psycopg://")  # type: ignore[union-attr]


def test_database_url_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://u:p@localhost/db")
    assert Settings(_env_file=None).database_configured is True


@pytest.mark.parametrize("empty", ["", "   "])
def test_empty_database_url_means_not_configured(empty: str) -> None:
    assert make_settings(database_url=empty).database_url is None


@pytest.mark.parametrize("bad", ["sqlite:///x.db", "mysql://u:p@h/db", "not a url"])
def test_non_postgres_database_urls_are_rejected(bad: str) -> None:
    with pytest.raises(ValidationError, match="PostgreSQL URL"):
        make_settings(database_url=bad)


def test_validation_error_never_echoes_the_rejected_url_or_its_password(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError) as exc:
        make_settings(database_url="mysql://user:hunter2@h/db")
    assert "hunter2" not in str(exc.value) and "mysql://" not in str(exc.value)
    # same when the bad value arrives through the environment, the realistic startup failure
    monkeypatch.setenv("DATABASE_URL", "mysql://user:hunter2@h/db")
    with pytest.raises(ValidationError) as exc_env:
        Settings(_env_file=None)
    assert "hunter2" not in str(exc_env.value)
