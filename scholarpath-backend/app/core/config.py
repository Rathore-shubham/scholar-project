"""Application settings, read from environment variables (and an optional local .env file).

Nothing here assumes database credentials: ``DATABASE_URL`` is optional, so the app (and
``GET /health``) starts without it. Secrets are held as ``SecretStr`` so they never show up
in ``repr()`` or logs.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_CORS_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]


class Settings(BaseSettings):
    # hide_input_in_errors: a rejected DATABASE_URL must never be echoed (with its password) in the
    # validation error that crashes startup or lands in logs.
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True
    )

    app_name: str = "ScholarPath API"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"

    # postgresql+psycopg://user:password@host:5432/dbname  (see .env.example)
    database_url: SecretStr | None = None
    db_connect_timeout_seconds: int = 3

    # Comma-separated list of browser origins allowed to call this API (the Next.js dev server).
    cors_origins: Annotated[list[str], NoDecode] = list(DEFAULT_CORS_ORIGINS)

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: object) -> object:
        if value is None:
            return None
        text = value.get_secret_value() if isinstance(value, SecretStr) else str(value)
        text = text.strip()
        if not text:
            return None  # DATABASE_URL= (set but empty) means "not configured"
        for plain in ("postgresql://", "postgres://"):
            if text.startswith(plain):
                text = "postgresql+psycopg://" + text[len(plain):]
        if not text.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must be a PostgreSQL URL: postgresql+psycopg://user:password@host:5432/dbname")
        return text

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> object:
        items = value.split(",") if isinstance(value, str) else value
        if not isinstance(items, (list, tuple)):
            return value
        origins: list[str] = []
        for raw in items:
            origin = str(raw).strip().rstrip("/")
            if not origin:
                continue
            parts = urlsplit(origin)
            if origin == "*" or parts.scheme not in {"http", "https"} or not parts.netloc or parts.path or parts.query:
                raise ValueError(
                    f"Invalid CORS origin {origin!r}: list explicit origins such as http://localhost:3000 "
                    "(scheme + host + optional port, no path, no wildcard)."
                )
            if origin not in origins:
                origins.append(origin)
        return origins

    @property
    def database_configured(self) -> bool:
        return self.database_url is not None


@lru_cache
def get_settings() -> Settings:
    return Settings()
