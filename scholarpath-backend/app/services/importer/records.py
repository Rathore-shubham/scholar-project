"""Reading and validating ETL records (``scholarships_cleaned.csv`` / ``.json``).

``ETL_COLUMNS`` is the exact 35-column contract of the ETL output. Records are validated *before* anything
touches the database; invalid ones are reported (never silently dropped, never partially imported).
"""

from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from app.core.url_check import is_valid_http_url

ETL_COLUMNS: tuple[str, ...] = (
    "scholarship_id", "scholarship_name", "provider_name", "scheme_type", "academic_year",
    "education_level", "eligible_courses", "eligible_states", "eligible_categories",
    "minimum_percentage", "maximum_family_income",
    "award_amount_min", "award_amount_max", "award_amount_text",
    "application_open_date", "application_deadline",
    "required_documents", "eligibility_rules", "application_procedure",
    "official_url", "source_url", "source_name", "source_type",
    "extracted_at", "last_verified_at", "verification_status", "review_notes",
    "source_record_id", "source_file", "source_sheet", "source_row",
    "duplicate_group_id", "validation_status", "validation_issue_codes", "extra_attributes",
)
REQUIRED_COLUMNS = ("scholarship_id", "scholarship_name", "source_type", "extracted_at", "verification_status")
LIST_COLUMNS = frozenset(
    {"education_level", "eligible_courses", "eligible_states", "eligible_categories",
     "required_documents", "eligibility_rules", "validation_issue_codes"}
)
JSON_COLUMNS = LIST_COLUMNS | {"extra_attributes"}
UNMAPPED_KEY = "import_unmapped_columns"


class ImportInputError(Exception):
    """The input file itself cannot be imported (missing, wrong format, wrong columns)."""


class ImportRecord(BaseModel):
    """One ETL record. Strict about structure; never invents values."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    scholarship_id: str = Field(min_length=1, max_length=64)
    scholarship_name: str = Field(min_length=1)
    provider_name: str | None = None
    scheme_type: Literal["central", "state", "other"] | None = None
    academic_year: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}$")
    education_level: list[str] = Field(default_factory=list)
    eligible_courses: list[str] = Field(default_factory=list)
    eligible_states: list[str] = Field(default_factory=list)
    eligible_categories: list[str] = Field(default_factory=list)
    minimum_percentage: float | None = Field(default=None, ge=0, le=100)
    maximum_family_income: float | None = Field(default=None, ge=0)
    award_amount_min: float | None = Field(default=None, ge=0)
    award_amount_max: float | None = Field(default=None, ge=0)
    award_amount_text: str | None = None
    application_open_date: date | None = None
    application_deadline: date | None = None
    required_documents: list[str] = Field(default_factory=list)
    eligibility_rules: list[str] = Field(default_factory=list)
    application_procedure: str | None = None
    official_url: str | None = None
    source_url: str | None = None
    source_name: str | None = None
    source_type: str = Field(min_length=1, max_length=32)
    extracted_at: datetime
    last_verified_at: date | None = None
    verification_status: Literal["pending", "needs_review", "verified", "rejected"]
    review_notes: str | None = None
    source_record_id: str | None = None
    source_file: str | None = None
    source_sheet: str | None = None
    source_row: int | None = None
    duplicate_group_id: str | None = Field(default=None, max_length=32)
    validation_status: Literal["ok", "warning", "error"] | None = None
    validation_issue_codes: list[str] = Field(default_factory=list)
    extra_attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("official_url", "source_url")
    @classmethod
    def _url_must_be_http(cls, value: str | None) -> str | None:
        if value is not None and not is_valid_http_url(value):
            raise ValueError("not a valid http(s) URL (value withheld from reports in case it contains credentials)")
        return value

    @field_validator("extracted_at")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("extracted_at must include a timezone (the ETL writes UTC 'Z')")
        return value

    @model_validator(mode="after")
    def _cross_field_rules(self) -> ImportRecord:
        if (
            self.award_amount_min is not None and self.award_amount_max is not None
            and self.award_amount_min > self.award_amount_max
        ):
            raise ValueError("award_amount_min is greater than award_amount_max")
        if (
            self.application_open_date and self.application_deadline
            and self.application_deadline < self.application_open_date
        ):
            raise ValueError("application_deadline is before application_open_date")
        if self.verification_status == "verified":
            has_source = bool(self.official_url or self.source_url)
            if self.last_verified_at is None or not has_source:
                raise ValueError("status 'verified' requires last_verified_at and a source URL (no evidence, no verification)")
        return self


@dataclass(frozen=True)
class RawRow:
    index: int  # 1-based position of the record in the file (data rows only)
    data: dict[str, Any]


@dataclass(frozen=True)
class InputFile:
    path: Path
    format: str  # 'csv' | 'json'
    sha256: str
    rows: list[RawRow]
    unmapped_columns: list[str] = field(default_factory=list)


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _csv_cell(column: str, raw: str | None) -> Any:
    text = (raw or "").strip()
    if column in JSON_COLUMNS:
        if text == "":
            return {} if column == "extra_attributes" else []
        return json.loads(text)  # a malformed JSON cell raises ValueError -> record fails with a clear reason
    return text if text != "" else None


def read_input(path: str | Path) -> InputFile:
    """Read a CSV or JSON file written by the ETL. Never modifies the file."""
    file_path = Path(path)
    if not file_path.is_file():
        raise ImportInputError(f"Input file not found: {file_path}")
    suffix = file_path.suffix.lower()
    if suffix not in {".csv", ".json"}:
        raise ImportInputError(f"Unsupported input type '{file_path.suffix}'. Use scholarships_cleaned.csv or scholarships_cleaned.json.")
    try:
        sha = sha256_of(file_path)
        if suffix == ".json":
            payload = json.loads(file_path.read_text(encoding="utf-8-sig"))
            records = payload["records"] if isinstance(payload, dict) and "records" in payload else payload
            if not isinstance(records, list) or not all(isinstance(r, dict) for r in records):
                raise ImportInputError("JSON must be a list of records or an object with a 'records' list.")
            rows = [RawRow(i, dict(r)) for i, r in enumerate(records, start=1)]
            columns = {key for r in records for key in r}
            fmt = "json"
        else:
            with file_path.open(newline="", encoding="utf-8-sig") as handle:
                reader = csv.DictReader(handle)
                columns = set(reader.fieldnames or [])
                missing = [c for c in REQUIRED_COLUMNS if c not in columns]
                if missing:
                    raise ImportInputError(
                        f"{file_path.name} is missing required column(s): {', '.join(missing)}. "
                        "Expected the ETL's scholarships_cleaned.csv."
                    )
                rows = []
                for i, raw in enumerate(reader, start=1):
                    row: dict[str, Any] = {}
                    for key, value in raw.items():
                        if key is None:
                            continue
                        try:
                            row[key] = _csv_cell(key, value)
                        except ValueError as exc:
                            row.setdefault("__errors__", []).append(f"column '{key}': invalid JSON ({exc})")
                    rows.append(RawRow(i, row))
            fmt = "csv"
    except ImportInputError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, csv.Error, KeyError) as exc:
        raise ImportInputError(f"Cannot read {file_path.name}: {type(exc).__name__}: {exc}") from exc
    if fmt == "json":
        missing = [c for c in REQUIRED_COLUMNS if rows and c not in columns]
        if missing:
            raise ImportInputError(f"{file_path.name} records are missing required field(s): {', '.join(missing)}.")
    unmapped = sorted(c for c in columns if c not in ETL_COLUMNS)
    return InputFile(file_path, fmt, sha, rows, unmapped)


def validate_row(row: RawRow, unmapped: list[str]) -> ImportRecord:
    """Validate one raw row. Unknown columns are preserved inside ``extra_attributes`` (nothing is discarded)."""
    data = dict(row.data)
    errors = data.pop("__errors__", None)
    if errors:
        raise ValueError("; ".join(errors))
    extras = {key: data.pop(key) for key in list(data) if key not in ETL_COLUMNS}
    if extras:
        attrs = dict(data.get("extra_attributes") or {})
        attrs[UNMAPPED_KEY] = {k: v for k, v in extras.items() if v not in (None, "")}
        data["extra_attributes"] = attrs
    try:
        return ImportRecord.model_validate(data)
    except ValidationError as exc:
        reasons = []
        for err in exc.errors(include_input=False, include_url=False):
            where = ".".join(str(p) for p in err["loc"]) or "record"
            reasons.append(f"{where}: {err['msg']}")
        raise ValueError("; ".join(reasons)) from None
