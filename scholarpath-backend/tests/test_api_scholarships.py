"""Scholarship endpoints: parameter handling, response shape, validation and errors (stubbed repository, no database)."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_repository
from app.main import create_app
from tests.conftest import make_settings
from tests.support import StubRepository, criterion, view


def client_with(repo) -> TestClient:
    app = create_app(make_settings())
    app.dependency_overrides[get_repository] = lambda: repo
    return TestClient(app)


@pytest.fixture()
def repo() -> StubRepository:
    return StubRepository([
        view("SP-A", education_levels=("UG", "12", "9"), eligible_states=("Madhya Pradesh",), official_url="https://scholarships.gov.in",
             award_amount_text="Rs 5,000 per month", criteria=[criterion("state", "in", {"values": ["Madhya Pradesh"]})]),
        view("SP-B", status="verified", last_verified_at=date(2026, 10, 1), name="Verified fixture"),
    ])


def test_list_response_shape_labels_and_notices(repo: StubRepository) -> None:
    body = client_with(repo).get("/api/v1/scholarships").json()
    assert body["total"] == 2 and body["page"] == 1 and body["page_size"] == 12 and body["pages"] == 1
    first, second = body["items"]
    assert first["scholarship_id"] == "SP-A" and first["verification_status"] == "pending" and first["is_verified"] is False
    assert first["education_levels"] == ["9", "12", "UG"]  # sorted school -> college
    assert first["education_level_labels"] == ["Class 9", "Class 12", "Undergraduate"]
    assert first["data_notice"].startswith("Unverified") and first["application_deadline"] is None  # unavailable, not invented
    assert first["award_amount_text"] == "Rs 5,000 per month" and first["award_amount_max"] is None
    assert second["is_verified"] is True and second["data_notice"] is None and second["last_verified_at"] == "2026-10-01"


def test_pending_status_is_never_presented_as_verified(repo: StubRepository) -> None:
    for item in client_with(repo).get("/api/v1/scholarships").json()["items"]:
        assert item["is_verified"] == (item["verification_status"] == "verified")
        assert (item["data_notice"] is None) == item["is_verified"]


def test_query_parameters_are_translated_to_etl_tokens(repo: StubRepository) -> None:
    response = client_with(repo).get("/api/v1/scholarships", params={
        "q": "  merit  award ", "state": "Madhya Pradesh", "education_level": "Undergraduate", "category": "obc", "gender": "Female",
        "scheme_type": "state", "student_percentage": 72.5, "student_income": 300000, "min_award": 1000, "verified_only": "true",
        "sort": "amount_desc", "page": 2, "page_size": 5, "ids": "SP-A, SP-B,SP-A",
    })
    assert response.status_code == 200
    q = repo.last_query
    assert (q.text, q.state, q.education_level, q.category, q.gender, q.scheme_type) == ("merit  award", "Madhya Pradesh", "UG", "OBC", "FEMALE", "state")
    assert (q.student_percentage, q.student_income, q.min_award, q.verified_only) == (72.5, 300000, 1000, True)
    assert (q.sort, q.page, q.page_size, q.ids) == ("amount_desc", 2, 5, ("SP-A", "SP-B"))


def test_defaults_and_blank_filters_mean_no_filter(repo: StubRepository) -> None:
    client_with(repo).get("/api/v1/scholarships", params={"q": "  ", "state": "Other", "education_level": " ", "category": "Prefer not to say", "gender": "Prefer not to say"})
    q = repo.last_query
    assert (q.text, q.state, q.education_level, q.category, q.gender) == (None, None, None, None, None)
    assert (q.verified_only, q.sort, q.page, q.page_size) == (False, "name", 1, 12)


def test_education_level_accepts_labels_and_tokens(repo: StubRepository) -> None:
    c = client_with(repo)
    for raw, token in (("Class 12", "12"), ("12", "12"), ("ug", "UG"), ("Postgraduate", "PG"), ("Diploma", "DIPLOMA")):
        c.get("/api/v1/scholarships", params={"education_level": raw})
        assert repo.last_query.education_level == token


def test_pagination_metadata(repo: StubRepository) -> None:
    repo.total = 34
    body = client_with(repo).get("/api/v1/scholarships", params={"page_size": 12, "page": 3}).json()
    assert (body["total"], body["pages"], body["page"]) == (34, 3, 3)
    repo.total = 0
    repo.views = []
    empty = client_with(repo).get("/api/v1/scholarships").json()
    assert empty == {"items": [], "total": 0, "page": 1, "page_size": 12, "pages": 0}


@pytest.mark.parametrize(
    "params",
    [{"page": 0}, {"page_size": 0}, {"page_size": 51}, {"sort": "random"}, {"scheme_type": "galactic"}, {"student_percentage": 101},
     {"student_percentage": -1}, {"student_income": -5}, {"min_award": -1}, {"q": "x" * 201}, {"page": "abc"}, {"verified_only": "maybe"}],
)
def test_invalid_query_parameters_return_422(repo: StubRepository, params: dict) -> None:
    assert client_with(repo).get("/api/v1/scholarships", params=params).status_code == 422


def test_domain_validation_errors_have_a_stable_code(repo: StubRepository) -> None:
    c = client_with(repo)
    bad_level = c.get("/api/v1/scholarships", params={"education_level": "Class 13"})
    assert bad_level.status_code == 422 and bad_level.json()["code"] == "invalid_education_level"
    bad_gender = c.get("/api/v1/scholarships", params={"gender": "robot"})
    assert bad_gender.status_code == 422 and bad_gender.json()["code"] == "invalid_gender"
    too_many = c.get("/api/v1/scholarships", params={"ids": ",".join(f"SP-{i}" for i in range(51))})
    assert too_many.status_code == 422 and too_many.json()["code"] == "invalid_ids"


def test_detail_includes_criteria_provenance_and_unavailable_fields_as_null(repo: StubRepository) -> None:
    body = client_with(repo).get("/api/v1/scholarships/SP-A").json()
    assert body["scholarship_id"] == "SP-A" and body["verification_status"] == "pending" and body["data_notice"]
    assert body["application_deadline"] is None and body["application_procedure"] is None and body["source_url"] is None
    assert body["required_documents"] == [] and body["minimum_percentage"] is None and body["maximum_family_income"] is None
    assert body["provenance"]["source_file"] is None  # the stub record has none; nothing is invented
    (crit,) = body["criteria"]
    assert crit["criterion_type"] == "state" and crit["review_status"] == "unreviewed" and crit["evidence_text"] is None
    assert crit["required_value"] == {"values": ["Madhya Pradesh"]}


def test_unknown_scholarship_is_a_structured_404(repo: StubRepository) -> None:
    response = client_with(repo).get("/api/v1/scholarships/SP-NOPE")
    assert response.status_code == 404
    assert response.json() == {"detail": "No scholarship with id 'SP-NOPE'.", "code": "scholarship_not_found"}
    assert client_with(repo).get("/api/v1/scholarships/" + "x" * 65).status_code == 422


def test_filter_options_endpoint(repo: StubRepository) -> None:
    body = client_with(repo).get("/api/v1/meta/filters").json()
    assert body["states"] == ["Madhya Pradesh"] and body["education_levels"] == [{"value": "12", "label": "Class 12"}, {"value": "UG", "label": "Undergraduate"}]
    assert body["total_scholarships"] == 2 and body["verified_scholarships"] == 0


def test_openapi_documents_every_required_endpoint(repo: StubRepository) -> None:
    paths = client_with(repo).get("/openapi.json").json()["paths"]
    assert {"/health", "/health/db", "/api/v1/scholarships", "/api/v1/scholarships/{scholarship_id}", "/api/v1/eligibility/check", "/api/v1/meta/filters"} <= set(paths)
