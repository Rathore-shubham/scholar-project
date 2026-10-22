"""Deterministic CSV / JSON exports.

Representation rules (same in CSV and JSON so the two always agree):
    * dates      -> ISO 'YYYY-MM-DD'; datetimes -> ISO 8601 UTC ('...Z')
    * missing    -> JSON null / empty CSV cell
    * lists/dicts-> native in JSON; JSON text in CSV (e.g. ["SC","ST"]), so they round-trip
    * numbers    -> integral values print as integers (12000, not 12000.0)
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from scholarpath_data.fileio import atomic_write_text
from scholarpath_data.schema import ALL_FIELDS, ScholarshipRecord, VerificationStatus

SCHEMA_VERSION = "1"


def _tidy(value: Any) -> Any:
    """Make floats that are whole numbers into ints (recursively)."""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, list):
        return [_tidy(v) for v in value]
    if isinstance(value, dict):
        return {k: _tidy(v) for k, v in value.items()}
    return value


def record_to_dict(record: ScholarshipRecord) -> dict[str, Any]:
    """JSON-ready dict with the canonical column order."""
    data = record.model_dump(mode="json")
    return {name: _tidy(data[name]) for name in ALL_FIELDS}


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def rows_to_csv_text(rows: Sequence[Mapping[str, Any]], columns: Sequence[str]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_csv_cell(row.get(column)) for column in columns])
    return buffer.getvalue()


def write_records_csv(records: Sequence[ScholarshipRecord], path: Path) -> bool:
    text = rows_to_csv_text([record_to_dict(r) for r in records], ALL_FIELDS)
    return atomic_write_text(path, text, encoding="utf-8-sig")  # BOM so Excel shows the rupee sign


def write_records_json(records: Sequence[ScholarshipRecord], path: Path) -> bool:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "record_count": len(records),
        "records": [record_to_dict(r) for r in records],
    }
    return atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def write_verified_csv(records: Sequence[ScholarshipRecord], path: Path) -> bool:
    """Only records a reviewer verified (header-only file when there are none yet)."""
    verified = [r for r in records if r.verification_status is VerificationStatus.VERIFIED]
    return write_records_csv(verified, path)


def write_dict_rows_csv(rows: Sequence[Mapping[str, Any]], columns: Sequence[str], path: Path) -> bool:
    return atomic_write_text(path, rows_to_csv_text(rows, columns), encoding="utf-8-sig")


def write_json(payload: Any, path: Path) -> bool:
    return atomic_write_text(path, json.dumps(_tidy(payload), indent=2, ensure_ascii=False, allow_nan=False) + "\n")
