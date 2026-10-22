"""Shared FastAPI dependencies.

``get_settings_dep`` is overridden by ``create_app`` so every route sees the Settings object the app was
built with (this is also how tests inject their own configuration). Tests override ``get_repository`` with a
stub, so route/service tests never need a database.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import engine_for
from app.repositories.scholarships import ScholarshipRepository, SqlScholarshipRepository
from app.services.eligibility_service import EligibilityService
from app.services.scholarships import ScholarshipService


def get_settings_dep() -> Settings:
    return get_settings()


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


def get_session(settings: SettingsDep) -> Iterator[Session]:
    """One database session per request, always closed. Raises DatabaseNotConfigured (-> 503) without a URL."""
    with Session(engine_for(settings), expire_on_commit=False) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]


def get_repository(session: SessionDep) -> ScholarshipRepository:
    return SqlScholarshipRepository(session)


RepositoryDep = Annotated[ScholarshipRepository, Depends(get_repository)]


def get_scholarship_service(repository: RepositoryDep) -> ScholarshipService:
    return ScholarshipService(repository)


def get_eligibility_service(repository: RepositoryDep) -> EligibilityService:
    return EligibilityService(repository)


ScholarshipServiceDep = Annotated[ScholarshipService, Depends(get_scholarship_service)]
EligibilityServiceDep = Annotated[EligibilityService, Depends(get_eligibility_service)]
