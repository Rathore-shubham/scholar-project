"""End-to-end behavior: counts, outputs, source preservation, reruns, CLI exit codes."""

from __future__ import annotations

import csv
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from conftest import make_row, write_csv, write_xlsx
from scholarpath_data.errors import OutputError, SourceError
from scholarpath_data.load_excel import sha256_file
from scholarpath_data.pipeline import main, output_paths, run_pipeline
from scholarpath_data.schema import VerificationStatus
from scholarpath_data.verification import DECISION_COLUMNS

AS_OF = date(2026, 6, 1)
T0 = datetime(2026, 6, 1, 8, 0, 0, tzinfo=timezone.utc)


def rows_for_pipeline() -> list[dict[str, Any]]:
    return [
        make_row(),  # clean-ish
        make_row(**{"Scholarship Name": "Beta State Scholarship", "government_level": "MP", "eligible_states": "MP",
                    "max_family_income": "<8,00,000", "amount": 50000, "min_percentage": 60, "provider": "Dept of Higher Education"}),
        make_row(**{"Scholarship Name": "Gamma Girls Scholarship", "gender": "FEMALE", "amount": "GIRLS - 3,000 ; BOYS - 2,500",
                    "min_percentage": "MP BOARD-60", "official_url": "https://a.gov.in (Portal) / https://b.nic.in"}),
        make_row(**{"Scholarship Name": "Delta Scholarship", "official_url": "scholarships.gov.in", "min_percentage": 150}),  # 2 errors
        make_row(**{"Scholarship Name": "Post Matric Scholarship for SC Students", "provider": "Social Welfare"}),
        make_row(**{"Scholarship Name": "Post Matric Scholarship for ST Students", "provider": "Tribal Affairs"}),  # similar -> group
        make_row(**{"Scholarship Name": "Epsilon", "provider": "Epsilon", "application_open_date": "2026-09-01", "deadline": "2026-08-01"}),  # provider copies name + deadline error
    ]


@pytest.fixture()
def source(tmp_path: Path) -> Path:
    folder = tmp_path / "src"
    folder.mkdir()
    return write_xlsx(folder / "scholarships.xlsx", rows_for_pipeline())


def run(source: Path, out: Path, **kw: Any):
    return run_pipeline(source, out, as_of=AS_OF, now=T0, **kw)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


# ----------------------------------------------------------------- outputs & counts
def test_all_output_files_are_created_with_expected_names(source: Path, tmp_path: Path) -> None:
    out = tmp_path / "data"
    result = run(source, out)
    for key, name in {"cleaned_csv": "processed/scholarships_cleaned.csv", "cleaned_json": "processed/scholarships_cleaned.json",
                      "quality_report": "reports/data_quality_report.json", "possible_duplicates": "reports/possible_duplicates.csv",
                      "verified_csv": "verified/scholarships_verified.csv"}.items():
        assert result.outputs[key] == out / name and (out / name).is_file()
    assert (result.raw_dir / "manifest.json").is_file() and (result.raw_dir / "Sheet1.csv").is_file()


def test_counts_are_computed_from_the_actual_data(source: Path, tmp_path: Path) -> None:
    result = run(source, tmp_path / "data")
    c = result.counts
    records = json.loads(result.outputs["cleaned_json"].read_text(encoding="utf-8"))["records"]
    report = json.loads(result.outputs["quality_report"].read_text(encoding="utf-8"))
    assert report["counts"] == c

    assert c["total_input_records"] == c["successfully_parsed_records"] == len(records) == 7
    assert c["records_failed_to_parse"] == 0
    assert c["records_with_validation_errors"] == sum(r["validation_status"] == "error" for r in records) == 2
    assert c["records_with_warnings"] == sum(any(i["severity"] == "warning" for i in e["issues"]) for e in report["records_needing_attention"])
    assert c["possible_duplicate_groups"] == len({r["duplicate_group_id"] for r in records if r["duplicate_group_id"]}) == 1
    assert c["records_marked_verified"] == 0
    assert c["records_pending_review"] == 7
    assert sum(report["verification_status_counts"].values()) == 7


def test_counts_change_when_the_data_changes(tmp_path: Path) -> None:
    src = write_xlsx(tmp_path / "a.xlsx", rows_for_pipeline()[:2])
    assert run(src, tmp_path / "o1").counts["total_input_records"] == 2
    src2 = write_xlsx(tmp_path / "b.xlsx", rows_for_pipeline())
    assert run(src2, tmp_path / "o2").counts["total_input_records"] == 7


def test_errors_and_warnings_are_reported_per_record_and_per_code(source: Path, tmp_path: Path) -> None:
    result = run(source, tmp_path / "data")
    summary = result.report["issue_summary"]
    assert summary["invalid_url"]["severity"] == "error"
    assert summary["percentage_out_of_range"]["severity"] == "error"
    assert summary["deadline_before_open_date"]["severity"] == "error"
    assert summary["percentage_not_numeric"]["severity"] == "warning"
    assert summary["provider_copies_scheme_name"]["records"] == 1
    flagged = {e["scholarship_name"]: e for e in result.report["records_needing_attention"]}
    delta_codes = {i["code"] for i in flagged["Delta Scholarship"]["issues"]}
    assert {"invalid_url", "percentage_out_of_range"} <= delta_codes
    assert flagged["Delta Scholarship"]["source_row"] == 5 and flagged["Delta Scholarship"]["validation_status"] == "error"


def test_field_completeness_distinguishes_missing_from_present(source: Path, tmp_path: Path) -> None:
    comp = run(source, tmp_path / "data").report["field_completeness"]
    assert comp["scholarship_name"]["missing"] == 0
    assert comp["academic_year"]["present"] == 0 and comp["academic_year"]["percent_present"] == 0.0
    assert comp["maximum_family_income"]["present"] == 1  # only Beta has an unambiguous income


def test_nothing_is_verified_by_running_the_pipeline(source: Path, tmp_path: Path) -> None:
    result = run(source, tmp_path / "data")
    assert all(r.verification_status is VerificationStatus.PENDING for r in result.records)
    assert read_csv(result.outputs["verified_csv"]) == []


def test_duplicates_are_reported_but_no_record_is_removed(source: Path, tmp_path: Path) -> None:
    result = run(source, tmp_path / "data")
    dupes = read_csv(result.outputs["possible_duplicates"])
    assert {d["scholarship_name"] for d in dupes} == {"Post Matric Scholarship for SC Students", "Post Matric Scholarship for ST Students"}
    assert {d["source_row"] for d in dupes} == {"6", "7"}
    assert len(result.records) == 7


def test_source_row_and_provenance_are_kept(source: Path, tmp_path: Path) -> None:
    rows = read_csv(run(source, tmp_path / "data").outputs["cleaned_csv"])
    assert [r["source_row"] for r in rows] == ["2", "3", "4", "5", "6", "7", "8"]
    assert {r["source_file"] for r in rows} == {"scholarships.xlsx"} and {r["source_type"] for r in rows} == {"local_excel"}
    assert all(r["extracted_at"] == "2026-06-01T08:00:00Z" for r in rows)


# ----------------------------------------------------------------- original files & reruns
def test_original_source_file_is_unchanged(source: Path, tmp_path: Path) -> None:
    before, mtime = sha256_file(source), source.stat().st_mtime_ns
    run(source, tmp_path / "data")
    run(source, tmp_path / "data")
    assert sha256_file(source) == before and source.stat().st_mtime_ns == mtime
    assert sorted(p.name for p in source.parent.iterdir()) == ["scholarships.xlsx"]  # nothing written next to it


def test_raw_layer_keeps_original_text_separate_from_cleaned_output(source: Path, tmp_path: Path) -> None:
    result = run(source, tmp_path / "data")
    raw = (result.raw_dir / "Sheet1.csv").read_text(encoding="utf-8-sig")
    assert "<8,00,000" in raw and "GIRLS - 3,000 ; BOYS - 2,500" in raw and "scholarships.gov.in" in raw
    cleaned = result.outputs["cleaned_csv"].read_text(encoding="utf-8-sig")
    assert "<8,00,000" not in cleaned and "GIRLS - 3,000" in cleaned  # tier text only survives as quoted raw in extra/amount text


def snapshot(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_rerun_is_idempotent_no_new_files_no_changed_outputs(source: Path, tmp_path: Path) -> None:
    out = tmp_path / "data"
    first = run(source, out)
    before = snapshot(out)
    second = run_pipeline(source, out, as_of=AS_OF, now=T0 + timedelta(days=3))  # a later run
    after = snapshot(out)
    assert set(before) == set(after)  # no duplicate outputs
    changed = {k for k in before if before[k] != after[k]}
    assert changed == {"reports/data_quality_report.json"}  # only the report's generated_at moves
    a, b = first.report, second.report
    a["generated_at"] = b["generated_at"] = ""
    assert a == b
    assert len(second.records) == len(first.records) == 7  # no duplicated records
    assert second.files_written == [out / "reports" / "data_quality_report.json"]


def test_rerun_with_a_later_clock_keeps_first_extraction_time(source: Path, tmp_path: Path) -> None:
    out = tmp_path / "data"
    run(source, out)
    later = run_pipeline(source, out, as_of=AS_OF, now=T0 + timedelta(days=30))
    assert {r.extracted_at for r in later.records} == {T0}


def test_changed_source_creates_new_raw_snapshot_and_refreshes_outputs(source: Path, tmp_path: Path) -> None:
    out = tmp_path / "data"
    first = run(source, out)
    write_xlsx(source, rows_for_pipeline()[:3])  # user edits the file
    second = run_pipeline(source, out, as_of=AS_OF, now=T0 + timedelta(days=1))
    assert first.raw_dir != second.raw_dir and first.raw_dir.is_dir()  # old raw layer is kept
    assert len(read_csv(second.outputs["cleaned_csv"])) == 3
    assert {r.extracted_at for r in second.records} == {T0 + timedelta(days=1)}


# ----------------------------------------------------------------- verification workflow
def write_decisions(path: Path, *rows: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(DECISION_COLUMNS)
        writer.writerows(rows)
    return path


def test_decisions_file_in_verified_folder_is_picked_up_automatically(source: Path, tmp_path: Path) -> None:
    out = tmp_path / "data"
    first = run(source, out)
    clean_id = next(r.scholarship_id for r in first.records if r.scholarship_name == "Alpha Merit Scholarship")
    error_id = next(r.scholarship_id for r in first.records if r.scholarship_name == "Delta Scholarship")
    write_decisions(out / "verified" / "verification_decisions.csv",
                    [clean_id, "verified", "Reviewer A", "2026-05-30", "https://scholarships.gov.in/x", "matches NSP page"],
                    [error_id, "verified", "Reviewer A", "2026-05-30", "https://scholarships.gov.in/x", ""],
                    ["SP-NOPE", "verified", "Reviewer A", "2026-05-30", "https://scholarships.gov.in/x", ""])
    result = run(source, out)
    assert result.counts["records_marked_verified"] == 1 and result.counts["records_pending_review"] == 6
    verified = read_csv(result.outputs["verified_csv"])
    assert [v["scholarship_id"] for v in verified] == [clean_id] and verified[0]["last_verified_at"] == "2026-05-30"
    decisions = result.report["verification_decisions"]
    assert [a["scholarship_id"] for a in decisions["applied"]] == [clean_id]
    assert [r["scholarship_id"] for r in decisions["refused"]] == [error_id]
    assert decisions["unmatched_scholarship_ids"] == ["SP-NOPE"]
    by_id = {r.scholarship_id: r for r in result.records}
    assert by_id[error_id].verification_status is VerificationStatus.PENDING
    assert "verified_without_evidence" not in by_id[clean_id].validation_issue_codes
    assert run(source, out).counts == result.counts  # deterministic on rerun


def test_explicit_missing_decisions_file_is_an_error(source: Path, tmp_path: Path) -> None:
    with pytest.raises(SourceError, match="Decisions file not found"):
        run(source, tmp_path / "data", decisions_path=tmp_path / "nope.csv")


# ----------------------------------------------------------------- sources & guards
def test_csv_input_and_source_name_override(tmp_path: Path) -> None:
    src = write_csv(tmp_path / "list.csv", rows_for_pipeline()[:2])
    result = run(src, tmp_path / "data", source_name="NSP export")
    assert result.counts["total_input_records"] == 2
    assert {r.source_name for r in result.records} == {"NSP export"} and {r.source_type.value for r in result.records} == {"local_csv"}


def test_multiple_sheets_are_combined_with_sheet_names_kept(tmp_path: Path) -> None:
    src = write_xlsx(tmp_path / "m.xlsx", rows_for_pipeline()[:2])
    import openpyxl
    wb = openpyxl.load_workbook(src)
    ws = wb.create_sheet("Second")
    ws.append(["Scholarship Name", "provider"])
    ws.append(["Zulu Fund", "Zulu Trust"])
    wb.save(src)
    result = run(src, tmp_path / "data")
    assert result.counts["total_input_records"] == 3
    assert {r.source_sheet for r in result.records} == {"Sheet1", "Second"}
    assert len(list(result.raw_dir.glob("*.csv"))) == 2


def test_input_that_is_one_of_the_outputs_is_refused(source: Path, tmp_path: Path) -> None:
    out = tmp_path / "data"
    run(source, out)
    with pytest.raises(OutputError, match="pipeline's own output"):
        run(output_paths(out)["cleaned_csv"], out)


def test_header_only_file_is_rejected(tmp_path: Path) -> None:
    src = write_xlsx(tmp_path / "h.xlsx", [])
    with pytest.raises(SourceError, match="no data rows"):
        run(src, tmp_path / "data")


def test_input_is_discovered_from_raw_folder_when_not_given(tmp_path: Path) -> None:
    out = tmp_path / "data"
    (out / "raw").mkdir(parents=True)
    write_xlsx(out / "raw" / "only.xlsx", rows_for_pipeline()[:1])
    result = run_pipeline(None, out, as_of=AS_OF, now=T0)
    assert result.counts["total_input_records"] == 1 and result.records[0].source_file == "only.xlsx"


# ----------------------------------------------------------------- CLI
def test_cli_success_prints_summary_and_returns_zero(source: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--input", str(source), "--output-dir", str(tmp_path / "data"), "--as-of", "2026-06-01"])
    out = capsys.readouterr().out
    assert code == 0
    assert "total input records" in out and ": 7" in out and "records marked verified" in out and "possible duplicate groups" in out


def test_cli_missing_file_is_a_clean_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--input", str(tmp_path / "missing.xlsx"), "--output-dir", str(tmp_path / "data")])
    captured = capsys.readouterr()
    assert code == 2 and "error: Input file not found" in captured.err and "Traceback" not in captured.err


def test_cli_unsupported_and_corrupt_files_are_clean_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    txt = tmp_path / "x.txt"
    txt.write_text("hi")
    assert main(["--input", str(txt), "-o", str(tmp_path / "d")]) == 2
    assert "Unsupported file type" in capsys.readouterr().err
    bad = tmp_path / "bad.xlsx"
    bad.write_bytes(b"nope")
    assert main(["--input", str(bad), "-o", str(tmp_path / "d")]) == 2
    assert "Cannot read bad.xlsx" in capsys.readouterr().err


def test_cli_rejects_bad_threshold(source: Path, tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--input", str(source), "-o", str(tmp_path / "d"), "--duplicate-threshold", "2"])
    assert exc.value.code == 2


def test_inspect_cli_is_read_only(source: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from scholarpath_data.load_excel import main as inspect_main

    before = sha256_file(source)
    assert inspect_main(["--input", str(source)]) == 0
    text = capsys.readouterr().out
    assert "Sheet 'Sheet1': 7 data rows" in text and "scholarship_name" in text and sha256_file(source) == before
    assert inspect_main(["--input", str(source.parent / "no.xlsx")]) == 2
