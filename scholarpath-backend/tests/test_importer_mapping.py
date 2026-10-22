"""ETL record -> database rows: coverage of all 35 columns, filter values, derived criteria, change hash."""

from __future__ import annotations

from typing import Any

from app.models import Scholarship
from app.services.importer.mapping import (
    COLUMN_DESTINATIONS,
    MAPPING_VERSION,
    criterion_specs,
    scholarship_fields,
    source_hash,
    value_rows,
)
from app.services.importer.records import ETL_COLUMNS, RawRow, validate_row
from tests.support import etl_record


def rec(**overrides: Any):
    return validate_row(RawRow(1, etl_record(**overrides)), [])


def types(specs) -> list[str]:
    return [s.criterion_type for s in specs]


def test_every_etl_column_has_a_documented_destination() -> None:
    assert set(COLUMN_DESTINATIONS) == set(ETL_COLUMNS)


def test_destination_columns_really_exist_on_the_model() -> None:
    for destination in COLUMN_DESTINATIONS.values():
        for part in destination.split(" + "):
            if part.startswith("scholarships."):
                name = part.removeprefix("scholarships.").split(" ")[0]
                assert hasattr(Scholarship, name), f"{name} is not a Scholarship column"


def test_scholarship_fields_cover_the_scalar_columns_and_keep_nulls() -> None:
    fields = scholarship_fields(rec())
    assert fields["scholarship_id"] == "SP-TEST000001" and fields["name"].startswith("Alpha")
    for nullable in ("academic_year", "minimum_percentage", "maximum_family_income", "award_amount_min", "application_deadline", "source_url", "last_verified_at", "review_notes"):
        assert fields[nullable] is None
    assert fields["verification_status"] == "pending" and fields["etl_validation_status"] == "warning"
    assert fields["etl_issue_codes"] == ["missing_academic_year"]
    assert fields["government_level"] == "CENTRAL" and fields["income_comparator"] is None
    assert all(hasattr(Scholarship, key) for key in fields)


def test_every_destination_attribute_is_produced() -> None:
    fields = scholarship_fields(rec())
    for destination in COLUMN_DESTINATIONS.values():
        for part in destination.split(" + "):
            if part.startswith("scholarships."):
                assert part.removeprefix("scholarships.").split(" ")[0] in fields


def test_filter_values_include_all_markers_and_gender_from_extra_attributes() -> None:
    rows = value_rows(rec(education_level=["9", "ug"], eligible_states=["ALL"], eligible_categories=["sc", "ST"],
                          eligible_courses=["ALL"], extra_attributes={"gender": ["female"]}))
    assert ("education_level", "9") in rows and ("education_level", "UG") in rows
    assert ("state", "ALL") in rows and ("category", "SC") in rows and ("category", "ST") in rows
    assert ("course", "ALL") in rows and ("gender", "FEMALE") in rows


def test_filter_values_are_deduplicated_case_insensitively() -> None:
    rows = value_rows(rec(eligible_states=["Bihar", "bihar", "BIHAR"]))
    assert [r for r in rows if r[0] == "state"] == [("state", "Bihar")]


def test_silence_creates_no_criterion() -> None:
    specs = criterion_specs(rec(education_level=[], eligible_states=[], eligible_categories=[], eligible_courses=[],
                                extra_attributes={}))
    assert specs == []


def test_all_criterion_types_are_derived_in_a_stable_order() -> None:
    specs = criterion_specs(rec(
        education_level=["12", "UG"], eligible_states=["Madhya Pradesh"], eligible_categories=["OBC"],
        eligible_courses=["B.SC", "M.Sc"], minimum_percentage=60, maximum_family_income=450000,
        extra_attributes={"gender": ["FEMALE"], "maximum_family_income_comparator": "<"},
        eligibility_rules=["Minimum percentage (as stated in source): MP BOARD-60"],
    ))
    assert types(specs) == ["education_level", "state", "category", "gender", "course", "minimum_percentage", "maximum_family_income", "other_rule"]
    assert [s.display_order for s in specs] == list(range(len(specs)))
    by_type = {s.criterion_type: s for s in specs}
    assert by_type["education_level"].required_value == {"values": ["12", "UG"]}
    assert by_type["minimum_percentage"].operator == "gte" and by_type["minimum_percentage"].required_value == {"value": 60}
    income = by_type["maximum_family_income"]
    assert income.operator == "lt" and income.required_value == {"value": 450000, "comparator": "<"}
    assert by_type["other_rule"].operator == "text" and "MP BOARD-60" in by_type["other_rule"].required_value["text"]


def test_income_without_comparator_is_less_or_equal() -> None:
    (spec,) = [s for s in criterion_specs(rec(maximum_family_income=250000)) if s.criterion_type == "maximum_family_income"]
    assert spec.operator == "lte" and spec.required_value == {"value": 250000, "comparator": None}


def test_open_gender_makes_no_criterion_but_restricted_gender_does_without_duplicate_text() -> None:
    open_specs = criterion_specs(rec(extra_attributes={"gender": ["MALE", "FEMALE", "OTHERS"]}))
    assert "gender" not in types(open_specs)
    restricted = criterion_specs(rec(
        extra_attributes={"gender": ["FEMALE"]}, eligibility_rules=["Gender (as stated in source): FEMALE", "Another condition"],
    ))
    assert types(restricted).count("gender") == 1
    texts = [s.required_value["text"] for s in restricted if s.criterion_type == "other_rule"]
    assert texts == ["Another condition"]  # the ETL's gender sentence is covered by the structured criterion


def test_gender_sentence_is_kept_when_there_is_no_structured_gender() -> None:
    specs = criterion_specs(rec(extra_attributes={}, eligibility_rules=["Gender (as stated in source): FEMALE"]))
    assert types(specs).count("other_rule") == 1


def test_derived_criteria_are_unreviewed_mandatory_and_evidence_free() -> None:
    for spec in criterion_specs(rec(minimum_percentage=50, eligibility_rules=["x"])):
        assert spec.review_status == "unreviewed" and spec.is_mandatory is True
        assert spec.evidence_text is None and spec.evidence_url is None and spec.has_evidence is False
        assert spec.source_ref == "fixture.xlsx / Sheet1 / row 2"  # ETL provenance only, not a citation


def test_derivation_is_deterministic() -> None:
    a, b = rec(minimum_percentage=55), rec(minimum_percentage=55)
    assert criterion_specs(a) == criterion_specs(b) and value_rows(a) == value_rows(b) and source_hash(a) == source_hash(b)


def test_source_hash_changes_with_content_and_is_versioned() -> None:
    base = source_hash(rec())
    assert len(base) == 64
    assert source_hash(rec(award_amount_text="changed")) != base
    assert source_hash(rec(verification_status="needs_review")) != base
    assert MAPPING_VERSION >= 1
