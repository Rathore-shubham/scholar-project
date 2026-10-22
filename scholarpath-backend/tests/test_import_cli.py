"""The importer's command line: dry run, refusal without a database, exit codes, report file."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.models import Scholarship
from app.scripts import import_scholarships as cli
from tests.support import etl_record, memory_engine, write_csv, write_json


@pytest.fixture()
def good_file(tmp_path: Path) -> Path:
    return write_json(tmp_path / "ok.json", [etl_record(scholarship_id="SP-C1"), etl_record(scholarship_id="SP-C2", scholarship_name="Second (test fixture)")])


@pytest.fixture()
def mixed_file(tmp_path: Path) -> Path:
    return write_json(tmp_path / "mixed.json", [etl_record(scholarship_id="SP-C1"), etl_record(scholarship_id="SP-BAD", minimum_percentage=500)])


def test_dry_run_needs_no_database_and_writes_nothing(good_file: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*_a, **_k):
        raise AssertionError("a dry run must not touch the database layer")

    monkeypatch.setattr(cli, "engine_for", forbidden)
    monkeypatch.setattr(cli, "run_import", forbidden)
    assert cli.main(["--input", str(good_file), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "no database was contacted" in out
    assert "records read       : 2" in out and "would be imported  : 2" in out and "failed             : 0" in out


def test_dry_run_reports_failures_and_exits_3(mixed_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--input", str(mixed_file), "--dry-run"]) == 3
    out = capsys.readouterr().out
    assert "failed             : 1" in out and "[failed] record #2 SP-BAD" in out and "minimum_percentage" in out


def test_report_json_is_written_with_every_detail(mixed_file: Path, tmp_path: Path) -> None:
    target = tmp_path / "report.json"
    cli.main(["--input", str(mixed_file), "--dry-run", "--report-json", str(target)])
    report = json.loads(target.read_text(encoding="utf-8"))
    assert report["dry_run"] is True and report["records_read"] == 2 and report["failed"] == 1
    assert report["failed_details"][0]["scholarship_id"] == "SP-BAD" and len(report["source_sha256"]) == 64


def test_real_run_without_a_configured_database_refuses_with_guidance(good_file: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--input", str(good_file)]) == 2
    err = capsys.readouterr().err
    assert "DATABASE_URL is not set" in err and "--dry-run" in err and "Configure PostgreSQL Later" in err


@pytest.mark.parametrize("argv_builder, message", [
    (lambda tmp: ["--input", str(tmp / "missing.json")], "not found"),
    (lambda tmp: ["--input", str(tmp / "notes.txt")], "Unsupported input type"),
])
def test_bad_input_paths_exit_2_with_a_clear_message(tmp_path: Path, capsys: pytest.CaptureFixture[str], argv_builder, message: str) -> None:
    (tmp_path / "notes.txt").write_text("x")
    assert cli.main(argv_builder(tmp_path)) == 2
    assert message in capsys.readouterr().err


def test_missing_input_argument_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 2


def test_real_run_branch_imports_and_is_repeatable(good_file: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    engine = memory_engine()  # stands in for PostgreSQL: this exercises the CLI's real-run code path only
    monkeypatch.setattr(cli, "engine_for", lambda _settings: engine)
    assert cli.main(["--input", str(good_file)]) == 0
    first = capsys.readouterr().out
    assert "IMPORT COMPLETE" in first and "inserted           : 2" in first
    assert cli.main(["--input", str(good_file)]) == 0
    second = capsys.readouterr().out
    assert "inserted           : 0" in second and "unchanged          : 2" in second
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(Scholarship)) == 2


def test_partial_failure_still_imports_valid_records_and_exits_3(mixed_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = memory_engine()
    monkeypatch.setattr(cli, "engine_for", lambda _settings: engine)
    assert cli.main(["--input", str(mixed_file)]) == 3
    with Session(engine) as s:
        assert [r.scholarship_id for r in s.scalars(select(Scholarship))] == ["SP-C1"]


def test_connection_problem_exits_1_without_leaking_details(good_file: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "engine_for", lambda _settings: object())

    def boom(_engine, _plan):
        raise OperationalError("SELECT 1", {}, Exception("could not connect to secret-host as leaky_user"))

    monkeypatch.setattr(cli, "run_import", boom)
    assert cli.main(["--input", str(good_file)]) == 1
    err = capsys.readouterr().err
    assert "could not connect" in err and "secret-host" not in err and "leaky_user" not in err


def test_missing_tables_point_to_the_migrations(good_file: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "engine_for", lambda _settings: object())

    def boom(_engine, _plan):
        raise ProgrammingError("INSERT ...", {}, Exception('relation "scholarships" does not exist'))

    monkeypatch.setattr(cli, "run_import", boom)
    assert cli.main(["--input", str(good_file)]) == 1
    assert "alembic upgrade head" in capsys.readouterr().err


def test_csv_input_works_through_the_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write_csv(tmp_path / "ok.csv", [etl_record()])
    assert cli.main(["--input", str(path), "--dry-run"]) == 0
    assert "(csv," in capsys.readouterr().out


def test_cli_never_modifies_the_input_file(good_file: Path) -> None:
    before = (good_file.read_bytes(), good_file.stat().st_mtime_ns)
    cli.main(["--input", str(good_file), "--dry-run"])
    assert (good_file.read_bytes(), good_file.stat().st_mtime_ns) == before
