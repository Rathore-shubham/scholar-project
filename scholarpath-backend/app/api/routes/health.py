"""Health endpoints.

``GET /health``    process liveness - never touches the database.
``GET /health/db`` database reachability - 200 when a query works, 503 otherwise.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app import __version__
from app.api.deps import SettingsDep
from app.schemas.health import DatabaseHealthResponse, HealthResponse
from app.services.health import database_health

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Service liveness (no database needed)")
def health(settings: SettingsDep) -> HealthResponse:
    return HealthResponse(service=settings.app_name, version=__version__, environment=settings.environment)


@router.get(
    "/health/db",
    response_model=DatabaseHealthResponse,
    responses={503: {"model": DatabaseHealthResponse, "description": "Database not configured or unreachable"}},
    summary="Database connectivity",
)
def health_db(settings: SettingsDep) -> JSONResponse:
    result = database_health(settings)
    return JSONResponse(status_code=200 if result.status == "ok" else 503, content=result.model_dump())
