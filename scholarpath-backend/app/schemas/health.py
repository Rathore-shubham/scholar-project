"""Response schemas for the health endpoints."""

from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = Field(examples=["ScholarPath API"])
    version: str = Field(examples=["0.1.0"])
    environment: str = Field(examples=["development"])


class DatabaseHealthResponse(BaseModel):
    status: Literal["ok", "unavailable", "not_configured"]
    detail: str | None = Field(
        default=None,
        description="Short, non-sensitive explanation. Never contains the connection URL or credentials.",
    )
