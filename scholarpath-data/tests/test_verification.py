"""Verification is only reachable through an explicit, complete reviewer decision."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from conftest import build, make_row
from scholarpath_data.errors import SourceError
from scholarpath_data.normalize import NormalizedRecord
from scholarpath_data.schema import VerificationStatus
from scholarpath_data.verification import DECISION_COLUMNS, apply_decisions, load_decisions

AS_OF = date(2026, 6, 1)


def item(name: str = "Alpha", **kw: object) -> NormalizedRecord:
    rec, issues = build(make_row(**{"Scholarship Name": name}, **kw))
    return NormalizedRecord(rec, issues, True)


def decision(sid: str, **kw: str) -> dict[str, str]:
    base = {"scholarship_id": sid, "decision": "verified", "reviewer": "S. Kumar", "reviewed_at": "2026-05-20",
            "evidence_url": "https://scholarships.gov.in/Scholarships", "notes": "", "_row": "2"}
    base.update(kw)
    return base


def test_records_start_pending_and_stay_so_without_decisions() -> None:
    it = item()
    outcome = apply_decisions([it], [], AS_OF, set())
    assert it.record.verification_status is VerificationStatus.PENDING
    assert outcome.applied == [] and outcome.rows_read == 0


def test_complete_decision_verifies_and_records_evidence() -> None:
    it = item()
    outcome = apply_decisions([it], [decision(it.record.scholarship_id, notes="Checked against NSP page")], AS_OF, set())
    rec = it.record
    assert rec.verification_status is VerificationStatus.VERIFIED
    assert rec.last_verified_at == date(2026, 5, 20)
    assert rec.extra_attributes["verification_evidence_url"] == "https://scholarships.gov.in/Scholarships"
    assert "verified by S. Kumar on 2026-05-20" in rec.review_notes and "Checked against NSP page" in rec.review_notes
    assert outcome.applied[0]["decision"] == "verified" and outcome.refused == []


@pytest.mark.parametrize(
    "override, reason",
    [
        ({"reviewer": ""}, "reviewer is required"),
        ({"reviewed_at": ""}, "unambiguous date"),
        ({"reviewed_at": "03/04/2026"}, "unambiguous date"),
        ({"reviewed_at": "2026-12-31"}, "future"),
        ({"evidence_url": ""}, "evidence_url"),
        ({"evidence_url": "scholarships.gov.in"}, "evidence_url"),
        ({"decision": "approved"}, "unknown decision"),
    ],
)
def test_incomplete_decisions_are_refused_and_record_stays_pending(override: dict[str, str], reason: str) -> None:
    it = item()
    outcome = apply_decisions([it], [decision(it.record.scholarship_id, **override)], AS_OF, set())
    assert it.record.verification_status is VerificationStatus.PENDING
    assert it.record.last_verified_at is None
    assert outcome.applied == [] and reason in outcome.refused[0]["reason"]
    assert "verification_decision_rejected" in {i.code for i in it.issues}


def test_cannot_verify_a_record_that_still_has_validation_errors() -> None:
    it = item()
    outcome = apply_decisions([it], [decision(it.record.scholarship_id)], AS_OF, {it.record.scholarship_id})
    assert it.record.verification_status is VerificationStatus.PENDING
    assert "validation errors" in outcome.refused[0]["reason"]


def test_shared_ids_are_never_verified() -> None:
    a, b = item("A"), item("B")
    a.record.scholarship_id = b.record.scholarship_id = "SAME"
    outcome = apply_decisions([a, b], [decision("SAME")], AS_OF, set())
    assert a.record.verification_status is b.record.verification_status is VerificationStatus.PENDING
    assert "shared by several records" in outcome.refused[0]["reason"]


def test_needs_review_and_rejected_do_not_need_evidence_but_do_need_a_reviewer() -> None:
    it, other = item("A"), item("B")
    apply_decisions([it, other], [decision(it.record.scholarship_id, decision="rejected", evidence_url="", notes="not a scholarship"),
                                  decision(other.record.scholarship_id, decision="needs_review", evidence_url="")], AS_OF, set())
    assert it.record.verification_status is VerificationStatus.REJECTED
    assert it.record.last_verified_at is None  # only a real verification sets this
    assert other.record.verification_status is VerificationStatus.NEEDS_REVIEW

    third = item("C")
    refused = apply_decisions([third], [decision(third.record.scholarship_id, decision="rejected", reviewer="")], AS_OF, set())
    assert third.record.verification_status is VerificationStatus.PENDING
    assert refused.refused[0]["reason"] == "reviewer is required"


def test_unmatched_ids_are_reported_not_ignored() -> None:
    outcome = apply_decisions([item()], [decision("SP-DOES-NOT-EXIST")], AS_OF, set())
    assert outcome.unmatched_ids == ["SP-DOES-NOT-EXIST"] and outcome.applied == []


def test_latest_decision_for_an_id_wins() -> None:
    it = item()
    sid = it.record.scholarship_id
    apply_decisions([it], [decision(sid), decision(sid, decision="rejected", evidence_url="", _row="3")], AS_OF, set())
    assert it.record.verification_status is VerificationStatus.REJECTED


def test_non_government_evidence_is_noted_for_the_reviewer() -> None:
    it = item()
    apply_decisions([it], [decision(it.record.scholarship_id, evidence_url="https://www.aicte-india.org/schemes")], AS_OF, set())
    assert it.record.verification_status is VerificationStatus.VERIFIED
    assert "not .gov.in" in it.record.review_notes


def test_load_decisions_reads_rows_with_line_numbers(tmp_path: Path) -> None:
    path = tmp_path / "d.csv"
    path.write_text(",".join(DECISION_COLUMNS) + "\nSP-1,verified,Me,2026-05-01,https://a.gov.in,ok\n\nSP-2,rejected,Me,2026-05-02,,bad\n", encoding="utf-8-sig")
    rows = load_decisions(path)
    assert [r["scholarship_id"] for r in rows] == ["SP-1", "SP-2"] and [r["_row"] for r in rows] == ["2", "4"]


def test_load_decisions_reports_missing_columns(tmp_path: Path) -> None:
    path = tmp_path / "d.csv"
    path.write_text("scholarship_id,decision\nSP-1,verified\n", encoding="utf-8")
    with pytest.raises(SourceError, match="missing column.*reviewed_at.*reviewer"):
        load_decisions(path)
