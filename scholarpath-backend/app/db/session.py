"""Database engine construction.

Importing this module never opens a connection. An engine is built on first use, and only
when ``DATABASE_URL`` is configured, so the API can run (and ``/health`` can answer) with no
database at all.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy import Engine, create_engine

from app.core.config import Settings


class DatabaseNotConfigured(RuntimeError):
    """DATABASE_URL is not set."""


NOT_CONFIGURED_MESSAGE = "DATABASE_URL is not set. Copy .env.example to .env and fill it in."


@lru_cache
def _cached_engine(url: str, connect_timeout: int) -> Engine:
    # create_engine is lazy: it does not connect until a connection is requested.
    return create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": connect_timeout})


def engine_for(settings: Settings) -> Engine:
    """Engine for these settings (shared per URL). Raises DatabaseNotConfigured if no URL."""
    if settings.database_url is None:
        raise DatabaseNotConfigured(NOT_CONFIGURED_MESSAGE)
    return _cached_engine(settings.database_url.get_secret_value(), settings.db_connect_timeout_seconds)
