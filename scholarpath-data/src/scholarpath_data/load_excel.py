"""Discover, load and inspect scholarship spreadsheets (.xlsx / .xlsm / .csv).

This module never modifies the source file. It also writes the *raw layer*: a
verbatim, text-only snapshot of every sheet plus a manifest with the file's SHA-256.

Inspect a file (read-only)::

    python -m scholarpath_data.load_excel --input "path/to/scholarship.xlsx"
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import sys
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from scholarpath_data.console import configure_stdout, human_size
from scholarpath_data.errors import ScholarPathError, SourceError
from scholarpath_data.fileio import atomic_write_text
from scholarpath_data.parsers import clean_text

SUPPORTED_EXTENSIONS = (".xlsx", ".xlsm", ".csv")
Grid = list[list[Any]]


@dataclass
class SheetData:
    name: str
    header_row: int  # 1-based row number of the header in the source
    columns: list[str]  # header text as written (made unique if repeated)
    frame: pd.DataFrame  # object dtype, index = 1-based source row numbers
    blank_rows_skipped: int = 0


@dataclass
class LoadedSource:
    path: Path
    file_format: str  # 'xlsx' | 'csv'
    sha256: str
    size_bytes: int
    sheets: list[SheetData]
    empty_sheets: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def total_rows(self) -> int:
        return sum(len(sheet.frame) for sheet in self.sheets)


# --------------------------------------------------------------------------- #
# Path handling
# --------------------------------------------------------------------------- #


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_input_path(path: str | Path) -> Path:
    """Validate an input path and return it resolved; raise a clear SourceError otherwise."""
    candidate = Path(path).expanduser()
    if not candidate.exists():
        raise SourceError(
            f"Input file not found: {candidate}\n"
            "  Check the path; wrap it in quotes if it contains spaces."
        )
    if candidate.is_dir():
        raise SourceError(f"Input path is a folder, not a file: {candidate}")
    if candidate.suffix.lower() not in SUPPORTED_EXTENSIONS:
        hint = (
            " Open it in Excel and use Save As > .xlsx."
            if candidate.suffix.lower() in {".xls", ".ods"}
            else ""
        )
        raise SourceError(
            f"Unsupported file type '{candidate.suffix}' for {candidate.name}. "
            f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}.{hint}"
        )
    return candidate.resolve()


def discover_input_files(search_dirs: Sequence[Path]) -> list[Path]:
    """Top-level spreadsheet/CSV files in the given folders (non-recursive, no temp files)."""
    found: dict[Path, None] = {}
    for directory in search_dirs:
        if not Path(directory).is_dir():
            continue
        for item in sorted(Path(directory).iterdir()):
            if item.is_file() and item.suffix.lower() in SUPPORTED_EXTENSIONS and not item.name.startswith(("~$", ".")):
                found[item.resolve()] = None
    return list(found)


def resolve_input(input_arg: str | Path | None, search_dirs: Sequence[Path]) -> Path:
    if input_arg:
        return check_input_path(input_arg)
    candidates = discover_input_files(search_dirs)
    searched = ", ".join(str(d) for d in search_dirs)
    if not candidates:
        raise SourceError(
            f"No --input given and no .xlsx/.xlsm/.csv file found in: {searched}\n"
            "  Pass --input \"path/to/file.xlsx\"."
        )
    if len(candidates) > 1:
        listing = "\n".join(f"    {c}" for c in candidates)
        raise SourceError(f"Several candidate files found; choose one with --input:\n{listing}")
    return candidates[0]


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #


def _read_xlsx(path: Path) -> dict[str, Grid]:
    import openpyxl
    from openpyxl.utils.exceptions import InvalidFileException

    try:
        workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except PermissionError as exc:
        raise SourceError(f"Cannot open {path.name}: permission denied. Close it in Excel and retry.") from exc
    except (InvalidFileException, zipfile.BadZipFile, KeyError, OSError, ValueError) as exc:
        raise SourceError(
            f"Cannot read {path.name} as an Excel workbook ({type(exc).__name__}: {exc}). "
            "It may be corrupt, password-protected, or not really an .xlsx file."
        ) from exc
    try:
        return {ws.title: [list(row) for row in ws.iter_rows(values_only=True)] for ws in workbook.worksheets}
    except Exception as exc:  # openpyxl raises many types for malformed XML
        raise SourceError(f"Failed while reading sheets of {path.name}: {type(exc).__name__}: {exc}") from exc
    finally:
        workbook.close()


def _read_csv(path: Path) -> tuple[Grid, list[str]]:
    raw = path.read_bytes()
    notes: list[str] = []
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(encoding)
            if encoding != "utf-8-sig":
                notes.append(f"CSV is not UTF-8; decoded as {encoding}.")
            break
        except UnicodeDecodeError:
            continue
    else:
        raise SourceError(f"{path.name} is neither UTF-8 nor Windows-1252 text; re-save it as UTF-8 CSV.")
    first_line = next((line for line in text.splitlines() if line.strip()), "")
    delimiter = max((",", ";", "\t", "|"), key=first_line.count) if first_line else ","
    if first_line.count(delimiter) == 0:
        delimiter = ","
    try:
        grid = [list(row) for row in csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)]
    except csv.Error as exc:
        raise SourceError(f"{path.name} is not valid CSV: {exc}") from exc
    return grid, notes


def _is_blank(cell: Any) -> bool:
    return clean_text(cell) is None


def _unique(names: list[str], notes: list[str], sheet: str) -> list[str]:
    seen: Counter[str] = Counter()
    result: list[str] = []
    for name in names:
        seen[name.casefold()] += 1
        if seen[name.casefold()] > 1:
            unique = f"{name}__{seen[name.casefold()]}"
            notes.append(f"Sheet '{sheet}': repeated column header '{name}' renamed to '{unique}'.")
            result.append(unique)
        else:
            result.append(name)
    return result


def grid_to_sheet(name: str, grid: Grid, notes: list[str]) -> SheetData | None:
    """Turn a raw cell grid into a SheetData; ``None`` if the sheet holds no data at all."""
    counts = [sum(not _is_blank(cell) for cell in row) for row in grid]
    header_idx = next((i for i, c in enumerate(counts) if c >= 2), None)
    if header_idx is None:
        header_idx = next((i for i, c in enumerate(counts) if c >= 1), None)
    if header_idx is None:
        return None

    header_cells = grid[header_idx]
    data = [(i + 1, row) for i, row in enumerate(grid) if i > header_idx]
    width = max([len(header_cells)] + [len(row) for _, row in data])

    def cell(row: list[Any], j: int) -> Any:
        return row[j] if j < len(row) else None

    kept = [
        j for j in range(width)
        if not _is_blank(cell(header_cells, j)) or any(not _is_blank(cell(row, j)) for _, row in data)
    ]
    raw_names = [
        str(cell(header_cells, j)).strip() if not _is_blank(cell(header_cells, j)) else f"unnamed_{j + 1}"
        for j in kept
    ]
    columns = _unique(raw_names, notes, name)

    rows: list[list[Any]] = []
    index: list[int] = []
    blank = 0
    for row_number, row in data:
        values = [cell(row, j) for j in kept]
        if all(_is_blank(v) for v in values):
            blank += 1
            continue
        rows.append(values)
        index.append(row_number)
    frame = pd.DataFrame(rows, columns=columns, index=pd.Index(index, name="source_row"), dtype=object)
    return SheetData(name=name, header_row=header_idx + 1, columns=columns, frame=frame, blank_rows_skipped=blank)


def load_source(path: str | Path, sheets: Sequence[str] | None = None) -> LoadedSource:
    """Load every non-empty sheet (or only ``sheets``) without altering the file."""
    resolved = check_input_path(path)
    notes: list[str] = []
    try:
        sha, size = sha256_file(resolved), resolved.stat().st_size
    except PermissionError as exc:
        raise SourceError(f"Cannot read {resolved.name}: permission denied.") from exc

    if resolved.suffix.lower() == ".csv":
        grid, csv_notes = _read_csv(resolved)
        notes += csv_notes
        grids = {resolved.stem: grid}
        file_format = "csv"
    else:
        grids = _read_xlsx(resolved)
        file_format = "xlsx"

    if sheets:
        missing = [s for s in sheets if s not in grids]
        if missing:
            raise SourceError(
                f"Sheet(s) not found in {resolved.name}: {', '.join(missing)}. "
                f"Available: {', '.join(grids) or '(none)'}."
            )
        grids = {name: grids[name] for name in sheets}

    loaded: list[SheetData] = []
    empty: list[str] = []
    for name, grid in grids.items():
        sheet = grid_to_sheet(name, grid, notes)
        if sheet is None:
            empty.append(name)
        else:
            loaded.append(sheet)
    if not loaded:
        raise SourceError(f"{resolved.name} contains no data (all sheets are empty).")
    return LoadedSource(resolved, file_format, sha, size, loaded, empty, notes)


# --------------------------------------------------------------------------- #
# Raw layer
# --------------------------------------------------------------------------- #


def raw_cell_text(value: Any) -> str:
    """Verbatim text for a cell (no cleaning, no missing-value handling)."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat(sep=" ")
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", text).strip("_") or "sheet"


@dataclass
class RawSnapshot:
    directory: Path
    manifest_path: Path
    extracted_at: datetime  # when this exact file content was first extracted
    csv_files: dict[str, Path]


def write_raw_snapshot(source: LoadedSource, raw_root: Path, now: datetime | None = None) -> RawSnapshot:
    """Write the verbatim raw layer for this exact file version.

    Folder name = ``<file-stem>-<sha256[:8]>`` so (a) re-running on an unchanged file
    rewrites nothing, and (b) a changed file gets a new folder instead of overwriting
    the earlier raw data. ``extracted_at`` is kept from the first run on that content.
    """
    now = (now or datetime.now(timezone.utc)).replace(microsecond=0)
    directory = Path(raw_root) / f"{_slug(source.path.stem)}-{source.sha256[:8]}"
    manifest_path = directory / "manifest.json"

    extracted_at = now
    if manifest_path.is_file():
        try:
            previous = json.loads(manifest_path.read_text(encoding="utf-8"))
            if previous.get("sha256") == source.sha256:
                extracted_at = datetime.fromisoformat(previous["first_extracted_at"])
        except (ValueError, KeyError, OSError):
            pass  # unreadable manifest: treat as first extraction

    csv_files: dict[str, Path] = {}
    sheet_entries: list[dict[str, Any]] = []
    used: set[str] = set()
    for sheet in source.sheets:
        filename = f"{_slug(sheet.name)}.csv"
        while filename.casefold() in used:
            filename = f"{Path(filename).stem}_{len(used)}.csv"
        used.add(filename.casefold())

        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(["source_row", *sheet.columns])
        for row_number, values in zip(sheet.frame.index, sheet.frame.itertuples(index=False, name=None)):
            writer.writerow([row_number, *(raw_cell_text(v) for v in values)])
        csv_path = directory / filename
        atomic_write_text(csv_path, buffer.getvalue(), encoding="utf-8-sig")
        csv_files[sheet.name] = csv_path
        sheet_entries.append(
            {
                "sheet": sheet.name,
                "header_row": sheet.header_row,
                "columns": sheet.columns,
                "data_rows": len(sheet.frame),
                "blank_rows_skipped": sheet.blank_rows_skipped,
                "raw_csv": filename,
            }
        )

    manifest = {
        "source_file": source.path.name,
        "file_format": source.file_format,
        "sha256": source.sha256,
        "size_bytes": source.size_bytes,
        "first_extracted_at": extracted_at.isoformat(),
        "sheets": sheet_entries,
        "empty_sheets_skipped": source.empty_sheets,
        "notes": source.notes,
    }
    atomic_write_text(manifest_path, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    return RawSnapshot(directory, manifest_path, extracted_at, csv_files)


# --------------------------------------------------------------------------- #
# Inspection report
# --------------------------------------------------------------------------- #


def inspect_source(source: LoadedSource) -> dict[str, Any]:
    from scholarpath_data.normalize import map_columns, normalize_columns

    sheets: list[dict[str, Any]] = []
    for sheet in source.sheets:
        frame = sheet.frame
        columns = []
        for name in sheet.columns:
            series = frame[name]
            present = series.map(lambda v: not _is_blank(v))
            types = Counter(type(v).__name__ for v in series[present])
            samples = [str(v) for v in series[present].head(3)]
            columns.append(
                {
                    "name": name,
                    "missing": int((~present).sum()),
                    "distinct": int(series[present].map(raw_cell_text).nunique()),
                    "python_types": dict(types),
                    "samples": samples,
                }
            )
        normalized = normalize_columns(sheet.columns)
        mapping = map_columns(list(normalized.values()))
        reverse = {v: k for k, v in normalized.items()}
        sheets.append(
            {
                "sheet": sheet.name,
                "header_row": sheet.header_row,
                "data_rows": len(frame),
                "blank_rows_skipped": sheet.blank_rows_skipped,
                "exact_duplicate_rows": int(frame.astype(str).duplicated().sum()),
                "columns": columns,
                "column_mapping": {reverse[norm]: key for key, norm in mapping.by_key.items()},
                "unmapped_columns": [reverse[n] for n in mapping.extras],
            }
        )
    return {
        "file": source.path.name,
        "format": source.file_format,
        "size_bytes": source.size_bytes,
        "sha256": source.sha256,
        "sheets_loaded": [s.name for s in source.sheets],
        "sheets_empty_skipped": source.empty_sheets,
        "notes": source.notes,
        "sheets": sheets,
    }


def format_inspection(report: dict[str, Any]) -> str:
    out = [
        f"File   : {report['file']}  ({report['format']}, {human_size(report['size_bytes'])})",
        f"SHA-256: {report['sha256']}",
        f"Sheets : loaded {report['sheets_loaded']}; empty/skipped {report['sheets_empty_skipped'] or 'none'}",
    ]
    out += [f"Note   : {n}" for n in report["notes"]]
    for sheet in report["sheets"]:
        out += [
            "",
            f"=== Sheet '{sheet['sheet']}': {sheet['data_rows']} data rows, header on row {sheet['header_row']}, "
            f"{len(sheet['columns'])} columns, {sheet['exact_duplicate_rows']} exact duplicate rows, "
            f"{sheet['blank_rows_skipped']} blank rows skipped",
            f"{'column':28} {'missing':>7} {'distinct':>8}  {'maps to':26} types / sample",
        ]
        for col in sheet["columns"]:
            target = sheet["column_mapping"].get(col["name"], "(extra_attributes)")
            types = ",".join(f"{k}:{v}" for k, v in col["python_types"].items()) or "-"
            sample = (col["samples"][0][:40] + "...") if col["samples"] and len(col["samples"][0]) > 40 else (col["samples"][0] if col["samples"] else "")
            out.append(f"{col['name'][:28]:28} {col['missing']:>7} {col['distinct']:>8}  {target:26} {types} | {sample}")
    return "\n".join(out)


def main(argv: Sequence[str] | None = None) -> int:
    configure_stdout()
    parser = argparse.ArgumentParser(
        prog="python -m scholarpath_data.load_excel",
        description="Inspect a scholarship spreadsheet (read-only): sheets, columns, missing values, mapping.",
    )
    parser.add_argument("--input", "-i", help="Path to .xlsx/.xlsm/.csv. If omitted, looks in ./data/raw and the current folder.")
    parser.add_argument("--sheet", action="append", help="Only inspect this sheet (repeatable).")
    parser.add_argument("--json", action="store_true", help="Print the inspection report as JSON.")
    args = parser.parse_args(argv)
    try:
        path = resolve_input(args.input, [Path("data/raw"), Path.cwd()])
        report = inspect_source(load_source(path, args.sheet))
    except ScholarPathError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, ensure_ascii=False) if args.json else format_inspection(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
