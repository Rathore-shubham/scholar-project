"""Request/response schemas for ``POST /api/v1/eligibility/check``."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.vocabulary import education_token, gender_token


class StudentProfileIn(BaseModel):
    """Everything is optional: a missing value is reported as 'missing', never guessed."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    state: str | None = Field(default=None, max_length=60, examples=["Madhya Pradesh"])
    education_level: str | None = Field(default=None, max_length=40, examples=["Undergraduate"], description="Label (Class 12, Undergraduate...) or token (12, UG)")
    percentage: float | None = Field(default=None, ge=0, le=100)
    family_income: float | None = Field(default=None, ge=0, le=1_000_000_000, description="Annual family income in INR")
    category: str | None = Field(default=None, max_length=40, examples=["OBC"])
    gender: str | None = Field(default=None, max_length=40, examples=["Female"])
    course: str | None = Field(default=None, max_length=100)

    @field_validator("education_level")
    @classmethod
    def _known_education_level(cls, value: str | None) -> str | None:
        if value and education_token(value) is None:
            raise ValueError("unrecognized education level; use Class 8-12, Diploma, Undergraduate or Postgraduate")
        return value

    @field_validator("gender")
    @classmethod
    def _known_gender(cls, value: str | None) -> str | None:
        if value:
            gender_token(value)  # raises ValueError for an unrecognized value
        return value


class EligibilityCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: StudentProfileIn
    scholarship_ids: list[str] = Field(min_length=1, max_length=50, description="1-50 stable scholarship ids")

    @field_validator("scholarship_ids")
    @classmethod
    def _unique_ids(cls, value: list[str]) -> list[str]:
        cleaned = [v.strip() for v in value]
        if any(not v or len(v) > 64 for v in cleaned):
            raise ValueError("scholarship ids must be 1-64 characters")
        return list(dict.fromkeys(cleaned))


class EvidenceOut(BaseModel):
    text: str | None = None
    url: str | None = None
    source_ref: str | None = None


class CriterionResultOut(BaseModel):
    criterion_type: str
    criterion: str
    required: str
    student_value: str | None
    status: Literal["pass", "fail", "missing", "unable_to_verify"]
    explanation: str
    is_mandatory: bool
    review_status: str
    reliable: bool = Field(description="True only for a reviewed, evidence-backed rule on a verified scholarship")
    evidence: EvidenceOut | None = None


class BasisOut(BaseModel):
    verification_status: str
    mandatory_criteria: int
    reviewed_mandatory_criteria: int
    supported_mandatory_criteria: int
    rules_reliable: bool


class EligibilityResultOut(BaseModel):
    scholarship_id: str
    scholarship_name: str
    outcome: Literal["eligible", "not_eligible", "cant_tell_yet"]
    summary: str
    indicative: Literal["all_listed_criteria_met", "some_criteria_not_met", "incomplete", "no_criteria_listed"] = Field(
        description="A hint from the raw criterion statuses. It is NOT an eligibility decision."
    )
    basis: BasisOut
    missing_information: list[str]
    limitations: list[str]
    criteria: list[CriterionResultOut]


class EligibilityCheckResponse(BaseModel):
    results: list[EligibilityResultOut]
    not_found: list[str] = Field(description="Requested ids that do not exist (or were rejected)")
