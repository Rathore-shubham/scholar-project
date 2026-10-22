"""End-to-end pipeline: load -> raw snapshot -> normalize -> dedupe -> validate -> verify -> export.

Run::

    python -m scholarpath_data --input "path/to/scholarship.xlsx" --output-dir data

All counts in the report are computed from the records, never hard-coded. The source
file is only ever read; every output goes under ``--output-dir``.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from scholarpath_data import __version__
from scholarpath_data.console import configure_stdout, human_size
from scholarpath_data.deduplicate import (
    DEFAULT_THRESHOLD,
    DUPLICATE_COLUMNS,
    DuplicateGroup,
    duplicate_issues,
    duplicate_rows,
    find_duplicate_groups,
)
from scholarpath_data.errors import OutputError, ScholarPathError, SourceError
from scholarpath_data.export import (
    write_dict_rows_csv,
    write_json,
    write_records_csv,
    write_records_json,
    write_verified_csv,
)
from scholarpath_data.load_excel import LoadedSource, load_source, resolve_input, write_raw_snapshot
from scholarpath_data.normalize import (
    ColumnMapping,
    NormalizedRecord,
    RowFailure,
    SourceContext,
    make_ids_unique,
    map_columns,
    normalize_columns,
    normalize_sheet,
)
from scholarpath_data.schema import (
    CANONICAL_FIELDS,
    ISSUE_CATALOG,
    Issue,
    ScholarshipRecord,
    Severity,
    SourceType,
    VerificationStatus,
    make_issue,
)
from scholarpath_data.validate import (
    DEFAULT_MAX_VERIFICATION_AGE_DAYS,
    find_duplicate_ids,
    status_from_issues,
    unique_issues,
    validate_record,
)
from scholarpath_data.verification import DecisionOutcome, apply_decisions, load_decisions

OUTPUT_FILES = {
    "cleaned_csv": ("processed", "scholarships_cleaned.csv"),
    "cleaned_json": ("processed", "scholarships_cleaned.json"),
    "verified_csv": ("verified", "scholarships_verified.csv"),
    "quality_report": ("reports", "data_quality_report.json"),
    "possible_duplicates": ("reports", "possible_duplicates.csv"),
}
DEFAULT_DECISIONS_NAME = "verification_decisions.csv"


@dataclass
class PipelineResult:
    records: list[ScholarshipRecord]
    report: dict[str, Any]
    outputs: dict[str, Path]
    raw_dir: Path
    files_written: list[Path] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        return self.report["counts"]


def output_paths(output_root: Path) -> dict[str, Path]:
    return {key: output_root / folder / name for key, (folder, name) in OUTPUT_FILES.items()}


def _guard_outputs(input_path: Path, paths: dict[str, Path]) -> None:
    if input_path in {p.resolve() for p in paths.values()}:
        raise OutputError(
            f"The input file {input_path} is one of the pipeline's own output files. "
            "Point --input at the original source file instead."
        )


# --------------------------------------------------------------------------- #
# Issue bookkeeping
# --------------------------------------------------------------------------- #


def _final_issues(
    items: Sequence[NormalizedRecord],
    stage: dict[int, list[Issue]],
    as_of: date,
    max_age: int,
) -> list[list[Issue]]:
    duplicate_ids = find_duplicate_ids(i.record for i in items)
    result: list[list[Issue]] = []
    for index, item in enumerate(items):
        issues = list(item.issues) + stage.get(index, []) + validate_record(item.record, as_of, max_age)
        if item.record.scholarship_id in duplicate_ids:
            issues.append(make_issue("duplicate_scholarship_id", "scholarship_id", f"value {item.record.scholarship_id!r}"))
        result.append(unique_issues(issues))
    return result


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #


def _is_present(value: Any) -> bool:
    return value is not None and value != [] and value != ""


def _fields_without_source_column(mapping: ColumnMapping) -> list[str]:
    """Canonical fields this source has no column for (so they stay empty for every record)."""
    covered = set(mapping.by_key)
    if "amount" in covered:
        covered |= {"award_amount_min", "award_amount_max"}
    if "government_level" in covered:
        covered.add("scheme_type")
    if "key_benefits" in covered:
        covered.add("award_amount_text")
    always_supplied = {"extracted_at", "source_type", "source_name"}  # set by the pipeline, not the source
    return sorted(set(CANONICAL_FIELDS) - covered - always_supplied)


def build_report(
    source: LoadedSource,
    items: Sequence[NormalizedRecord],
    issues: Sequence[Sequence[Issue]],
    groups: Sequence[DuplicateGroup],
    failures: Sequence[RowFailure],
    outcome: DecisionOutcome | None,
    *,
    as_of: date,
    now: datetime,
    raw_dir: Path,
    extracted_at: datetime,
) -> dict[str, Any]:
    records = [i.record for i in items]
    status_counts = Counter(r.verification_status.value for r in records)
    total_rows = source.total_rows

    def severity_count(level: Severity) -> int:
        return sum(any(i.severity is level for i in rec_issues) for rec_issues in issues)

    by_code: dict[str, dict[str, Any]] = {}
    for rec_issues in issues:
        for issue in rec_issues:
            entry = by_code.setdefault(issue.code, {"severity": issue.severity.value, "records": 0, "fields": set()})
            entry["records"] += 1
            if issue.field:
                entry["fields"].add(issue.field)
    severity_order = {"error": 0, "warning": 1, "info": 2}
    issue_summary = {
        code: {"severity": e["severity"], "records": e["records"], "fields": sorted(e["fields"]), "description": ISSUE_CATALOG[code][1]}
        for code, e in sorted(by_code.items(), key=lambda kv: (severity_order[kv[1]["severity"]], -kv[1]["records"], kv[0]))
    }

    completeness = {}
    for name in CANONICAL_FIELDS:
        present = sum(_is_present(getattr(r, name)) for r in records)
        completeness[name] = {
            "present": present,
            "missing": len(records) - present,
            "percent_present": round(100 * present / len(records), 1) if records else 0.0,
        }

    columns = []
    for sheet in source.sheets:
        normalized = normalize_columns(sheet.columns)
        mapping = map_columns(normalized.values())
        reverse = {v: k for k, v in normalized.items()}
        columns.append(
            {
                "sheet": sheet.name,
                "header_row": sheet.header_row,
                "mapped": {reverse[col]: key for key, col in mapping.by_key.items()},
                "kept_in_extra_attributes": [reverse[col] for col in mapping.extras],
                "canonical_fields_without_source_column": _fields_without_source_column(mapping),
            }
        )

    flagged = []
    for item, rec_issues in zip(items, issues):
        if any(i.severity is not Severity.INFO for i in rec_issues):
            r = item.record
            flagged.append(
                {
                    "scholarship_id": r.scholarship_id,
                    "source_sheet": r.source_sheet,
                    "source_row": r.source_row,
                    "scholarship_name": r.scholarship_name,
                    "validation_status": r.validation_status,
                    "issues": [i.to_dict() for i in rec_issues],
                }
            )

    errors, warnings = severity_count(Severity.ERROR), severity_count(Severity.WARNING)
    return {
        "generated_at": now.isoformat(),
        "as_of": as_of.isoformat(),
        "pipeline_version": __version__,
        "source": {
            "file": source.path.name,
            "format": source.file_format,
            "size_bytes": source.size_bytes,
            "sha256": source.sha256,
            "first_extracted_at": extracted_at.isoformat(),
            "sheets_loaded": {s.name: len(s.frame) for s in source.sheets},
            "sheets_empty_skipped": source.empty_sheets,
            "blank_rows_skipped": sum(s.blank_rows_skipped for s in source.sheets),
            "notes": source.notes,
            "raw_snapshot_dir": raw_dir.name,
        },
        "counts": {
            "total_input_records": total_rows,
            "successfully_parsed_records": len(items),
            "records_failed_to_parse": len(failures),
            "records_with_validation_errors": errors,
            "records_with_warnings": warnings,
            "records_without_errors_or_warnings": sum(
                not any(i.severity is not Severity.INFO for i in rec_issues) for rec_issues in issues
            ),
            "possible_duplicate_groups": len(groups),
            "records_in_possible_duplicate_groups": sum(len(g.members) for g in groups),
            "records_marked_verified": status_counts.get(VerificationStatus.VERIFIED.value, 0),
            "records_pending_review": status_counts.get(VerificationStatus.PENDING.value, 0)
            + status_counts.get(VerificationStatus.NEEDS_REVIEW.value, 0),
        },
        "verification_status_counts": {s.value: status_counts.get(s.value, 0) for s in VerificationStatus},
        "ids": {
            "generated_by_pipeline": sum(i.id_generated for i in items),
            "taken_from_source": sum(not i.id_generated for i in items),
        },
        "issue_summary": issue_summary,
        "field_completeness": completeness,
        "columns": columns,
        "failed_rows": [{"sheet": f.sheet, "row": f.row, "message": f.message} for f in failures],
        "verification_decisions": outcome.to_dict() if outcome else None,
        "records_needing_attention": flagged,
    }


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


def run_pipeline(
    input_path: str | Path | None,
    output_root: str | Path = "data",
    *,
    sheets: Sequence[str] | None = None,
    source_name: str | None = None,
    source_type: SourceType | None = None,
    decisions_path: str | Path | None = None,
    as_of: date | None = None,
    duplicate_threshold: float = DEFAULT_THRESHOLD,
    max_verification_age_days: int = DEFAULT_MAX_VERIFICATION_AGE_DAYS,
    now: datetime | None = None,
    log: Callable[[str], None] = lambda _msg: None,
) -> PipelineResult:
    root = Path(output_root)
    now = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    as_of = as_of or now.date()
    outputs = output_paths(root)

    path = resolve_input(input_path, [root / "raw", Path.cwd()])
    _guard_outputs(path, outputs)

    log(f"[1/6] Loading {path.name} ({human_size(path.stat().st_size)})")
    source = load_source(path, sheets)
    for sheet in source.sheets:
        log(f"      sheet '{sheet.name}': {len(sheet.frame)} rows x {len(sheet.columns)} columns (header on row {sheet.header_row})")
    for name in source.empty_sheets:
        log(f"      sheet '{name}': empty, skipped")
    if source.total_rows == 0:
        raise SourceError(f"{path.name} has a header but no data rows.")

    log("[2/6] Writing raw layer (verbatim copy of every cell, original file untouched)")
    snapshot = write_raw_snapshot(source, root / "raw", now)

    log("[3/6] Normalizing columns and values")
    ctx = SourceContext(
        source_file=path.name,
        source_name=source_name or path.name,
        source_type=source_type or (SourceType.LOCAL_CSV if source.file_format == "csv" else SourceType.LOCAL_EXCEL),
        extracted_at=snapshot.extracted_at,
    )
    items: list[NormalizedRecord] = []
    failures: list[RowFailure] = []
    for sheet in source.sheets:
        sheet_items, sheet_failures = normalize_sheet(sheet, ctx)
        items += sheet_items
        failures += sheet_failures
    if not items:
        raise SourceError(f"None of the {source.total_rows} rows could be converted; see the failed rows above.")
    make_ids_unique(items)

    log("[4/6] Finding possible duplicates (nothing is merged or deleted)")
    records = [i.record for i in items]
    groups = find_duplicate_groups(records, duplicate_threshold)
    stage = duplicate_issues(groups, records)
    for group in groups:
        for index in group.members:
            records[index].duplicate_group_id = group.group_id

    log("[5/6] Validating and applying reviewer decisions")
    issues = _final_issues(items, stage, as_of, max_verification_age_days)
    outcome: DecisionOutcome | None = None
    decisions_file = Path(decisions_path) if decisions_path else root / "verified" / DEFAULT_DECISIONS_NAME
    if decisions_file.is_file():
        error_ids = {
            items[i].record.scholarship_id for i, rec in enumerate(issues) if any(x.severity is Severity.ERROR for x in rec)
        }
        outcome = apply_decisions(items, load_decisions(decisions_file), as_of, error_ids)
        log(f"      decisions: {len(outcome.applied)} applied, {len(outcome.refused)} refused, {len(outcome.unmatched_ids)} unmatched")
        issues = _final_issues(items, stage, as_of, max_verification_age_days)
    elif decisions_path:
        raise SourceError(f"Decisions file not found: {decisions_file}")
    for record, rec_issues in zip(records, issues):
        record.validation_status = status_from_issues(rec_issues)
        record.validation_issue_codes = sorted({i.code for i in rec_issues if i.severity is not Severity.INFO})

    log("[6/6] Writing outputs")
    report = build_report(
        source, items, issues, groups, failures, outcome,
        as_of=as_of, now=now, raw_dir=snapshot.directory, extracted_at=snapshot.extracted_at,
    )
    written = {
        "cleaned_csv": write_records_csv(records, outputs["cleaned_csv"]),
        "cleaned_json": write_records_json(records, outputs["cleaned_json"]),
        "verified_csv": write_verified_csv(records, outputs["verified_csv"]),
        "possible_duplicates": write_dict_rows_csv(duplicate_rows(groups, records), DUPLICATE_COLUMNS, outputs["possible_duplicates"]),
        "quality_report": write_json(report, outputs["quality_report"]),
    }
    files_written = [outputs[key] for key, was_written in written.items() if was_written]
    return PipelineResult(records, report, outputs, snapshot.directory, files_written)


def format_summary(result: PipelineResult) -> str:
    c = result.counts
    lines = [
        "",
        "Summary (computed from the data)",
        f"  total input records             : {c['total_input_records']}",
        f"  successfully parsed             : {c['successfully_parsed_records']}",
        f"  failed to parse                 : {c['records_failed_to_parse']}",
        f"  records with validation errors  : {c['records_with_validation_errors']}",
        f"  records with warnings           : {c['records_with_warnings']}",
        f"  possible duplicate groups       : {c['possible_duplicate_groups']}",
        f"  records marked verified         : {c['records_marked_verified']}",
        f"  records pending review          : {c['records_pending_review']}",
        "",
        "Top issues",
    ]
    shown = [(code, e) for code, e in result.report["issue_summary"].items() if e["severity"] != "info"][:8]
    lines += [f"  [{e['severity']:7}] {code:34} {e['records']:>3} record(s)" for code, e in shown] or ["  none"]
    lines += ["", "Outputs"]
    lines += [f"  {key:20} {path}" for key, path in result.outputs.items()]
    lines.append(f"  {'raw layer':20} {result.raw_dir}")
    unchanged = len(result.outputs) - len(result.files_written)
    if unchanged:
        lines.append(f"  ({unchanged} output file(s) already up to date and left untouched)")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    configure_stdout()
    parser = argparse.ArgumentParser(
        prog="python -m scholarpath_data",
        description="Load, normalize, validate and export scholarship records. Never modifies the source file "
        "and never marks a record verified without a reviewer decision.",
    )
    parser.add_argument("--input", "-i", help="Source .xlsx/.xlsm/.csv. If omitted, a single file in <output-dir>/raw or the current folder is used.")
    parser.add_argument("--output-dir", "-o", default="data", help="Root folder containing raw/, processed/, verified/, reports/ (default: ./data).")
    parser.add_argument("--sheet", action="append", help="Only process this sheet (repeatable). Default: every non-empty sheet.")
    parser.add_argument("--source-name", help="Label stored in source_name (default: the file name).")
    parser.add_argument("--source-type", choices=[t.value for t in SourceType], help="Stored in source_type (default: local_excel / local_csv).")
    parser.add_argument("--decisions", help=f"Reviewer decisions CSV (default: <output-dir>/verified/{DEFAULT_DECISIONS_NAME} if it exists).")
    parser.add_argument("--as-of", type=date.fromisoformat, metavar="YYYY-MM-DD", help="Date used for 'deadline passed' / 'outdated' checks (default: today).")
    parser.add_argument("--duplicate-threshold", type=float, default=DEFAULT_THRESHOLD, help=f"Name similarity (0-1) for possible duplicates (default {DEFAULT_THRESHOLD}).")
    parser.add_argument("--max-verification-age-days", type=int, default=DEFAULT_MAX_VERIFICATION_AGE_DAYS, help="Verified records older than this are flagged outdated.")
    parser.add_argument("--quiet", "-q", action="store_true", help="Only print the summary.")
    parser.add_argument("--debug", action="store_true", help="Show tracebacks for unexpected errors.")
    args = parser.parse_args(argv)
    if not 0 < args.duplicate_threshold <= 1:
        parser.error("--duplicate-threshold must be between 0 and 1")

    log = (lambda _m: None) if args.quiet else print
    try:
        result = run_pipeline(
            args.input,
            args.output_dir,
            sheets=args.sheet,
            source_name=args.source_name,
            source_type=SourceType(args.source_type) if args.source_type else None,
            decisions_path=args.decisions,
            as_of=args.as_of,
            duplicate_threshold=args.duplicate_threshold,
            max_verification_age_days=args.max_verification_age_days,
            log=log,
        )
    except ScholarPathError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except Exception as exc:  # noqa: BLE001 - last-resort message for the CLI
        if args.debug:
            traceback.print_exc()
        print(f"unexpected error: {type(exc).__name__}: {exc}\n  Re-run with --debug for the traceback.", file=sys.stderr)
        return 1
    print(format_summary(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
