"""The check_database command, tested with fake engines (never a real server)."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.scripts import check_database as cmd
from tests.conftest import make_settings


def test_not_configured_exits_2_with_guidance(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cmd, "get_settings", lambda: make_settings())
    assert cmd.main() == 2
    out = capsys.readouterr().out
    assert "NOT SET" in out and ".env.example" in out


def test_unreachable_database_exits_1_without_leaking_credentials(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    settings = make_settings(database_url="postgresql+psycopg://leaky_user:hunter2@127.0.0.1:1/leaky_db", db_connect_timeout_seconds=1)
    monkeypatch.setattr(cmd, "get_settings", lambda: settings)
    assert cmd.main() == 1
    out = capsys.readouterr().out
    assert "FAILED (OperationalError)" in out and "service is running" in out
    for leaked in ("hunter2", "leaky_user", "leaky_db", "127.0.0.1"):
        assert leaked not in out


class _Engine:
    """Minimal engine double driven by a list of scripted results."""

    def __init__(self, results: list[object]) -> None:
        self.results = results

    def connect(self):
        results = self.results

        class _Conn:
            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return False

            def execute(self_inner, statement):  # noqa: ANN001
                value = results.pop(0)
                if isinstance(value, Exception):
                    raise value

                class _R:
                    def scalar_one(self_r):
                        return value

                    def scalar(self_r):
                        return value

                    def __iter__(self_r):
                        return iter(value)

                return _R()

        return _Conn()


def run_with(monkeypatch: pytest.MonkeyPatch, results: list[object]) -> int:
    monkeypatch.setattr(cmd, "get_settings", lambda: make_settings(database_url="postgresql+psycopg://u:p@h/db"))
    monkeypatch.setattr(cmd, "engine_for", lambda _s: _Engine(results))
    return cmd.main()


def test_connected_but_not_migrated(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    code = run_with(monkeypatch, ["18.4", OperationalError("SELECT", {}, Exception("no such table"))])
    out = capsys.readouterr().out
    assert code == 1 and "Connection .......... OK (PostgreSQL 18.4)" in out and "NOT APPLIED" in out and "alembic upgrade head" in out


def test_partially_migrated(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    code = run_with(monkeypatch, ["18.4", "0001_initial_schema", [("scholarships",), ("alembic_version",)]])
    out = capsys.readouterr().out
    assert code == 1 and "INCOMPLETE" in out and "scholarship_criteria" in out


def test_fully_ready(capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    tables = [(t,) for t in ("scholarships", "scholarship_values", "scholarship_criteria", "import_runs", "alembic_version")]
    code = run_with(monkeypatch, ["18.4", "0001_initial_schema", tables])
    out = capsys.readouterr().out
    assert code == 0 and "Migrations .......... OK (revision 0001_initial_schema" in out


def test_sqlite_engine_is_irrelevant_but_text_is_importable() -> None:
    # guards against accidental removal of the sqlalchemy.text import used by the command
    assert create_engine("sqlite://").connect().execute(text("SELECT 1")).scalar() == 1
