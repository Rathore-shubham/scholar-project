"""Versioned API router (``/api/v1``)."""

from fastapi import APIRouter

from app.api.routes import eligibility, scholarships

api_router = APIRouter()
api_router.include_router(scholarships.router)
api_router.include_router(eligibility.router)
