"""Deterministic, rule-based eligibility engine (no database, no AI, no scores).

Per-criterion status
    pass              the rule is known, the student's value is known, and the rule is satisfied
    fail              the rule is known, the student's value is known, and the rule is NOT satisfied
    missing           the student has not supplied the value this rule needs
    unable_to_verify  the rule is free text or ambiguous, or cannot be compared reliably

Overall outcome
    eligible       every mandatory criterion passes AND is reliable
    not_eligible   at least one mandatory criterion fails AND is reliable
    cant_tell_yet  everything else

A criterion is *reliable* only when the scholarship is ``verified``, the criterion is ``reviewed`` and it has
supporting evidence (text or URL). Rules extracted from the ETL carry no review or evidence, so on real,
unverified data this engine can only ever answer ``cant_tell_yet`` - it still reports every criterion and an
``indicative`` hint, but never declares eligibility from unreviewed rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.domain import ALL, CriterionView, ScholarshipView
from app.services.vocabulary import GENDER_LABELS, education_label

Status = Literal["pass", "fail", "missing", "unable_to_verify"]
Outcome = Literal["eligible", "not_eligible", "cant_tell_yet"]
Indicative = Literal["all_listed_criteria_met", "some_criteria_not_met", "incomplete", "no_criteria_listed"]


@dataclass(frozen=True)
class StudentProfile:
    """Normalized student facts. ``None`` always means "not provided"."""

    state: str | None = None
    education_level: str | None = None  # ETL token: "10", "12", "UG", "PG", "DIPLOMA"...
    percentage: float | None = None
    family_income: float | None = None
    category: str | None = None  # upper-case code: "SC", "GENERAL"...
    gender: str | None = None  # MALE / FEMALE / OTHERS
    course: str | None = None


@dataclass(frozen=True)
class Evidence:
    text: str | None
    url: str | None
    source_ref: str | None


@dataclass(frozen=True)
class CriterionResult:
    criterion_type: str
    name: str
    required: str
    student_value: str | None
    status: Status
    explanation: str
    is_mandatory: bool
    review_status: str
    reliable: bool
    needs_profile_field: str | None
    evidence: Evidence | None


@dataclass(frozen=True)
class Basis:
    verification_status: str
    mandatory_criteria: int
    reviewed_mandatory_criteria: int
    supported_mandatory_criteria: int
    rules_reliable: bool


@dataclass(frozen=True)
class EligibilityResult:
    scholarship_id: str
    scholarship_name: str
    outcome: Outcome
    summary: str
    indicative: Indicative
    basis: Basis
    missing_information: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    criteria: list[CriterionResult] = field(default_factory=list)


# ----------------------------------------------------------------------------------------------- formatting
def format_inr(value: float) -> str:
    """12345678 -> ₹1,23,45,678 (Indian digit grouping)."""
    whole = int(value) if float(value).is_integer() else None
    text = f"{whole}" if whole is not None else f"{value:.2f}"
    integer, _, fraction = text.partition(".")
    head, tail = integer[:-3], integer[-3:]
    groups = []
    while head:
        groups.insert(0, head[-2:])
        head = head[:-2]
    grouped = ",".join([*groups, tail]) if groups else tail
    return "₹" + grouped + (f".{fraction}" if fraction else "")


def _number(value: float) -> str:
    return f"{value:g}"


def _join(values: list[str]) -> str:
    return ", ".join(values)


def _values(spec: CriterionView) -> list[str]:
    raw = spec.required_value.get("values")
    return [str(v) for v in raw] if isinstance(raw, list) else []


# ----------------------------------------------------------------------------------------------- criteria
def _result(
    spec: CriterionView, required: str, student: str | None, status: Status, explanation: str,
    needs: str | None, reliable: bool,
) -> CriterionResult:
    evidence = Evidence(spec.evidence_text, spec.evidence_url, spec.source_ref) if (
        spec.evidence_text or spec.evidence_url or spec.source_ref
    ) else None
    return CriterionResult(
        criterion_type=spec.criterion_type, name=spec.label, required=required, student_value=student,
        status=status, explanation=explanation, is_mandatory=spec.is_mandatory, review_status=spec.review_status,
        reliable=reliable, needs_profile_field=needs if status == "missing" else None, evidence=evidence,
    )


def evaluate_criterion(spec: CriterionView, profile: StudentProfile, *, scholarship_verified: bool) -> CriterionResult:
    reliable = scholarship_verified and spec.review_status == "reviewed" and spec.has_evidence

    def make(required: str, student: str | None, status: Status, explanation: str, needs: str | None = None) -> CriterionResult:
        return _result(spec, required, student, status, explanation, needs, reliable)

    kind, values = spec.criterion_type, _values(spec)
    is_all = any(v.upper() == ALL for v in values)

    if kind == "state":
        required = "Open to all states" if is_all else f"Resident of: {_join(values)}"
        if is_all:
            return make(required, profile.state, "pass", "This scholarship is open to students from every state.")
        if profile.state is None:
            return make(required, None, "missing", "Add your state of residence to check this requirement.", "state")
        if profile.state.casefold() in {v.casefold() for v in values}:
            return make(required, profile.state, "pass", f"Your state ({profile.state}) is one of the listed states.")
        return make(required, profile.state, "fail", f"Your state ({profile.state}) is not among the listed states ({_join(values)}).")

    if kind == "category":
        required = "Open to all categories" if is_all else f"Category: {_join(values)}"
        if is_all:
            return make(required, profile.category, "pass", "This scholarship is open to every category.")
        if profile.category is None:
            return make(required, None, "missing", "Add your category to check this requirement.", "category")
        if profile.category in {v.upper() for v in values}:
            return make(required, profile.category, "pass", f"Your category ({profile.category}) is one of the listed categories.")
        return make(required, profile.category, "fail", f"Your category ({profile.category}) is not among the listed categories ({_join(values)}).")

    if kind == "gender":
        required = f"Gender: {_join([GENDER_LABELS.get(v.upper(), v) for v in values])}"
        if is_all:
            return make("Open to all genders", profile.gender, "pass", "This scholarship has no gender restriction.")
        student = GENDER_LABELS.get(profile.gender or "", profile.gender)
        if profile.gender is None:
            return make(required, None, "missing", "Add your gender to check this requirement.", "gender")
        if profile.gender in {v.upper() for v in values}:
            return make(required, student, "pass", f"Your gender ({student}) matches the listed gender.")
        return make(required, student, "fail", f"Your gender ({student}) does not match the listed gender.")

    if kind == "education_level":
        labels = [education_label(v) for v in values]
        required = "Open to all education levels" if is_all else f"Education level: {_join(labels)}"
        student = education_label(profile.education_level) if profile.education_level else None
        if is_all:
            return make(required, student, "pass", "This scholarship is open to every education level.")
        if profile.education_level is None:
            return make(required, None, "missing", "Add your education level to check this requirement.", "education_level")
        if profile.education_level.upper() in {v.upper() for v in values}:
            return make(required, student, "pass", f"Your education level ({student}) is one of the listed levels.")
        return make(
            required, student, "unable_to_verify",
            f"The source lists {_join(labels)}, which does not directly match {student}. The source does not say whether a "
            "level means 'currently studying in' or 'completed', so this cannot be confirmed here. Check the official page.",
        )

    if kind == "course":
        required = "Open to all courses" if is_all else f"Courses: {_join(values)}"
        if is_all:
            return make(required, profile.course, "pass", "This scholarship is open to every course or stream.")
        return make(
            required, profile.course, "unable_to_verify",
            f"The source lists {_join(values)}. Course names are free text and cannot be matched reliably, so check the official page.",
        )

    if kind == "minimum_percentage":
        minimum = float(spec.required_value["value"])
        required = f"At least {_number(minimum)}%"
        if profile.percentage is None:
            return make(required, None, "missing", "Add your academic percentage to check this requirement.", "percentage")
        student = f"{_number(profile.percentage)}%"
        if profile.percentage >= minimum:
            return make(required, student, "pass", f"Your percentage ({student}) is at least {_number(minimum)}%.")
        return make(required, student, "fail", f"Your percentage ({student}) is below the required {_number(minimum)}%.")

    if kind == "maximum_family_income":
        limit = float(spec.required_value["value"])
        strict = spec.operator == "lt"
        required = f"Below {format_inr(limit)}" if strict else f"Up to {format_inr(limit)}"
        if profile.family_income is None:
            return make(required, None, "missing", "Add your annual family income to check this requirement.", "family_income")
        student = format_inr(profile.family_income)
        ok = profile.family_income < limit if strict else profile.family_income <= limit
        if ok:
            return make(required, student, "pass", f"Your family income ({student}) is within the limit ({required.lower()}).")
        return make(required, student, "fail", f"Your family income ({student}) is above the limit ({required.lower()}).")

    text = str(spec.required_value.get("text") or spec.label)
    return make(
        f"As stated in the source: {text}", None, "unable_to_verify",
        "The source states this condition only as text, so it cannot be checked automatically. Read it on the official page.",
    )


# ----------------------------------------------------------------------------------------------- overall
def _indicative(results: list[CriterionResult]) -> Indicative:
    if not results:
        return "no_criteria_listed"
    statuses = {r.status for r in results if r.is_mandatory}
    if "fail" in statuses:
        return "some_criteria_not_met"
    if statuses & {"missing", "unable_to_verify"}:
        return "incomplete"
    return "all_listed_criteria_met" if statuses else "no_criteria_listed"


def evaluate(scholarship: ScholarshipView, profile: StudentProfile) -> EligibilityResult:
    verified = scholarship.verification_status == "verified"
    results = [
        evaluate_criterion(spec, profile, scholarship_verified=verified)
        for spec in sorted(scholarship.criteria, key=lambda c: c.display_order)
    ]
    mandatory = [r for r in results if r.is_mandatory]
    reviewed = sum(r.review_status == "reviewed" for r in mandatory)
    supported = sum(r.evidence is not None and (r.evidence.text or r.evidence.url) is not None for r in mandatory)
    rules_reliable = bool(mandatory) and all(r.reliable for r in mandatory)
    basis = Basis(scholarship.verification_status, len(mandatory), reviewed, supported, rules_reliable)

    reliable_failures = [r for r in mandatory if r.status == "fail" and r.reliable]
    unmet_or_unknown = [r for r in mandatory if r.status != "pass" or not r.reliable]
    missing_fields = sorted({r.needs_profile_field for r in results if r.needs_profile_field})
    limitations: list[str] = []
    if not verified:
        limitations.append(
            f"This record has not been verified (status: {scholarship.verification_status}). Its rules were extracted from "
            "source data and may be incomplete or out of date, so no definite eligibility result is given."
        )
    elif not rules_reliable and mandatory:
        limitations.append("Some mandatory rules have no reviewed, evidence-backed entry on record.")
    if not mandatory:
        limitations.append("No eligibility criteria are recorded for this scholarship.")

    if reliable_failures:
        outcome: Outcome = "not_eligible"
        names = ", ".join(r.name for r in reliable_failures)
        summary = f"Not eligible: at least one reviewed mandatory criterion is not met ({names})."
    elif mandatory and all(r.status == "pass" and r.reliable for r in mandatory):
        outcome = "eligible"
        summary = "Eligible: every mandatory criterion on record is met, reviewed and supported by evidence."
    else:
        outcome = "cant_tell_yet"
        reasons = []
        if not verified:
            reasons.append("the scholarship's rules are unverified")
        elif unmet_or_unknown and not all(r.reliable for r in mandatory):
            reasons.append("some rules lack reviewed evidence")
        if missing_fields:
            reasons.append("some of your details are missing")
        if any(r.status == "unable_to_verify" for r in mandatory):
            reasons.append("some rules cannot be checked automatically")
        if any(r.status == "fail" for r in mandatory):
            reasons.append("at least one listed criterion does not match your profile, but that rule is unreviewed")
        if not mandatory:
            reasons.append("no eligibility criteria are recorded")
        summary = "Can't tell yet: " + "; ".join(reasons or ["the available information is not sufficient"]) + "."

    return EligibilityResult(
        scholarship_id=scholarship.scholarship_id, scholarship_name=scholarship.name, outcome=outcome, summary=summary,
        indicative=_indicative(results), basis=basis, missing_information=missing_fields, limitations=limitations,
        criteria=results,
    )
