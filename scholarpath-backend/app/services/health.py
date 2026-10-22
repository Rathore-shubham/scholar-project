"""Health-check logic (kept out of the route so it can be tested on its own)."""

from __future__ import annotations

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.db.session import DatabaseNotConfigured, engine_for
from app.schemas.health import DatabaseHealthResponse


def check_database(engine: Engine) -> DatabaseHealthResponse:
    """Run ``SELECT 1``. Reports only the failure *type*, never the URL, host or credentials."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        return DatabaseHealthResponse(
            status="unavailable",
            detail=f"Could not run a query ({type(exc).__name__}). Check that PostgreSQL is running and DATABASE_URL is correct.",
        )
    return DatabaseHealthResponse(status="ok")


def database_health(settings: Settings) -> DatabaseHealthResponse:
    try:
        engine = engine_for(settings)
    except DatabaseNotConfigured:
        return DatabaseHealthResponse(
            status="not_configured",
            detail="DATABASE_URL is not set. Copy .env.example to .env and fill it in.",
        )
    return check_database(engine)
