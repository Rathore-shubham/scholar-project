"""SQL repository semantics, executed against seeded synthetic records on in-memory SQLite."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.domain import ScholarshipQuery
from app.repositories.scholarships import SqlScholarshipRepository
from app.services.importer.runner import plan_import, run_import
from tests.support import etl_record, memory_engine, write_json


def seed() -> list[dict[str, Any]]:
    common_extra = {"government_level": "CENTRAL", "gender": ["MALE", "FEMALE", "OTHERS"]}
    return [
        etl_record(scholarship_id="SP-A", scholarship_name="Alpha National Merit (test fixture)", provider_name="Ministry of Education",
                   education_level=["12"], eligible_states=["ALL"], eligible_categories=["SC", "ST"], award_amount_min=50000, award_amount_max=50000,
                   award_amount_text="Rs 50,000 per annum", extra_attributes=common_extra),
        etl_record(scholarship_id="SP-B", scholarship_name="Beta Madhya Pradesh Post-Matric (test fixture)", provider_name="Tribal Affairs Department",
                   scheme_type="state", education_level=["UG", "PG"], eligible_states=["Madhya Pradesh"], eligible_categories=["OBC"],
                   minimum_percentage=60, maximum_family_income=800000, extra_attributes={"government_level": "MP", "gender": ["MALE", "FEMALE", "OTHERS"]}),
        etl_record(scholarship_id="SP-C", scholarship_name="Gamma Girls Scholarship (test fixture)", provider_name="Women Welfare Trust",
                   education_level=["UG"], eligible_states=["Maharashtra"], eligible_categories=["ALL"], award_amount_min=20000, award_amount_max=80000,
                   application_deadline="2026-12-01", verification_status="verified", last_verified_at="2026-10-01",
                   extra_attributes={"government_level": "CENTRAL", "gender": ["FEMALE"]}),
        etl_record(scholarship_id="SP-D", scholarship_name="Delta Rejected Scheme (test fixture)", verification_status="rejected"),
        etl_record(scholarship_id="SP-E", scholarship_name="Epsilon Silent Scheme (test fixture)", education_level=[], eligible_states=[],
                   eligible_categories=[], eligible_courses=[], extra_attributes={}, application_deadline="2026-11-01"),
        etl_record(scholarship_id="SP-F", scholarship_name="Zeta 100% Support_Plan (test fixture)", provider_name="Zeta Foundation",
                   education_level=["9", "10"], eligible_states=["ALL"], eligible_categories=["GENERAL"], award_amount_min=1000, award_amount_max=9000,
                   extra_attributes={"government_level": "CENTRAL", "gender": ["MALE", "FEMALE", "OTHERS"]}),
    ]


@pytest.fixture()
def repo(tmp_path: Path):
    engine = memory_engine()
    run_import(engine, plan_import(write_json(tmp_path / "seed.json", seed())))
    with Session(engine) as session:
        yield SqlScholarshipRepository(session)


def ids(result) -> list[str]:
    return [v.scholarship_id for v in result.items]


def q(**kw: Any) -> ScholarshipQuery:
    return ScholarshipQuery(page_size=50, **kw)


def test_rejected_records_are_never_listed_or_fetched(repo) -> None:
    result = repo.search(q())
    assert "SP-D" not in ids(result) and result.total == 5
    assert repo.get("SP-D") is None
    assert [v.scholarship_id for v in repo.get_many(["SP-D", "SP-A"])] == ["SP-A"]


def test_unverified_records_are_included_by_default_and_labelled(repo) -> None:
    result = repo.search(q())
    statuses = {v.scholarship_id: v.verification_status for v in result.items}
    assert statuses["SP-A"] == "pending" and statuses["SP-C"] == "verified"


def test_verified_only(repo) -> None:
    result = repo.search(q(verified_only=True))
    assert ids(result) == ["SP-C"] and result.total == 1


def test_default_sort_is_by_name(repo) -> None:
    assert ids(repo.search(q())) == ["SP-A", "SP-B", "SP-E", "SP-C", "SP-F"]  # alpha, beta, epsilon, gamma, zeta


def test_state_filter_matches_the_state_or_all_but_not_silent_records(repo) -> None:
    assert ids(repo.search(q(state="Madhya Pradesh"))) == ["SP-A", "SP-B", "SP-F"]
    assert ids(repo.search(q(state="madhya pradesh"))) == ["SP-A", "SP-B", "SP-F"]  # case-insensitive
    assert "SP-E" not in ids(repo.search(q(state="Bihar"))) and ids(repo.search(q(state="Bihar"))) == ["SP-A", "SP-F"]


def test_education_level_filter(repo) -> None:
    assert ids(repo.search(q(education_level="UG"))) == ["SP-B", "SP-C"]
    assert ids(repo.search(q(education_level="12"))) == ["SP-A"]
    assert ids(repo.search(q(education_level="10"))) == ["SP-F"]
    assert repo.search(q(education_level="DIPLOMA")).total == 0


def test_category_filter_matches_all_marker(repo) -> None:
    assert ids(repo.search(q(category="OBC"))) == ["SP-B", "SP-C"]  # SP-C lists ALL
    assert ids(repo.search(q(category="obc"))) == ["SP-B", "SP-C"]
    assert ids(repo.search(q(category="SC"))) == ["SP-A", "SP-C"]


def test_gender_filter(repo) -> None:
    assert ids(repo.search(q(gender="FEMALE"))) == ["SP-A", "SP-B", "SP-C", "SP-F"]
    assert ids(repo.search(q(gender="MALE"))) == ["SP-A", "SP-B", "SP-F"]  # the FEMALE-only scheme is excluded


def test_scheme_type_filter(repo) -> None:
    assert ids(repo.search(q(scheme_type="state"))) == ["SP-B"]


def test_numeric_student_filters_keep_unknown_requirements(repo) -> None:
    assert ids(repo.search(q(student_percentage=50))) == ["SP-A", "SP-E", "SP-C", "SP-F"]  # SP-B needs 60; nulls kept
    assert "SP-B" in ids(repo.search(q(student_percentage=60)))
    assert ids(repo.search(q(student_income=900000))) == ["SP-A", "SP-E", "SP-C", "SP-F"]  # SP-B caps income at 8,00,000
    assert ids(repo.search(q(student_income=800000))) == ["SP-A", "SP-B", "SP-E", "SP-C", "SP-F"]  # boundary is inclusive
    assert repo.search(q(student_income=900001, scheme_type="state")).total == 0


def test_min_award_excludes_unknown_amounts(repo) -> None:
    assert ids(repo.search(q(min_award=50000))) == ["SP-A", "SP-C"]
    assert ids(repo.search(q(min_award=1))) == ["SP-A", "SP-C", "SP-F"]  # null amounts are not treated as 0 or as huge


def test_text_search_across_fields_and_terms(repo) -> None:
    assert ids(repo.search(q(text="alpha"))) == ["SP-A"]
    assert ids(repo.search(q(text="tribal"))) == ["SP-B"]  # provider
    assert ids(repo.search(q(text="per annum"))) == ["SP-A"]  # benefits text, AND of both terms
    assert ids(repo.search(q(text="maharashtra"))) == ["SP-C"]  # filter values
    assert ids(repo.search(q(text="madhya merit"))) == []  # AND semantics across terms
    assert ids(repo.search(q(text="MERIT NATIONAL"))) == ["SP-A"]  # case and order insensitive
    assert repo.search(q(text="nonexistent-term")).total == 0


def test_like_wildcards_in_search_text_are_literal(repo) -> None:
    assert ids(repo.search(q(text="100%"))) == ["SP-F"]
    assert ids(repo.search(q(text="support_plan"))) == ["SP-F"]
    assert repo.search(q(text="%")).total == 1  # only the record that actually contains '%'
    assert repo.search(q(text="_")).total == 1


def test_sorting_puts_unknown_values_last(repo) -> None:
    assert ids(repo.search(q(sort="amount_desc")))[:3] == ["SP-C", "SP-A", "SP-F"]
    assert ids(repo.search(q(sort="amount_desc")))[3:] == ["SP-B", "SP-E"]
    assert ids(repo.search(q(sort="deadline")))[:2] == ["SP-E", "SP-C"]
    assert ids(repo.search(q(sort="recently_verified")))[0] == "SP-C"


def test_pagination_and_totals(repo) -> None:
    page1 = repo.search(ScholarshipQuery(page=1, page_size=2))
    page3 = repo.search(ScholarshipQuery(page=3, page_size=2))
    beyond = repo.search(ScholarshipQuery(page=9, page_size=2))
    assert (page1.total, page3.total, beyond.total) == (5, 5, 5)
    assert ids(page1) == ["SP-A", "SP-B"] and ids(page3) == ["SP-F"] and beyond.items == []


def test_ids_filter_and_get_many_preserve_requested_order(repo) -> None:
    assert ids(repo.search(q(ids=("SP-F", "SP-A")))) == ["SP-A", "SP-F"]  # list order is the normal sort
    assert [v.scholarship_id for v in repo.get_many(["SP-F", "SP-A", "SP-NOPE"])] == ["SP-F", "SP-A"]
    assert repo.get_many([]) == []


def test_detail_view_carries_values_criteria_and_provenance(repo) -> None:
    view = repo.get("SP-B")
    assert view is not None and view.name.startswith("Beta") and view.scheme_type == "state"
    assert view.eligible_states == ("Madhya Pradesh",) and set(view.education_levels) == {"UG", "PG"}
    assert view.minimum_percentage == 60 and view.maximum_family_income == 800000 and view.official_url == "https://scholarships.gov.in"
    assert {c.criterion_type for c in view.criteria} >= {"education_level", "state", "category", "minimum_percentage", "maximum_family_income"}
    assert all(c.review_status == "unreviewed" and not c.has_evidence for c in view.criteria)
    assert (view.source_file, view.source_row, view.verification_status) == ("fixture.xlsx", 2, "pending")
    assert view.government_level == "MP" and view.extra_attributes["government_level"] == "MP"
    assert repo.get("SP-NOPE") is None


def test_filter_options_exclude_all_marker_and_rejected(repo) -> None:
    options = repo.filter_options()
    assert options.states == ["Madhya Pradesh", "Maharashtra"]
    assert options.education_levels == ["10", "12", "9", "PG", "UG"]
    assert options.categories == ["GENERAL", "OBC", "SC", "ST"] and options.genders == ["FEMALE", "MALE", "OTHERS"]
    assert options.scheme_types == ["central", "state"]
    assert (options.total_scholarships, options.verified_scholarships) == (5, 1)
