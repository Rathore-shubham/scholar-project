"""POST /api/v1/eligibility/check (stubbed repository, no database)."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_repository
from app.main import create_app
from tests.conftest import make_settings
from tests.support import StubRepository, criterion, view


def make_client(repo: StubRepository) -> TestClient:
    app = create_app(make_settings())
    app.dependency_overrides[get_repository] = lambda: repo
    return TestClient(app)


@pytest.fixture()
def repo() -> StubRepository:
    reliable = lambda t, op, v, o: criterion(t, op, v, reviewed=True, evidence="Official notification", order=o)  # noqa: E731
    return StubRepository([
        view("SP-PENDING", name="Pending fixture", criteria=[
            criterion("state", "in", {"values": ["Madhya Pradesh"]}, order=0),
            criterion("minimum_percentage", "gte", {"value": 60}, order=1),
        ]),
        view("SP-VERIFIED", name="Verified fixture", status="verified", last_verified_at=date(2026, 10, 1), criteria=[
            reliable("state", "in", {"values": ["Madhya Pradesh"]}, 0), reliable("category", "in", {"values": ["OBC"]}, 1),
        ]),
    ])


PROFILE = {"state": "Madhya Pradesh", "education_level": "Undergraduate", "percentage": 72, "family_income": 300000, "category": "OBC", "gender": "Female"}


def post(client: TestClient, ids: list[str], profile: dict | None = None):
    return client.post("/api/v1/eligibility/check", json={"profile": PROFILE if profile is None else profile, "scholarship_ids": ids})


def test_response_has_every_field_the_ui_needs(repo: StubRepository) -> None:
    body = post(make_client(repo), ["SP-PENDING"]).json()
    assert body["not_found"] == [] and len(body["results"]) == 1
    result = body["results"][0]
    assert set(result) == {"scholarship_id", "scholarship_name", "outcome", "summary", "indicative", "basis", "missing_information", "limitations", "criteria"}
    crit = result["criteria"][0]
    assert set(crit) == {"criterion_type", "criterion", "required", "student_value", "status", "explanation", "is_mandatory", "review_status", "reliable", "evidence"}
    assert (crit["criterion"], crit["required"], crit["student_value"], crit["status"]) == ("State", "Resident of: Madhya Pradesh", "Madhya Pradesh", "pass")
    assert crit["evidence"]["source_ref"] == "fixture.xlsx / Sheet1 / row 2" and crit["evidence"]["text"] is None


def test_unverified_scholarship_is_cant_tell_yet_even_when_everything_matches(repo: StubRepository) -> None:
    result = post(make_client(repo), ["SP-PENDING"]).json()["results"][0]
    assert result["outcome"] == "cant_tell_yet" and result["indicative"] == "all_listed_criteria_met"
    assert result["basis"]["verification_status"] == "pending" and result["basis"]["rules_reliable"] is False
    assert [c["status"] for c in result["criteria"]] == ["pass", "pass"] and all(c["reliable"] is False for c in result["criteria"])
    assert "not been verified" in result["limitations"][0]


def test_verified_scholarship_with_reviewed_evidence_can_be_eligible_or_not(repo: StubRepository) -> None:
    c = make_client(repo)
    eligible = post(c, ["SP-VERIFIED"]).json()["results"][0]
    assert eligible["outcome"] == "eligible" and eligible["basis"]["rules_reliable"] is True
    assert all(x["reliable"] and x["evidence"]["text"] == "Official notification" for x in eligible["criteria"])
    not_eligible = post(c, ["SP-VERIFIED"], {**PROFILE, "category": "General"}).json()["results"][0]
    assert not_eligible["outcome"] == "not_eligible" and "Category" in not_eligible["summary"]


def test_missing_profile_fields_are_reported_not_guessed(repo: StubRepository) -> None:
    result = post(make_client(repo), ["SP-VERIFIED"], {}).json()["results"][0]
    assert result["outcome"] == "cant_tell_yet" and result["missing_information"] == ["category", "state"]
    assert [c["status"] for c in result["criteria"]] == ["missing", "missing"]
    assert all(c["student_value"] is None for c in result["criteria"])


def test_prefer_not_to_say_and_other_state_count_as_not_provided(repo: StubRepository) -> None:
    profile = {"state": "Other", "category": "Prefer not to say", "gender": "Prefer not to say"}
    result = post(make_client(repo), ["SP-VERIFIED"], profile).json()["results"][0]
    assert result["missing_information"] == ["category", "state"]


def test_batch_keeps_request_order_and_reports_unknown_ids(repo: StubRepository) -> None:
    body = post(make_client(repo), ["SP-VERIFIED", "SP-NOPE", "SP-PENDING", "SP-VERIFIED"]).json()
    assert [r["scholarship_id"] for r in body["results"]] == ["SP-VERIFIED", "SP-PENDING"]  # duplicates collapsed
    assert body["not_found"] == ["SP-NOPE"]


@pytest.mark.parametrize(
    "payload",
    [
        {"profile": PROFILE, "scholarship_ids": []},
        {"profile": PROFILE, "scholarship_ids": [f"SP-{i}" for i in range(51)]},
        {"profile": PROFILE, "scholarship_ids": [""]},
        {"profile": PROFILE, "scholarship_ids": ["x" * 65]},
        {"scholarship_ids": ["SP-A"]},
        {"profile": {**PROFILE, "percentage": 101}, "scholarship_ids": ["SP-A"]},
        {"profile": {**PROFILE, "percentage": -1}, "scholarship_ids": ["SP-A"]},
        {"profile": {**PROFILE, "family_income": -1}, "scholarship_ids": ["SP-A"]},
        {"profile": {**PROFILE, "education_level": "Class 13"}, "scholarship_ids": ["SP-A"]},
        {"profile": {**PROFILE, "gender": "robot"}, "scholarship_ids": ["SP-A"]},
        {"profile": {**PROFILE, "state": "x" * 61}, "scholarship_ids": ["SP-A"]},
        {"profile": {**PROFILE, "aadhaar": "123456789012"}, "scholarship_ids": ["SP-A"]},  # sensitive/unknown fields are refused
        {"profile": PROFILE, "scholarship_ids": ["SP-A"], "extra": 1},
        {"profile": "not an object", "scholarship_ids": ["SP-A"]},
    ],
)
def test_invalid_requests_are_rejected_with_422(repo: StubRepository, payload: dict) -> None:
    assert make_client(repo).post("/api/v1/eligibility/check", json=payload).status_code == 422


def test_malformed_body_and_wrong_method(repo: StubRepository) -> None:
    c = make_client(repo)
    assert c.post("/api/v1/eligibility/check", content="not json", headers={"Content-Type": "application/json"}).status_code == 422
    assert c.get("/api/v1/eligibility/check").status_code == 405


def test_results_are_deterministic(repo: StubRepository) -> None:
    c = make_client(repo)
    assert post(c, ["SP-PENDING", "SP-VERIFIED"]).json() == post(c, ["SP-PENDING", "SP-VERIFIED"]).json()


def test_labels_and_tokens_are_both_accepted_for_education_level() -> None:
    repo = StubRepository([view("SP-E", criteria=[criterion("education_level", "in", {"values": ["UG"]})])])
    c = make_client(repo)
    for level in ("Undergraduate", "UG", "ug"):
        result = post(c, ["SP-E"], {"education_level": level}).json()["results"][0]
        assert result["criteria"][0]["status"] == "pass" and result["criteria"][0]["student_value"] == "Undergraduate"
