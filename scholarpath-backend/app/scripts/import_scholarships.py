"""Import the ETL's cleaned scholarships into PostgreSQL.

    python -m app.scripts.import_scholarships --input "D:\\major\\scholarpath-data\\data\\processed\\scholarships_cleaned.json" --dry-run
    python -m app.scripts.import_scholarships --input "D:\\major\\scholarpath-data\\data\\processed\\scholarships_cleaned.json"

* ``--dry-run`` validates and reports only. It needs no database and never connects to one.
* A real run needs ``DATABASE_URL`` and the migrated schema (``alembic upgrade head``). It runs in one
  transaction and is safe to repeat: records are matched by their stable ETL ``scholarship_id``.
* The input file is only read. Nothing is ever deleted from the database.

Exit codes: 0 success, 3 imported but some records failed validation, 2 usage/input/configuration problem,
1 unexpected or database error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from sqlalchemy.exc import OperationalError, ProgrammingError, SQLAlchemyError

from app.core.config import get_settings
from app.db.session import DatabaseNotConfigured, engine_for
from app.services.importer.records import ImportInputError
from app.services.importer.runner import ImportReport, ImportPlan, plan_import, report_for_plan, run_import

NOT_CONFIGURED_HELP = (
    "No database is configured (DATABASE_URL is not set), so nothing can be imported yet.\n"
    "  * To only validate the file:  add --dry-run\n"
    "  * To import: see README.md > 'Configure PostgreSQL Later' (create the database, set DATABASE_URL in .env,\n"
    "    run `alembic upgrade head`), then run this command again."
)


def _print_report(report: ImportReport, header: str) -> None:
    print(header)
    print(f"  file               : {report.source_file} ({report.source_format}, sha256 {report.source_sha256[:12]}...)")
    print(f"  records read       : {report.records_read}")
    print(f"  valid              : {report.valid}")
    if report.dry_run:
        print(f"  would be imported  : {report.valid}  (inserted/updated/unchanged are unknown until a real run)")
    else:
        print(f"  inserted           : {report.inserted}")
        print(f"  updated            : {report.updated}")
        print(f"  unchanged          : {report.unchanged}")
    print(f"  skipped            : {report.skipped}")
    print(f"  failed             : {report.failed}")
    if report.absent_from_input is not None:
        print(f"  in DB, not in file : {report.absent_from_input}  (left untouched; nothing is deleted)")
    print(f"  verification status: {report.status_counts or '-'}")
    print(f"  possible-duplicate groups in file: {report.duplicate_groups_in_input}")
    if report.unmapped_columns:
        print(f"  unmapped columns   : {', '.join(report.unmapped_columns)} (kept in extra_attributes)")
    for label, items in (("skipped", report.skipped_details), ("failed", report.failed_details)):
        for issue in items[:20]:
            print(f"  [{label}] record #{issue.row} {issue.scholarship_id or '(no id)'}: {issue.reason}")
        if len(items) > 20:
            print(f"  [{label}] ... and {len(items) - 20} more (see --report-json)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.scripts.import_scholarships",
        description="Validate and import the ETL's cleaned scholarships (CSV or JSON). Never modifies the input file.",
    )
    parser.add_argument("--input", "-i", required=True, help="Path to scholarships_cleaned.csv or scholarships_cleaned.json")
    parser.add_argument("--dry-run", action="store_true", help="Validate and report only; no database needed, nothing written.")
    parser.add_argument("--include-errors", action="store_true", help="Also import records the ETL flagged with validation errors (default: skip them).")
    parser.add_argument("--report-json", help="Also write the full report (including every skipped/failed record) to this JSON file.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        plan: ImportPlan = plan_import(args.input, include_errors=args.include_errors)
    except ImportInputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        report = report_for_plan(plan, dry_run=True)
        _print_report(report, "DRY RUN - nothing was written and no database was contacted")
        _maybe_write_report(report, args.report_json)
        return 0 if not report.failed else 3

    try:
        engine = engine_for(get_settings())
    except DatabaseNotConfigured:
        print(f"error: {NOT_CONFIGURED_HELP}", file=sys.stderr)
        return 2
    try:
        report = run_import(engine, plan)
    except OperationalError as exc:
        print(f"error: could not connect to the database ({type(exc).__name__}). Check that PostgreSQL is running and DATABASE_URL is correct.", file=sys.stderr)
        return 1
    except ProgrammingError as exc:
        print(f"error: the database rejected the import ({type(exc).__name__}). Have the migrations been run? Try: alembic upgrade head", file=sys.stderr)
        return 1
    except SQLAlchemyError as exc:
        print(f"error: database error ({type(exc).__name__}); the transaction was rolled back and nothing was imported.", file=sys.stderr)
        return 1
    _print_report(report, "IMPORT COMPLETE (single transaction committed)")
    _maybe_write_report(report, args.report_json)
    return 0 if not report.failed else 3


def _maybe_write_report(report: ImportReport, path: str | None) -> None:
    if path:
        Path(path).write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
        print(f"  report written to {path}")


if __name__ == "__main__":
    raise SystemExit(main())
