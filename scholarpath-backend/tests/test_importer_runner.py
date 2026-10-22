"""Importer planning and the transactional upsert (executed on in-memory SQLite)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ImportRun, Scholarship, ScholarshipCriterion, ScholarshipValue
from app.services.importer import runner
from app.services.importer.runner import plan_import, report_for_plan, run_import
from tests.support import etl_record, memory_engine, write_csv, write_json


def records() -> list[dict[str, Any]]:
    return [
        etl_record(scholarship_id="SP-RUN000001", scholarship_name="Alpha (test fixture)", source_row=2,
                   minimum_percentage=60, maximum_family_income=450000,
                   extra_attributes={"government_level": "CENTRAL", "gender": ["MALE", "FEMALE", "OTHERS"], "maximum_family_income_comparator": "<"}),
        etl_record(scholarship_id="SP-RUN000002", scholarship_name="Beta (test fixture)", source_row=3, scheme_type="state",
                   eligible_states=["Madhya Pradesh"], eligible_categories=["OBC"], award_amount_text="Rs 5,000 per month",
                   eligibility_rules=["Minimum percentage (as stated in source): MP BOARD-60"]),
        etl_record(scholarship_id="SP-RUN000003", scholarship_name="Gamma (test fixture)", source_row=4, education_level=["UG"],
                   eligible_categories=[], extra_attributes={"government_level": "CENTRAL", "gender": ["FEMALE"]},
                   eligibility_rules=["Gender (as stated in source): FEMALE"]),
    ]


@pytest.fixture()
def engine():
    return memory_engine()


def count(engine, model) -> int:
    with Session(engine) as s:
        return s.scalar(select(func.count()).select_from(model)) or 0


def do_import(engine, path: Path, **kw: Any):
    return run_import(engine, plan_import(path, **kw))


def test_plan_is_pure_and_reports_counts_without_a_database(tmp_path: Path) -> None:
    path = write_json(tmp_path / "a.json", records())
    plan = plan_import(path)
    report = report_for_plan(plan, dry_run=True)
    assert (report.records_read, report.valid, report.failed, report.skipped) == (3, 3, 0, 0)
    assert report.dry_run is True and report.inserted == report.updated == 0
    assert report.status_counts == {"pending": 3}


def test_first_import_inserts_everything(engine, tmp_path: Path) -> None:
    report = do_import(engine, write_json(tmp_path / "a.json", records()))
    assert (report.inserted, report.updated, report.unchanged, report.skipped, report.failed) == (3, 0, 0, 0, 0)
    assert count(engine, Scholarship) == 3 and count(engine, ImportRun) == 1
    with Session(engine) as s:
        run = s.scalars(select(ImportRun)).one()
        assert (run.status, run.inserted, run.records_read) == ("succeeded", 3, 3) and run.finished_at is not None
        assert run.source_sha256 == plan_import(tmp_path / "a.json").input.sha256
        assert {sch.last_import_run_id for sch in s.scalars(select(Scholarship))} == {run.id}


def test_reimporting_the_same_file_creates_no_duplicates_and_changes_nothing(engine, tmp_path: Path) -> None:
    path = write_json(tmp_path / "a.json", records())
    do_import(engine, path)
    child_counts = (count(engine, ScholarshipValue), count(engine, ScholarshipCriterion))
    with Session(engine) as s:
        before = [(r.scholarship_id, r.source_hash, r.updated_at, r.last_import_run_id) for r in s.scalars(select(Scholarship).order_by(Scholarship.id))]
    second = do_import(engine, path)
    third = do_import(engine, path)
    assert (second.inserted, second.updated, second.unchanged) == (0, 0, 3) == (third.inserted, third.updated, third.unchanged)
    assert count(engine, Scholarship) == 3
    assert (count(engine, ScholarshipValue), count(engine, ScholarshipCriterion)) == child_counts  # no duplicated child rows
    with Session(engine) as s:
        after = [(r.scholarship_id, r.source_hash, r.updated_at, r.last_import_run_id) for r in s.scalars(select(Scholarship).order_by(Scholarship.id))]
    assert after == before  # rows untouched
    assert count(engine, ImportRun) == 3  # every run is audited


def test_csv_and_json_import_to_identical_rows(tmp_path: Path) -> None:
    def dump(engine) -> list[Any]:
        with Session(engine) as s:
            return [
                (r.scholarship_id, r.name, r.source_hash, sorted((v.kind, v.value) for v in r.values),
                 [(c.criterion_type, c.operator) for c in r.criteria])
                for r in s.scalars(select(Scholarship).order_by(Scholarship.scholarship_id))
            ]

    e1, e2 = memory_engine(), memory_engine()
    do_import(e1, write_json(tmp_path / "a.json", records()))
    do_import(e2, write_csv(tmp_path / "a.csv", records()))
    assert dump(e1) == dump(e2)


def test_changed_record_is_updated_and_others_stay_unchanged(engine, tmp_path: Path) -> None:
    path = tmp_path / "a.json"
    do_import(engine, write_json(path, records()))
    changed = records()
    changed[1]["award_amount_text"] = "Rs 6,000 per month"
    changed[1]["eligible_states"] = ["Madhya Pradesh", "Bihar"]
    report = do_import(engine, write_json(path, changed))
    assert (report.inserted, report.updated, report.unchanged) == (0, 1, 2)
    with Session(engine) as s:
        row = s.scalars(select(Scholarship).where(Scholarship.scholarship_id == "SP-RUN000002")).one()
        assert row.award_amount_text == "Rs 6,000 per month"
        assert sorted(v.value for v in row.values if v.kind == "state") == ["Bihar", "Madhya Pradesh"]
        state_criterion = next(c for c in row.criteria if c.criterion_type == "state")
        assert state_criterion.required_value == {"values": ["Madhya Pradesh", "Bihar"]}
    assert count(engine, Scholarship) == 3


def test_nulls_urls_and_status_are_preserved(engine, tmp_path: Path) -> None:
    do_import(engine, write_json(tmp_path / "a.json", records()))
    with Session(engine) as s:
        row = s.scalars(select(Scholarship).where(Scholarship.scholarship_id == "SP-RUN000002")).one()
        assert row.minimum_percentage is None and row.maximum_family_income is None  # never 0
        assert row.award_amount_min is None and row.application_deadline is None and row.source_url is None
        assert row.official_url == "https://scholarships.gov.in"
        assert row.verification_status == "pending" and row.last_verified_at is None
        assert row.required_documents == [] and row.etl_issue_codes == ["missing_academic_year"]
        assert row.extra_attributes["government_level"] == "CENTRAL"
        assert (row.source_file, row.source_sheet, row.source_row) == ("fixture.xlsx", "Sheet1", 3)


def test_importer_never_upgrades_verification(engine, tmp_path: Path) -> None:
    recs = [
        etl_record(scholarship_id="SP-V1", verification_status="verified", last_verified_at="2026-10-01", review_notes="verified by tester"),
        etl_record(scholarship_id="SP-V2", verification_status="verified"),  # claims verified without a date -> invalid
        etl_record(scholarship_id="SP-V3", verification_status="pending"),
    ]
    report = do_import(engine, write_json(tmp_path / "a.json", recs))
    assert (report.inserted, report.failed) == (2, 1)
    assert "verified" in report.failed_details[0].reason and report.failed_details[0].scholarship_id == "SP-V2"
    with Session(engine) as s:
        status = {r.scholarship_id: r.verification_status for r in s.scalars(select(Scholarship))}
    assert status == {"SP-V1": "verified", "SP-V3": "pending"}  # values come only from the input, never inferred


def test_invalid_records_fail_valid_ones_still_import(engine, tmp_path: Path) -> None:
    recs = records()
    recs[1]["minimum_percentage"] = 150
    recs.append(etl_record(scholarship_id="SP-BAD", official_url="not-a-url"))
    report = do_import(engine, write_json(tmp_path / "a.json", recs))
    assert (report.records_read, report.valid, report.inserted, report.failed) == (4, 2, 2, 2)
    assert {i.scholarship_id for i in report.failed_details} == {"SP-RUN000002", "SP-BAD"}
    assert count(engine, Scholarship) == 2


def test_duplicate_ids_in_the_file_are_all_failed_not_guessed(engine, tmp_path: Path) -> None:
    recs = [etl_record(scholarship_id="SP-DUP", scholarship_name="One"), etl_record(scholarship_id="SP-DUP", scholarship_name="Two"), *records()[:1]]
    report = do_import(engine, write_json(tmp_path / "a.json", recs))
    assert (report.inserted, report.failed) == (1, 2)
    assert all("appears 2 times" in i.reason for i in report.failed_details)
    assert count(engine, Scholarship) == 1


def test_records_the_etl_flagged_with_errors_are_skipped_unless_asked(engine, tmp_path: Path) -> None:
    recs = [*records()[:1], etl_record(scholarship_id="SP-ERR", validation_status="error", validation_issue_codes=["invalid_url"])]
    path = write_json(tmp_path / "a.json", recs)
    report = do_import(engine, path)
    assert (report.inserted, report.skipped, report.failed) == (1, 1, 0)
    assert "invalid_url" in report.skipped_details[0].reason and "--include-errors" in report.skipped_details[0].reason
    forced = do_import(engine, path, include_errors=True)
    assert (forced.inserted, forced.unchanged, forced.skipped) == (1, 1, 0)


def test_unmapped_input_columns_are_kept_in_extra_attributes(engine, tmp_path: Path) -> None:
    path = write_csv(tmp_path / "a.csv", [etl_record(hostel="Yes")], extra_columns=("hostel",))
    report = do_import(engine, path)
    assert report.unmapped_columns == ["hostel"]
    with Session(engine) as s:
        assert s.scalars(select(Scholarship)).one().extra_attributes["import_unmapped_columns"] == {"hostel": "Yes"}


def test_failure_rolls_back_everything_and_is_audited(engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = write_json(tmp_path / "a.json", records())
    original = runner._replace_criteria
    calls = {"n": 0}

    def explode(obj, specs):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("simulated failure on the third record")
        return original(obj, specs)

    monkeypatch.setattr(runner, "_replace_criteria", explode)
    with pytest.raises(RuntimeError, match="simulated"):
        do_import(engine, path)
    assert count(engine, Scholarship) == 0 and count(engine, ScholarshipValue) == 0 and count(engine, ScholarshipCriterion) == 0
    with Session(engine) as s:
        run = s.scalars(select(ImportRun)).one()
        assert run.status == "failed" and run.error_message == "RuntimeError" and run.inserted == 0
    monkeypatch.undo()
    assert do_import(engine, path).inserted == 3  # and a clean retry works


def test_database_constraint_violation_rolls_back_the_whole_import(engine, tmp_path: Path) -> None:
    # two different records that collide on a unique column only at write time -> IntegrityError -> nothing persists
    recs = [etl_record(scholarship_id="SP-A"), etl_record(scholarship_id="SP-B")]
    plan = plan_import(write_json(tmp_path / "a.json", recs))
    plan.valid[1][1].scholarship_id = "SP-A"  # sabotage after validation
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        run_import(engine, plan)
    assert count(engine, Scholarship) == 0


def test_reviewed_criteria_survive_a_reimport_when_the_rule_is_unchanged(engine, tmp_path: Path) -> None:
    path = tmp_path / "a.json"
    do_import(engine, write_json(path, records()))
    with Session(engine) as s, s.begin():
        row = s.scalars(select(Scholarship).where(Scholarship.scholarship_id == "SP-RUN000001")).one()
        pct = next(c for c in row.criteria if c.criterion_type == "minimum_percentage")
        pct.review_status, pct.evidence_text = "reviewed", "Checked against the official notification"
    changed = records()
    changed[0]["award_amount_text"] = "text changed, rules unchanged"
    assert do_import(engine, write_json(path, changed)).updated == 1
    with Session(engine) as s:
        row = s.scalars(select(Scholarship).where(Scholarship.scholarship_id == "SP-RUN000001")).one()
        pct = next(c for c in row.criteria if c.criterion_type == "minimum_percentage")
        assert (pct.review_status, pct.evidence_text) == ("reviewed", "Checked against the official notification")
        income = next(c for c in row.criteria if c.criterion_type == "maximum_family_income")
        assert income.review_status == "unreviewed"
    # when the rule itself changes, the old review no longer applies
    changed[0]["minimum_percentage"] = 70
    do_import(engine, write_json(path, changed))
    with Session(engine) as s:
        pct = next(c for c in s.scalars(select(Scholarship).where(Scholarship.scholarship_id == "SP-RUN000001")).one().criteria if c.criterion_type == "minimum_percentage")
        assert (pct.required_value, pct.review_status, pct.evidence_text) == ({"value": 70}, "unreviewed", None)


def test_reviewer_added_criteria_are_never_removed(engine, tmp_path: Path) -> None:
    path = tmp_path / "a.json"
    do_import(engine, write_json(path, records()))
    with Session(engine) as s, s.begin():
        row = s.scalars(select(Scholarship).where(Scholarship.scholarship_id == "SP-RUN000001")).one()
        row.criteria.append(ScholarshipCriterion(criterion_type="other_rule", label="Reviewer note", operator="text", required_value={"text": "added by a person"}, origin="reviewer", display_order=100, review_status="reviewed", evidence_text="official FAQ"))
    changed = records()
    changed[0]["award_amount_text"] = "changed"
    do_import(engine, write_json(path, changed))
    with Session(engine) as s:
        row = s.scalars(select(Scholarship).where(Scholarship.scholarship_id == "SP-RUN000001")).one()
        assert [c.label for c in row.criteria if c.origin == "reviewer"] == ["Reviewer note"]


def test_records_missing_from_the_file_are_counted_but_never_deleted(engine, tmp_path: Path) -> None:
    do_import(engine, write_json(tmp_path / "a.json", records()))
    report = do_import(engine, write_json(tmp_path / "b.json", records()[:1]))
    assert report.absent_from_input == 2 and report.unchanged == 1
    assert count(engine, Scholarship) == 3


def test_import_never_modifies_its_input(engine, tmp_path: Path) -> None:
    path = write_json(tmp_path / "a.json", records())
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    do_import(engine, path)
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
