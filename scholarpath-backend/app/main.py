"""FastAPI application factory.

Run locally::

    uvicorn app.main:app --reload --port 8001
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError, ProgrammingError

from app import __version__
from app.api.deps import get_settings_dep
from app.api.router import api_router
from app.api.routes import health
from app.core.config import Settings, get_settings
from app.core.errors import (
    DATABASE_NOT_CONFIGURED,
    DATABASE_NOT_MIGRATED,
    DATABASE_UNAVAILABLE,
    ApiError,
)
from app.db.session import DatabaseNotConfigured

# PostgreSQL SQLSTATEs meaning "the schema is not what the code expects" (undefined table / column).
SCHEMA_MISSING_SQLSTATES = {"42P01", "42703"}


def _error(status: int, code: str, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": detail, "code": code})


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "Scholarship discovery and rule-based eligibility for Indian students. "
            "Records are imported from the ScholarPath ETL and keep their real verification status; "
            "pending records are unverified and are labelled as such."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    app.dependency_overrides[get_settings_dep] = lambda: settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
        allow_credentials=False,
    )

    @app.exception_handler(ApiError)
    async def _api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return _error(exc.status_code, exc.code, exc.detail)

    @app.exception_handler(DatabaseNotConfigured)
    async def _database_not_configured(_request: Request, _exc: DatabaseNotConfigured) -> JSONResponse:
        return _error(503, *DATABASE_NOT_CONFIGURED)

    @app.exception_handler(OperationalError)
    @app.exception_handler(InterfaceError)
    async def _database_unavailable(_request: Request, _exc: Exception) -> JSONResponse:
        return _error(503, *DATABASE_UNAVAILABLE)

    @app.exception_handler(ProgrammingError)
    async def _programming_error(_request: Request, exc: ProgrammingError) -> JSONResponse:
        if getattr(exc.orig, "sqlstate", None) in SCHEMA_MISSING_SQLSTATES:
            return _error(503, *DATABASE_NOT_MIGRATED)
        raise exc  # a genuine bug: let it surface as a 500 instead of hiding it

    app.include_router(health.router)
    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
