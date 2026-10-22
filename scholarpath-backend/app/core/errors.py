"""Structured API errors: every handled failure has a stable machine-readable ``code`` plus a ``detail`` message."""

from __future__ import annotations


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail


class NotFoundError(ApiError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(404, code, detail)


# Database problems the frontend can show distinct messages for (never includes URLs, hosts or credentials).
DATABASE_NOT_CONFIGURED = ("database_not_configured", "The database is not configured on the server (DATABASE_URL is not set).")
DATABASE_UNAVAILABLE = ("database_unavailable", "The database is unavailable right now. Please try again shortly.")
DATABASE_NOT_MIGRATED = (
    "database_not_migrated",
    "The database is reachable but its tables do not exist yet. An administrator needs to run the migrations (alembic upgrade head).",
)
