"""Deterministic eligibility engine: per-criterion statuses and overall outcomes."""

from __future__ import annotations

import pytest

from app.domain import CriterionView
from app.services.eligibility import StudentProfile, evaluate, evaluate_criterion, format_inr
from tests.support import criterion, view

GOOD = StudentProfile(state="Madhya Pradesh", education_level="UG", percentage=72, family_income=300000, category="OBC", gender="FEMALE")


def check(spec: CriterionView, profile: StudentProfile = GOOD, *, verified: bool = False):
    return evaluate_criterion(spec, profile, scholarship_verified=verified)


def status(spec: CriterionView, profile: StudentProfile = GOOD) -> str:
    return check(spec, profile).status


# ------------------------------------------------------------------ state / category / gender
def test_state() -> None:
    spec = criterion("state", "in", {"values": ["Madhya Pradesh", "Bihar"]})
    assert status(spec) == "pass"
    assert status(spec, StudentProfile(state="madhya pradesh")) == "pass"  # case-insensitive
    assert status(spec, StudentProfile(state="Kerala")) == "fail"
    assert status(spec, StudentProfile()) == "missing"
    open_spec = criterion("state", "in", {"values": ["ALL"]})
    assert status(open_spec, StudentProfile()) == "pass"  # an explicit "all states" rule needs no student value


def test_category() -> None:
    spec = criterion("category", "in", {"values": ["SC", "ST", "OBC"]})
    assert status(spec) == "pass" and status(spec, StudentProfile(category="GENERAL")) == "fail"
    assert status(spec, StudentProfile()) == "missing"
    assert status(criterion("category", "in", {"values": ["ALL"]}), StudentProfile()) == "pass"


def test_gender() -> None:
    spec = criterion("gender", "in", {"values": ["FEMALE"]})
    assert status(spec) == "pass" and status(spec, StudentProfile(gender="MALE")) == "fail" and status(spec, StudentProfile()) == "missing"
    assert check(spec, StudentProfile(gender="MALE")).student_value == "Male"


# ------------------------------------------------------------------ numbers
def test_minimum_percentage_boundaries() -> None:
    spec = criterion("minimum_percentage", "gte", {"value": 60})
    assert status(spec, StudentProfile(percentage=60)) == "pass"  # equal passes
    assert status(spec, StudentProfile(percentage=59.99)) == "fail"
    assert status(spec, StudentProfile()) == "missing"
    result = check(spec, StudentProfile(percentage=45))
    assert result.required == "At least 60%" and result.student_value == "45%" and "below" in result.explanation


def test_income_limit_strict_vs_inclusive() -> None:
    lte = criterion("maximum_family_income", "lte", {"value": 450000, "comparator": None})
    lt = criterion("maximum_family_income", "lt", {"value": 450000, "comparator": "<"})
    at_limit = StudentProfile(family_income=450000)
    assert status(lte, at_limit) == "pass" and status(lt, at_limit) == "fail"
    assert status(lt, StudentProfile(family_income=449999)) == "pass" and status(lte, StudentProfile(family_income=450001)) == "fail"
    assert status(lte, StudentProfile()) == "missing"
    assert check(lt, at_limit).required == "Below ₹4,50,000" and check(lte, at_limit).required == "Up to ₹4,50,000"


def test_zero_income_is_a_real_value_not_missing() -> None:
    spec = criterion("maximum_family_income", "lte", {"value": 100000, "comparator": None})
    assert status(spec, StudentProfile(family_income=0)) == "pass"


# ------------------------------------------------------------------ ambiguous rules
def test_education_level_matches_but_a_mismatch_is_never_a_confirmed_fail() -> None:
    spec = criterion("education_level", "in", {"values": ["12"]})
    assert status(spec, StudentProfile(education_level="12")) == "pass"
    mismatch = check(spec, StudentProfile(education_level="UG"))
    assert mismatch.status == "unable_to_verify"  # '12' may mean "studying in" or "completed"
    assert "does not say whether" in mismatch.explanation and "Undergraduate" in mismatch.explanation
    assert status(spec, StudentProfile()) == "missing"
    assert status(criterion("education_level", "in", {"values": ["ALL"]}), StudentProfile()) == "pass"
    assert check(criterion("education_level", "in", {"values": ["9", "10"]})).required == "Education level: Class 9, Class 10"


def test_courses_can_only_pass_when_open_to_all() -> None:
    assert status(criterion("course", "in", {"values": ["ALL"]})) == "pass"
    ambiguous = check(criterion("course", "in", {"values": ["B.SC", "M.Sc"]}), StudentProfile(course="B.Sc Physics"))
    assert ambiguous.status == "unable_to_verify" and "free text" in ambiguous.explanation


def test_free_text_rules_are_quoted_and_unable_to_verify() -> None:
    result = check(criterion("other_rule", "text", {"text": "Family income limit (as stated in source): HIGHER ED. - 120000,SCHOOL-54000"}))
    assert result.status == "unable_to_verify" and "HIGHER ED. - 120000,SCHOOL-54000" in result.required


def test_unknown_criterion_type_is_unable_to_verify_not_a_crash() -> None:
    assert status(criterion("some_future_type", "text", {})) == "unable_to_verify"


def test_every_result_has_an_explanation_and_echoes_evidence() -> None:
    spec = CriterionView("state", "State", "in", {"values": ["Bihar"]}, True, "reviewed", "Official notification, section 3", "https://x.gov.in/n", "file / sheet / row 2", 0)
    result = check(spec, StudentProfile(state="Bihar"), verified=True)
    assert result.explanation and result.evidence is not None
    assert (result.evidence.text, result.evidence.url, result.evidence.source_ref) == ("Official notification, section 3", "https://x.gov.in/n", "file / sheet / row 2")
    assert result.reliable is True
    assert check(criterion("state", "in", {"values": ["Bihar"]}), StudentProfile(state="Bihar")).reliable is False


# ------------------------------------------------------------------ outcomes
def reliable(criterion_type: str, operator: str, value: dict, order: int = 0, **kw) -> CriterionView:
    return criterion(criterion_type, operator, value, reviewed=True, evidence="Official source says so", order=order, **kw)


def full_reliable_scholarship(status_value: str = "verified"):
    return view(status=status_value, criteria=[
        reliable("state", "in", {"values": ["Madhya Pradesh"]}, 0),
        reliable("category", "in", {"values": ["OBC"]}, 1),
        reliable("minimum_percentage", "gte", {"value": 60}, 2),
        reliable("maximum_family_income", "lte", {"value": 450000, "comparator": None}, 3),
    ])


def test_eligible_only_when_verified_and_every_mandatory_rule_is_reviewed_supported_and_met() -> None:
    result = evaluate(full_reliable_scholarship(), GOOD)
    assert result.outcome == "eligible" and result.basis.rules_reliable is True
    assert (result.basis.mandatory_criteria, result.basis.reviewed_mandatory_criteria, result.basis.supported_mandatory_criteria) == (4, 4, 4)
    assert all(c.status == "pass" and c.reliable for c in result.criteria) and result.limitations == []


def test_not_eligible_when_a_reviewed_mandatory_rule_fails() -> None:
    result = evaluate(full_reliable_scholarship(), StudentProfile(state="Madhya Pradesh", category="GENERAL", percentage=80, family_income=1000))
    assert result.outcome == "not_eligible" and "Category" in result.summary
    assert result.indicative == "some_criteria_not_met"


def test_a_confirmed_failure_beats_missing_information() -> None:
    result = evaluate(full_reliable_scholarship(), StudentProfile(state="Kerala"))  # fails state; the rest is missing
    assert result.outcome == "not_eligible" and result.missing_information == ["category", "family_income", "percentage"]


def test_pending_scholarship_can_never_be_eligible_or_not_eligible() -> None:
    for profile in (GOOD, StudentProfile(state="Kerala", category="GENERAL")):
        result = evaluate(full_reliable_scholarship("pending"), profile)
        assert result.outcome == "cant_tell_yet"
        assert any("has not been verified" in line for line in result.limitations)
    assert evaluate(full_reliable_scholarship("pending"), GOOD).indicative == "all_listed_criteria_met"  # a hint, not a decision
    assert evaluate(full_reliable_scholarship("needs_review"), GOOD).outcome == "cant_tell_yet"


def test_unreviewed_rules_on_a_verified_scholarship_are_not_enough() -> None:
    unreviewed = view(status="verified", criteria=[criterion("state", "in", {"values": ["Madhya Pradesh"]}, evidence="has evidence but no review")])
    result = evaluate(unreviewed, GOOD)
    assert result.outcome == "cant_tell_yet" and result.basis.rules_reliable is False
    assert any("no reviewed, evidence-backed" in line for line in result.limitations)


def test_reviewed_rules_without_evidence_are_not_enough() -> None:
    no_evidence = view(status="verified", criteria=[criterion("state", "in", {"values": ["Madhya Pradesh"]}, reviewed=True)])  # only a source_ref
    result = evaluate(no_evidence, GOOD)
    assert result.outcome == "cant_tell_yet" and result.basis.supported_mandatory_criteria == 0 and result.criteria[0].reliable is False


def test_a_failing_unreviewed_rule_cannot_produce_not_eligible() -> None:
    mixed = view(status="verified", criteria=[
        reliable("state", "in", {"values": ["Madhya Pradesh"]}, 0),
        criterion("category", "in", {"values": ["SC"]}, order=1),  # fails for an OBC student, but is unreviewed
    ])
    result = evaluate(mixed, GOOD)
    assert result.outcome == "cant_tell_yet" and result.indicative == "some_criteria_not_met"
    assert "unreviewed" in result.summary


def test_missing_student_information_gives_cant_tell_yet_and_names_the_fields() -> None:
    result = evaluate(full_reliable_scholarship(), StudentProfile(state="Madhya Pradesh"))
    assert result.outcome == "cant_tell_yet" and result.indicative == "incomplete"
    assert result.missing_information == ["category", "family_income", "percentage"]
    assert "details are missing" in result.summary
    assert [c.status for c in result.criteria] == ["pass", "missing", "missing", "missing"]


def test_an_unverifiable_mandatory_rule_blocks_a_positive_outcome() -> None:
    sch = view(status="verified", criteria=[
        reliable("state", "in", {"values": ["ALL"]}, 0),
        reliable("other_rule", "text", {"text": "Must hold a domicile certificate"}, 1),
    ])
    result = evaluate(sch, GOOD)
    assert result.outcome == "cant_tell_yet" and "cannot be checked automatically" in result.summary


def test_optional_criteria_do_not_affect_the_outcome() -> None:
    sch = view(status="verified", criteria=[
        reliable("state", "in", {"values": ["Madhya Pradesh"]}, 0),
        reliable("category", "in", {"values": ["SC"]}, 1, mandatory=False),  # fails but is optional
    ])
    result = evaluate(sch, GOOD)
    assert result.outcome == "eligible"
    assert [c.status for c in result.criteria] == ["pass", "fail"] and result.criteria[1].is_mandatory is False


def test_scholarship_without_criteria_is_cant_tell_yet() -> None:
    result = evaluate(view(status="verified"), GOOD)
    assert result.outcome == "cant_tell_yet" and result.indicative == "no_criteria_listed" and result.criteria == []
    assert any("No eligibility criteria" in line for line in result.limitations)


def test_criteria_are_reported_in_display_order_and_results_are_deterministic() -> None:
    shuffled = view(status="verified", criteria=[
        criterion("category", "in", {"values": ["OBC"]}, order=2), criterion("state", "in", {"values": ["ALL"]}, order=0),
        criterion("minimum_percentage", "gte", {"value": 50}, order=1),
    ])
    first, second = evaluate(shuffled, GOOD), evaluate(shuffled, GOOD)
    assert first == second
    assert [c.criterion_type for c in first.criteria] == ["state", "minimum_percentage", "category"]


@pytest.mark.parametrize(
    "value, expected",
    [(0, "₹0"), (999, "₹999"), (1000, "₹1,000"), (450000, "₹4,50,000"), (12345678, "₹1,23,45,678"), (2500.5, "₹2,500.50")],
)
def test_indian_digit_grouping(value: float, expected: str) -> None:
    assert format_inr(value) == expected
