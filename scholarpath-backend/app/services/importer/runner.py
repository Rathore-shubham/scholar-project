"""Plan and apply an import.

``plan_import`` is pure (no database): it validates records, detects duplicate ids, and decides what is
skipped or failed. ``run_import`` applies a plan inside ONE transaction: either every valid record is written
or, on any database error, nothing is.

Definitions used in the report:
    read       records found in the file
    failed     invalid records (validation errors, bad JSON cells, duplicate ids in the file) - not imported
    skipped    valid but deliberately not imported (the ETL itself flagged validation errors)
    inserted / updated / unchanged   outcome for each imported record (unchanged = identical content hash)
Nothing is ever deleted: records present in the database but absent from the file are only counted.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, object_session, selectinload

from app.domain import CriterionView
from app.models import ImportRun, Scholarship, ScholarshipCriterion, ScholarshipValue
from app.services.importer.mapping import criterion_specs, scholarship_fields, source_hash, value_rows
from app.services.importer.records import ImportInputError, ImportRecord, InputFile, read_input, validate_row

CHUNK = 400


@dataclass(frozen=True)
class ImportIssue:
    row: int  # 1-based record position in the file
    scholarship_id: str | None
    reason: str


@dataclass
class ImportPlan:
    input: InputFile
    valid: list[tuple[int, ImportRecord]] = field(default_factory=list)
    skipped: list[ImportIssue] = field(default_factory=list)
    failed: list[ImportIssue] = field(default_factory=list)

    @property
    def records_read(self) -> int:
        return len(self.input.rows)


@dataclass
class ImportReport:
    source_file: str
    source_format: str
    source_sha256: str
    dry_run: bool
    records_read: int = 0
    valid: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    failed: int = 0
    absent_from_input: int | None = None
    unmapped_columns: list[str] = field(default_factory=list)
    skipped_details: list[ImportIssue] = field(default_factory=list)
    failed_details: list[ImportIssue] = field(default_factory=list)
    duplicate_groups_in_input: int = 0
    status_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def plan_import(path: str | Path, *, include_errors: bool = False) -> ImportPlan:
    """Validate a CSV/JSON file without touching any database."""
    input_file = read_input(path)
    plan = ImportPlan(input_file)
    parsed: list[tuple[int, ImportRecord]] = []
    for row in input_file.rows:
        try:
            record = validate_row(row, input_file.unmapped_columns)
        except ValueError as exc:
            sid = row.data.get("scholarship_id")
            plan.failed.append(ImportIssue(row.index, str(sid) if sid else None, str(exc)))
            continue
        parsed.append((row.index, record))

    counts = Counter(rec.scholarship_id for _, rec in parsed)
    for index, record in parsed:
        if counts[record.scholarship_id] > 1:
            plan.failed.append(
                ImportIssue(index, record.scholarship_id, f"scholarship_id appears {counts[record.scholarship_id]} times in the file; identity is ambiguous")
            )
        elif record.validation_status == "error" and not include_errors:
            codes = ", ".join(record.validation_issue_codes) or "unspecified"
            plan.skipped.append(ImportIssue(index, record.scholarship_id, f"ETL flagged validation errors ({codes}); use --include-errors to import anyway"))
        else:
            plan.valid.append((index, record))
    plan.failed.sort(key=lambda issue: issue.row)
    return plan


def report_for_plan(plan: ImportPlan, *, dry_run: bool) -> ImportReport:
    groups = {rec.duplicate_group_id for _, rec in plan.valid if rec.duplicate_group_id}
    return ImportReport(
        source_file=plan.input.path.name,
        source_format=plan.input.format,
        source_sha256=plan.input.sha256,
        dry_run=dry_run,
        records_read=plan.records_read,
        valid=len(plan.valid),
        skipped=len(plan.skipped),
        failed=len(plan.failed),
        unmapped_columns=list(plan.input.unmapped_columns),
        skipped_details=list(plan.skipped),
        failed_details=list(plan.failed),
        duplicate_groups_in_input=len(groups),
        status_counts=dict(Counter(rec.verification_status for _, rec in plan.valid)),
    )


def _criterion_key(spec_type: str, operator: str, value: dict[str, Any]) -> str:
    return json.dumps([spec_type, operator, value], sort_keys=True, ensure_ascii=False)


def _apply_fields(obj: Scholarship, fields: dict[str, Any], digest: str, run_id: int) -> None:
    for key, value in fields.items():
        setattr(obj, key, value)
    obj.source_hash = digest
    obj.last_import_run_id = run_id


def _flush_removals(obj: Scholarship) -> None:
    """SQLAlchemy runs INSERTs before DELETEs; flush removals first so re-inserted rows cannot hit unique constraints."""
    session = object_session(obj)
    if session is not None:
        session.flush()


def _replace_values(obj: Scholarship, rows: list[tuple[str, str]]) -> None:
    obj.values.clear()
    _flush_removals(obj)
    obj.values.extend(ScholarshipValue(kind=kind, value=value) for kind, value in rows)


def _replace_criteria(obj: Scholarship, specs: list[CriterionView]) -> None:
    """Replace ETL-derived criteria, but carry over review state when the rule itself is unchanged.

    Criteria added by a reviewer (origin='reviewer') are never touched.
    """
    previous = {
        _criterion_key(c.criterion_type, c.operator, c.required_value): c for c in obj.criteria if c.origin == "etl"
    }
    for old in [c for c in obj.criteria if c.origin == "etl"]:
        obj.criteria.remove(old)
    _flush_removals(obj)
    for spec in specs:
        old = previous.get(_criterion_key(spec.criterion_type, spec.operator, spec.required_value))
        obj.criteria.append(
            ScholarshipCriterion(
                criterion_type=spec.criterion_type,
                label=spec.label,
                operator=spec.operator,
                required_value=spec.required_value,
                is_mandatory=spec.is_mandatory,
                review_status=old.review_status if old else spec.review_status,
                evidence_text=old.evidence_text if old else spec.evidence_text,
                evidence_url=old.evidence_url if old else spec.evidence_url,
                source_ref=spec.source_ref,
                origin="etl",
                display_order=spec.display_order,
            )
        )


def apply_plan(session: Session, plan: ImportPlan, run: ImportRun) -> ImportReport:
    """Write a plan using ``session`` (the caller owns the transaction)."""
    report = report_for_plan(plan, dry_run=False)
    ids = [rec.scholarship_id for _, rec in plan.valid]
    existing: dict[str, Scholarship] = {}
    for start in range(0, len(ids), CHUNK):
        rows = session.scalars(
            select(Scholarship)
            .where(Scholarship.scholarship_id.in_(ids[start : start + CHUNK]))
            .options(selectinload(Scholarship.values), selectinload(Scholarship.criteria))
        )
        existing.update({row.scholarship_id: row for row in rows})

    now = datetime.now(timezone.utc)
    for _, record in plan.valid:
        digest = source_hash(record)
        obj = existing.get(record.scholarship_id)
        if obj is None:
            obj = Scholarship(**scholarship_fields(record), source_hash=digest, last_import_run_id=run.id)
            _replace_values(obj, value_rows(record))
            _replace_criteria(obj, criterion_specs(record))
            session.add(obj)
            report.inserted += 1
        elif obj.source_hash == digest:
            report.unchanged += 1
        else:
            _apply_fields(obj, scholarship_fields(record), digest, run.id)
            obj.updated_at = now
            _replace_values(obj, value_rows(record))
            _replace_criteria(obj, criterion_specs(record))
            report.updated += 1
    session.flush()

    in_file = set(ids)
    all_ids = set(session.scalars(select(Scholarship.scholarship_id)))
    report.absent_from_input = len(all_ids - in_file)
    return report


def run_import(engine: Any, plan: ImportPlan) -> ImportReport:
    """Apply ``plan`` in a single transaction; on failure roll everything back and record a failed run."""
    started = datetime.now(timezone.utc)
    try:
        with Session(engine, expire_on_commit=False) as session, session.begin():
            run = ImportRun(
                started_at=started,
                source_file=plan.input.path.name,
                source_sha256=plan.input.sha256,
                source_format=plan.input.format,
                records_read=plan.records_read,
                status="running",
            )
            session.add(run)
            session.flush()
            report = apply_plan(session, plan, run)
            run.inserted, run.updated, run.unchanged = report.inserted, report.updated, report.unchanged
            run.skipped, run.failed = report.skipped, report.failed
            run.status, run.finished_at = "succeeded", datetime.now(timezone.utc)
        return report
    except Exception as exc:
        # The failed transaction is rolled back (nothing was written). Best-effort audit row, error *type* only.
        try:
            with Session(engine) as audit, audit.begin():
                audit.add(
                    ImportRun(
                        started_at=started, finished_at=datetime.now(timezone.utc),
                        source_file=plan.input.path.name, source_sha256=plan.input.sha256,
                        source_format=plan.input.format, records_read=plan.records_read,
                        failed=plan.records_read, status="failed", error_message=type(exc).__name__,
                    )
                )
        except Exception:  # noqa: BLE001 - e.g. tables missing; the original error is what matters
            pass
        raise


__all__ = [
    "ImportInputError", "ImportIssue", "ImportPlan", "ImportReport",
    "apply_plan", "plan_import", "report_for_plan", "run_import",
]
