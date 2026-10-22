"""Column-name normalization, canonical mapping and row -> ScholarshipRecord conversion.

Policy for each value (see README 'Normalization policy'):

* clean and convert when the meaning is unambiguous;
* if a value is present but cannot be read unambiguously, store ``None``, keep the
  original text in ``extra_attributes`` / ``eligibility_rules`` and raise a warning;
* if a value is present but invalid (bad URL, impossible date...), the validator
  reports an error - nothing is silently fixed or dropped.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Iterable, Mapping

from pydantic import ValidationError

from scholarpath_data.load_excel import SheetData
from scholarpath_data.parsers import (
    clean_text,
    government_level_to_scheme_type,
    match_key,
    parse_academic_year,
    parse_amount,
    parse_date,
    parse_income,
    parse_percentage,
    parse_url_cell,
    resolve_states,
    split_list,
)
from scholarpath_data.schema import (
    ALL_SENTINEL,
    Issue,
    ScholarshipRecord,
    SchemeType,
    SourceType,
    VerificationStatus,
    make_issue,
)

# --------------------------------------------------------------------------- #
# Column names
# --------------------------------------------------------------------------- #


def normalize_column_name(name: Any) -> str:
    """'Scholarship Name' / 'scholarshipName' / ' SCHOLARSHIP_ID ' -> snake_case."""
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(name).strip())  # camelCase -> camel_Case
    text = re.sub(r"[^0-9A-Za-z]+", "_", text).strip("_").lower()
    return text or "unnamed"


def normalize_columns(columns: Iterable[Any]) -> dict[str, str]:
    """Map each original header to a unique normalized name (``name_2`` for repeats)."""
    result: dict[str, str] = {}
    seen: Counter[str] = Counter()
    for original in columns:
        base = normalize_column_name(original)
        seen[base] += 1
        result[str(original)] = base if seen[base] == 1 else f"{base}_{seen[base]}"
    return result


# internal key -> accepted normalized column names. Canonical field names map to themselves.
_ALIASES: dict[str, tuple[str, ...]] = {
    "scholarship_id": ("scholarship_id", "scheme_id", "sch_id", "record_id", "id"),
    "scholarship_name": ("scholarship_name", "scheme_name", "name", "scholarship", "scheme", "title"),
    "provider_name": ("provider_name", "provider", "department", "ministry", "organisation", "organization", "agency"),
    "scheme_type": ("scheme_type",),
    "government_level": ("government_level", "govt_level", "level_of_government"),
    "academic_year": ("academic_year", "academic_session", "session"),
    "education_level": ("education_level", "educational_level", "class_level", "study_level"),
    "eligible_courses": ("eligible_courses", "courses", "course", "eligible_streams", "streams"),
    "eligible_states": ("eligible_states", "states", "state"),
    "eligible_categories": ("eligible_categories", "categories", "category", "caste_category", "eligible_category"),
    "gender": ("gender", "eligible_gender"),
    "minimum_percentage": ("minimum_percentage", "min_percentage", "minimum_marks", "min_marks", "minimum_percent"),
    "maximum_family_income": ("maximum_family_income", "max_family_income", "family_income", "income_limit", "annual_family_income", "max_income"),
    "award_amount_min": ("award_amount_min", "amount_min", "min_amount", "minimum_amount"),
    "award_amount_max": ("award_amount_max", "amount_max", "max_amount", "maximum_amount"),
    "amount": ("amount", "award_amount", "scholarship_amount", "benefit_amount"),
    "award_amount_text": ("award_amount_text", "amount_text"),
    "key_benefits": ("key_benefits", "benefits", "benefit"),
    "application_open_date": ("application_open_date", "open_date", "opening_date", "start_date", "application_start_date"),
    "application_deadline": ("application_deadline", "deadline", "last_date", "due_date", "closing_date", "application_end_date"),
    "required_documents": ("required_documents", "documents", "documents_required"),
    "eligibility_rules": ("eligibility_rules", "eligibility", "eligibility_criteria"),
    "application_procedure": ("application_procedure", "procedure", "how_to_apply"),
    "official_url": ("official_url", "official_link", "official_website", "url", "link", "website"),
    "source_url": ("source_url",),
    "source_name": ("source_name",),
    "last_verified_at": ("last_verified_at", "last_verified", "verified_at"),
    "verification_status": ("verification_status", "verified_status"),
    "review_notes": ("review_notes", "notes", "reviewer_notes"),
}
_ALIAS_TO_KEY: dict[str, str] = {alias: key for key, aliases in _ALIASES.items() for alias in aliases}


@dataclass
class ColumnMapping:
    by_key: dict[str, str] = field(default_factory=dict)  # internal key -> normalized column
    extras: list[str] = field(default_factory=list)  # normalized columns kept in extra_attributes


def map_columns(normalized_columns: Iterable[str]) -> ColumnMapping:
    """Assign normalized column names to canonical keys; the first column claiming a key wins."""
    mapping = ColumnMapping()
    for column in normalized_columns:
        key = _ALIAS_TO_KEY.get(column)
        if key is None or key in mapping.by_key:
            mapping.extras.append(column)
        else:
            mapping.by_key[key] = column
    return mapping


# --------------------------------------------------------------------------- #
# Row -> record
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SourceContext:
    source_file: str
    source_name: str
    source_type: SourceType
    extracted_at: datetime


@dataclass
class NormalizedRecord:
    record: ScholarshipRecord
    issues: list[Issue]
    id_generated: bool


@dataclass(frozen=True)
class RowFailure:
    sheet: str
    row: int
    message: str


class _Acc:
    """Collects fields, extra attributes and issues while one row is converted."""

    def __init__(self) -> None:
        self.fields: dict[str, Any] = {}
        self.extra: dict[str, Any] = {}
        self.rules: list[str] = []
        self.issues: list[Issue] = []

    def issue(self, code: str, field_name: str | None = None, detail: str | None = None) -> None:
        self.issues.append(make_issue(code, field_name, detail))


_DATE_CODES = {"ambiguous": "date_ambiguous", "invalid": "date_invalid", "unparsed": "date_unparsed"}


def make_scholarship_id(name: str | None, provider: str | None, level: str | None, fallback: str) -> str:
    """Deterministic id: same name+provider+level -> same id on every run."""
    basis = "|".join((match_key(name), match_key(provider), match_key(level))) if name else f"row|{fallback}"
    return "SP-" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:10].upper()


def _map_dates(acc: _Acc, get: Callable[[str], Any]) -> None:
    for key in ("application_open_date", "application_deadline", "last_verified_at"):
        raw = get(key)
        result = parse_date(raw)
        if result.status == "ok":
            acc.fields[key] = result.value
        elif result.status != "missing":
            acc.issue(_DATE_CODES[result.status], key, f"source value {clean_text(raw)!r}")
            acc.extra[f"{key}_raw"] = clean_text(raw)


def _map_eligibility(acc: _Acc, get: Callable[[str], Any]) -> None:
    acc.fields["education_level"] = split_list(get("education_level"), upper=True, all_sentinel=True)
    acc.fields["eligible_courses"] = split_list(get("eligible_courses"), all_sentinel=True)
    acc.fields["eligible_categories"] = split_list(get("eligible_categories"), upper=True, all_sentinel=True)
    states, unknown = resolve_states(get("eligible_states"))
    acc.fields["eligible_states"] = states
    for token in unknown:
        acc.issue("unrecognized_state", "eligible_states", f"value {token!r}")

    acc.rules.extend(split_list(get("eligibility_rules"), separators=re.compile(r"[;|]")))

    percentage, status = parse_percentage(get("minimum_percentage"))
    if status == "ok":
        acc.fields["minimum_percentage"] = percentage
    elif status == "ambiguous":
        text = clean_text(get("minimum_percentage"))
        acc.issue("percentage_not_numeric", "minimum_percentage", f"source value {text!r}")
        acc.extra["minimum_percentage_raw"] = text
        acc.rules.append(f"Minimum percentage (as stated in source): {text}")

    income = parse_income(get("maximum_family_income"))
    if income.status == "ok":
        acc.fields["maximum_family_income"] = income.value
        if income.comparator:
            acc.extra["maximum_family_income_comparator"] = income.comparator
    elif income.status == "ambiguous":
        text = clean_text(get("maximum_family_income"))
        acc.issue("income_not_numeric", "maximum_family_income", f"source value {text!r}")
        acc.extra["maximum_family_income_raw"] = text
        acc.rules.append(f"Family income limit (as stated in source): {text}")

    genders = split_list(get("gender"), upper=True, all_sentinel=True)
    if genders:
        acc.extra["gender"] = genders
        if genders != [ALL_SENTINEL] and not {"MALE", "FEMALE"} <= set(genders):
            acc.rules.append(f"Gender (as stated in source): {', '.join(genders)}")


def _map_award(acc: _Acc, get: Callable[[str], Any]) -> None:
    explicit_min, explicit_max = get("award_amount_min"), get("award_amount_max")
    amount_raw = clean_text(get("amount"))
    if clean_text(explicit_min) is not None or clean_text(explicit_max) is not None:
        low, high = parse_amount(explicit_min), parse_amount(explicit_max)
        if low.status == "ok":
            acc.fields["award_amount_min"] = low.minimum
        if high.status == "ok":
            acc.fields["award_amount_max"] = high.maximum
        if "ambiguous" in (low.status, high.status):
            acc.issue("amount_not_numeric", "award_amount", f"source values {clean_text(explicit_min)!r} / {clean_text(explicit_max)!r}")
    else:
        parsed = parse_amount(get("amount"))
        if parsed.status == "ok":
            acc.fields["award_amount_min"], acc.fields["award_amount_max"] = parsed.minimum, parsed.maximum
        elif parsed.status == "ambiguous":
            acc.issue("amount_not_numeric", "award_amount", f"source value {amount_raw!r}")
            acc.extra["amount_raw"] = amount_raw

    text = clean_text(get("award_amount_text")) or clean_text(get("key_benefits"))
    if text is None and "amount_raw" in acc.extra:
        text = acc.extra["amount_raw"]
    acc.fields["award_amount_text"] = text


def _map_provenance(acc: _Acc, get: Callable[[str], Any], ctx: SourceContext) -> None:
    official = parse_url_cell(get("official_url"))
    acc.fields["official_url"] = official.url
    if official.multiple:
        acc.extra["official_urls_all"] = official.all_urls
        acc.issue("official_url_multiple", "official_url", f"source cell {official.raw!r}")
    elif official.cleaned:
        acc.issue("official_url_cleaned", "official_url", f"source cell {official.raw!r}")
    acc.fields["source_url"] = parse_url_cell(get("source_url")).url
    acc.fields["source_name"] = clean_text(get("source_name")) or ctx.source_name


_STATUS_ALIASES = {
    "pending": VerificationStatus.PENDING, "unverified": VerificationStatus.PENDING,
    "not_verified": VerificationStatus.PENDING,
    "needs_review": VerificationStatus.NEEDS_REVIEW, "need_review": VerificationStatus.NEEDS_REVIEW,
    "rejected": VerificationStatus.REJECTED,
}


def _map_verification(acc: _Acc, get: Callable[[str], Any]) -> None:
    """The pipeline never grants 'verified' (see verification.py for the only path)."""
    raw = clean_text(get("verification_status"))
    notes = [n for n in (clean_text(get("review_notes")),) if n]
    status = VerificationStatus.PENDING
    if raw is not None:
        key = re.sub(r"[\s-]+", "_", raw.casefold())
        if key == "verified":
            status = VerificationStatus.NEEDS_REVIEW
            acc.issue("verification_claim_unconfirmed", "verification_status", f"source value {raw!r}")
            notes.append("Source status 'verified' was not accepted: no reviewer/evidence recorded in the pipeline.")
        elif key in _STATUS_ALIASES:
            status = _STATUS_ALIASES[key]
        else:
            status = VerificationStatus.NEEDS_REVIEW
            acc.issue("verification_status_unrecognized", "verification_status", f"source value {raw!r}")
            acc.extra["verification_status_raw"] = raw
    acc.fields["verification_status"] = status
    acc.fields["review_notes"] = "; ".join(notes) or None


def _map_identity(acc: _Acc, get: Callable[[str], Any]) -> tuple[str | None, str | None, str | None]:
    name = clean_text(get("scholarship_name"))
    provider = clean_text(get("provider_name"))
    if provider and name and match_key(provider) == match_key(name):
        acc.issue("provider_copies_scheme_name", "provider_name", f"source value {provider!r}")
        acc.extra["provider_raw"] = provider
        provider = None
    acc.fields["scholarship_name"], acc.fields["provider_name"] = name, provider

    level_raw = clean_text(get("government_level"))
    if level_raw:
        acc.extra["government_level"] = level_raw
    explicit_type = clean_text(get("scheme_type"))
    scheme_type: str | None = None
    if explicit_type and explicit_type.casefold() in {t.value for t in SchemeType}:
        scheme_type = explicit_type.casefold()
    elif level_raw:
        scheme_type = government_level_to_scheme_type(level_raw)
        if scheme_type is None:
            acc.issue("scheme_type_unmapped", "scheme_type", f"government_level {level_raw!r}")
    acc.fields["scheme_type"] = scheme_type

    year, status = parse_academic_year(get("academic_year"))
    if status == "ok":
        acc.fields["academic_year"] = year
    elif status == "unparsed":
        raw_year = clean_text(get("academic_year"))
        acc.issue("academic_year_unparsed", "academic_year", f"source value {raw_year!r}")
        acc.extra["academic_year_raw"] = raw_year
    acc.fields["application_procedure"] = clean_text(get("application_procedure"))
    acc.fields["required_documents"] = split_list(get("required_documents"))
    return name, provider, level_raw


def build_record(
    row: Mapping[str, Any],
    mapping: ColumnMapping,
    ctx: SourceContext,
    sheet_name: str,
    source_row: int,
) -> NormalizedRecord:
    """Convert one source row (keyed by normalized column name) into a canonical record."""

    def get(key: str) -> Any:
        column = mapping.by_key.get(key)
        return row.get(column) if column is not None else None

    acc = _Acc()
    name, provider, level = _map_identity(acc, get)
    _map_eligibility(acc, get)
    _map_award(acc, get)
    _map_dates(acc, get)
    _map_provenance(acc, get, ctx)
    _map_verification(acc, get)

    for column in mapping.extras:
        value = clean_text(row.get(column))
        if value is not None:
            acc.extra[column] = value

    source_id = clean_text(get("scholarship_id"))
    record = ScholarshipRecord(
        scholarship_id=source_id or make_scholarship_id(name, provider, level, f"{sheet_name}|{source_row}"),
        eligibility_rules=acc.rules,
        source_type=ctx.source_type,
        extracted_at=ctx.extracted_at,
        source_record_id=source_id,
        source_file=ctx.source_file,
        source_sheet=sheet_name,
        source_row=source_row,
        extra_attributes=acc.extra,
        **acc.fields,
    )
    return NormalizedRecord(record=record, issues=acc.issues, id_generated=source_id is None)


def normalize_sheet(sheet: SheetData, ctx: SourceContext) -> tuple[list[NormalizedRecord], list[RowFailure]]:
    """Convert every data row of a sheet; rows that cannot be built are reported, not dropped silently."""
    normalized = normalize_columns(sheet.columns)
    mapping = map_columns(normalized.values())
    names = [normalized[c] for c in sheet.columns]
    records: list[NormalizedRecord] = []
    failures: list[RowFailure] = []
    for row_number, values in zip(sheet.frame.index, sheet.frame.itertuples(index=False, name=None)):
        try:
            records.append(build_record(dict(zip(names, values)), mapping, ctx, sheet.name, int(row_number)))
        except (ValidationError, ValueError, TypeError) as exc:
            failures.append(RowFailure(sheet.name, int(row_number), f"{type(exc).__name__}: {exc}"))
    return records, failures


def make_ids_unique(records: list[NormalizedRecord]) -> None:
    """Generated ids that collide (identical name/provider/level) get '-2', '-3'... in row order.

    Source-provided ids are never changed; duplicates among them are reported by the validator.
    """
    seen: Counter[str] = Counter(r.record.scholarship_id for r in records if not r.id_generated)
    for item in records:
        if not item.id_generated:
            continue
        base = item.record.scholarship_id
        seen[base] += 1
        if seen[base] > 1:
            item.record.scholarship_id = f"{base}-{seen[base]}"
