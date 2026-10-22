"""Map a validated ETL record to database rows: scholarship columns, filter values and criteria.

Every one of the 35 ETL columns is accounted for (see ``tests/test_importer_mapping.py``). Derived rows
are deterministic: the same record always yields the same values and criteria.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.domain import ALL, CriterionView
from app.services.importer.records import ImportRecord

MAPPING_VERSION = 1  # bump when derivation rules change so unchanged inputs are re-derived on the next import
GENDER_RULE_PREFIX = "Gender (as stated in source):"  # wording written by the ETL for restricted-gender schemes

# Where every one of the 35 ETL columns ends up. ``tests/test_importer_mapping.py`` checks this stays complete,
# so no useful field can be silently discarded. "values:<kind>" = scholarship_values rows; "criteria" = derived
# scholarship_criteria rows (the column ALSO lands in its own scholarships column unless noted).
COLUMN_DESTINATIONS: dict[str, str] = {
    "scholarship_id": "scholarships.scholarship_id",
    "scholarship_name": "scholarships.name",
    "provider_name": "scholarships.provider_name",
    "scheme_type": "scholarships.scheme_type",
    "academic_year": "scholarships.academic_year",
    "education_level": "values:education_level + criteria",
    "eligible_courses": "values:course + criteria",
    "eligible_states": "values:state + criteria",
    "eligible_categories": "values:category + criteria",
    "minimum_percentage": "scholarships.minimum_percentage + criteria",
    "maximum_family_income": "scholarships.maximum_family_income + criteria",
    "award_amount_min": "scholarships.award_amount_min",
    "award_amount_max": "scholarships.award_amount_max",
    "award_amount_text": "scholarships.award_amount_text",
    "application_open_date": "scholarships.application_open_date",
    "application_deadline": "scholarships.application_deadline",
    "required_documents": "scholarships.required_documents",
    "eligibility_rules": "scholarships.eligibility_rules + criteria (other_rule)",
    "application_procedure": "scholarships.application_procedure",
    "official_url": "scholarships.official_url",
    "source_url": "scholarships.source_url",
    "source_name": "scholarships.source_name",
    "source_type": "scholarships.source_type",
    "extracted_at": "scholarships.extracted_at",
    "last_verified_at": "scholarships.last_verified_at",
    "verification_status": "scholarships.verification_status",
    "review_notes": "scholarships.review_notes",
    "source_record_id": "scholarships.source_record_id",
    "source_file": "scholarships.source_file",
    "source_sheet": "scholarships.source_sheet",
    "source_row": "scholarships.source_row",
    "duplicate_group_id": "scholarships.duplicate_group_id",
    "validation_status": "scholarships.etl_validation_status",
    "validation_issue_codes": "scholarships.etl_issue_codes",
    "extra_attributes": "scholarships.extra_attributes (+ government_level, income_comparator, values:gender)",
}


def source_hash(record: ImportRecord) -> str:
    """sha256 of the canonical record + mapping version; equal hash => nothing to update."""
    payload = {"mapping_version": MAPPING_VERSION, "record": record.model_dump(mode="json")}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def gender_values(record: ImportRecord) -> list[str]:
    raw = record.extra_attributes.get("gender")
    if not isinstance(raw, list):
        return []
    return [str(v).strip().upper() for v in raw if str(v).strip()]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = value.strip()
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            out.append(text)
    return out


def scholarship_fields(record: ImportRecord) -> dict[str, Any]:
    """Column values for the ``scholarships`` table (nulls stay null)."""
    comparator = record.extra_attributes.get("maximum_family_income_comparator")
    government_level = record.extra_attributes.get("government_level")
    return {
        "scholarship_id": record.scholarship_id,
        "name": record.scholarship_name,
        "provider_name": record.provider_name,
        "scheme_type": record.scheme_type,
        "government_level": government_level if isinstance(government_level, str) else None,
        "academic_year": record.academic_year,
        "minimum_percentage": record.minimum_percentage,
        "maximum_family_income": record.maximum_family_income,
        "income_comparator": comparator if comparator in ("<", "<=") else None,
        "award_amount_min": record.award_amount_min,
        "award_amount_max": record.award_amount_max,
        "award_amount_text": record.award_amount_text,
        "application_open_date": record.application_open_date,
        "application_deadline": record.application_deadline,
        "application_procedure": record.application_procedure,
        "required_documents": list(record.required_documents),
        "eligibility_rules": list(record.eligibility_rules),
        "official_url": record.official_url,
        "source_url": record.source_url,
        "source_name": record.source_name,
        "source_type": record.source_type,
        "extracted_at": record.extracted_at,
        "last_verified_at": record.last_verified_at,
        "verification_status": record.verification_status,
        "review_notes": record.review_notes,
        "etl_validation_status": record.validation_status,
        "etl_issue_codes": list(record.validation_issue_codes),
        "duplicate_group_id": record.duplicate_group_id,
        "source_file": record.source_file,
        "source_sheet": record.source_sheet,
        "source_row": record.source_row,
        "source_record_id": record.source_record_id,
        "extra_attributes": dict(record.extra_attributes),
    }


def value_rows(record: ImportRecord) -> list[tuple[str, str]]:
    """(kind, value) rows for the filterable ``scholarship_values`` table."""
    rows: list[tuple[str, str]] = []
    for kind, values in (
        ("education_level", [v.upper() for v in record.education_level]),
        ("course", record.eligible_courses),
        ("state", record.eligible_states),
        ("category", [v.upper() for v in record.eligible_categories]),
        ("gender", gender_values(record)),
    ):
        rows += [(kind, v) for v in _unique(values)]
    return rows


def source_ref(record: ImportRecord) -> str | None:
    """ETL-provided provenance of a derived criterion (file / sheet / row). Not a citation of the rule itself."""
    parts = [record.source_file, record.source_sheet, f"row {record.source_row}" if record.source_row is not None else None]
    text = " / ".join(p for p in parts if p)
    return text or None


def criterion_specs(record: ImportRecord) -> list[CriterionView]:
    """Eligibility criteria derived from the record's fields.

    * Fields the source is silent about produce no criterion (silence is not "open to everyone").
    * All rows are unreviewed, mandatory (the canonical eligibility fields *are* the conditions) and carry no
      evidence, because the ETL does not provide any.
    """
    ref = source_ref(record)
    specs: list[CriterionView] = []

    def add(criterion_type: str, label: str, operator: str, required_value: dict[str, Any]) -> None:
        specs.append(
            CriterionView(criterion_type, label, operator, required_value, True, "unreviewed", None, None, ref, len(specs))
        )

    levels = _unique([v.upper() for v in record.education_level])
    if levels:
        add("education_level", "Education level", "in", {"values": levels})
    states = _unique(record.eligible_states)
    if states:
        add("state", "State of residence", "in", {"values": states})
    categories = _unique([v.upper() for v in record.eligible_categories])
    if categories:
        add("category", "Category", "in", {"values": categories})

    genders = gender_values(record)
    gender_restricted = bool(genders) and ALL not in genders and not {"MALE", "FEMALE"} <= set(genders)
    if gender_restricted:
        add("gender", "Gender", "in", {"values": _unique(genders)})

    courses = _unique(record.eligible_courses)
    if courses:
        add("course", "Course or stream", "in", {"values": courses})
    if record.minimum_percentage is not None:
        add("minimum_percentage", "Minimum academic percentage", "gte", {"value": record.minimum_percentage})
    if record.maximum_family_income is not None:
        comparator = record.extra_attributes.get("maximum_family_income_comparator")
        strict = comparator == "<"
        add(
            "maximum_family_income", "Maximum annual family income", "lt" if strict else "lte",
            {"value": record.maximum_family_income, "comparator": "<" if strict else ("<=" if comparator == "<=" else None)},
        )
    for rule in record.eligibility_rules:
        text = rule.strip()
        if not text or (gender_restricted and text.startswith(GENDER_RULE_PREFIX)):
            continue  # the structured gender criterion already covers it
        add("other_rule", "Other condition (as stated in source)", "text", {"text": text})
    return specs
