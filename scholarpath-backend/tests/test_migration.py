"""The initial Alembic migration, verified WITHOUT any database.

* It generates valid PostgreSQL SQL in Alembic's offline mode.
* Its tables, columns, defaults, constraints and indexes match the DDL SQLAlchemy generates for PostgreSQL from
  the models (so migration and models cannot drift apart unnoticed).
* It never reads DATABASE_URL when only printing SQL, and refuses to run online without one.

These tests do NOT show that the migration has run on a real PostgreSQL server - that still needs a configured
database (README: "Configure PostgreSQL Later").
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

import app.models  # noqa: F401
from app.core.config import Settings
from app.db.base import Base

BACKEND_DIR = Path(__file__).resolve().parents[1]


def alembic_config() -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("path_separator", "os")
    cfg.set_main_option("prepend_sys_path", str(BACKEND_DIR))
    return cfg


def offline_sql(*, downgrade: bool = False) -> str:
    cfg = alembic_config()
    cfg.output_buffer = io.StringIO()
    if downgrade:
        command.downgrade(cfg, "0001_initial_schema:base", sql=True)
    else:
        command.upgrade(cfg, "head", sql=True)
    return cfg.output_buffer.getvalue()


def _normalize(line: str) -> str:
    return " ".join(line.strip().rstrip(",").split())


def tables_from_sql(sql: str) -> dict[str, set[str]]:
    """table name -> set of normalized column/constraint definition lines."""
    found = {}
    for match in re.finditer(r"CREATE TABLE (\w+) \(\s*\n(.*?)\n\)", sql, re.DOTALL):
        found[match.group(1)] = {_normalize(line) for line in match.group(2).splitlines() if line.strip()}
    return found


def indexes_from_sql(sql: str) -> set[str]:
    return {" ".join(m.group(0).split()).rstrip(";") for m in re.finditer(r"CREATE (?:UNIQUE )?INDEX [^;]+;", sql)}


def metadata_ddl() -> str:
    pg = postgresql.dialect()
    parts = []
    for table in Base.metadata.sorted_tables:
        parts.append(str(CreateTable(table).compile(dialect=pg)))
        parts.extend(str(CreateIndex(index).compile(dialect=pg)) + ";" for index in sorted(table.indexes, key=lambda i: i.name))
    return "\n".join(parts)


def test_single_linear_head() -> None:
    script = ScriptDirectory.from_config(alembic_config())
    assert script.get_heads() == ["0001_initial_schema"]
    assert [r.revision for r in script.walk_revisions()] == ["0001_initial_schema"]


def test_upgrade_generates_postgresql_sql_for_every_table() -> None:
    sql = offline_sql()
    assert "BEGIN;" in sql and "COMMIT;" in sql
    for table in ("import_runs", "scholarships", "scholarship_values", "scholarship_criteria"):
        assert f"CREATE TABLE {table} (" in sql
    assert "JSONB" in sql and "BIGSERIAL" in sql and "TIMESTAMP WITH TIME ZONE" in sql
    assert "INSERT INTO alembic_version" in sql


def test_migration_tables_match_the_models_exactly() -> None:
    from_migration, from_models = tables_from_sql(offline_sql()), tables_from_sql(metadata_ddl())
    from_migration.pop("alembic_version")  # Alembic's own bookkeeping table, not a model
    assert set(from_migration) == set(from_models) == set(Base.metadata.tables)
    for table in from_models:
        assert from_migration[table] == from_models[table], (
            f"{table}: only in migration {sorted(from_migration[table] - from_models[table])}; "
            f"only in models {sorted(from_models[table] - from_migration[table])}"
        )


def test_migration_indexes_match_the_models() -> None:
    from_migration, from_models = indexes_from_sql(offline_sql()), indexes_from_sql(metadata_ddl())
    assert from_models and from_migration == from_models


def test_constraint_names_are_not_double_prefixed() -> None:
    sql = offline_sql()
    assert "ck_import_runs_ck_" not in sql and not re.search(r"ck_(\w+)_ck_", sql)
    names = re.findall(r"CONSTRAINT (\w+)", sql)
    assert len(names) == len(set(names)), "constraint names must be unique"


def test_downgrade_drops_everything_in_dependency_order() -> None:
    sql = offline_sql(downgrade=True)
    order = [sql.index(f"DROP TABLE {t}") for t in ("scholarship_criteria", "scholarship_values", "scholarships", "import_runs")]
    assert order == sorted(order)


def test_printing_sql_never_needs_or_reads_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://nobody:topsecret@unreachable.invalid:5432/none")
    sql = offline_sql()
    assert "topsecret" not in sql and "unreachable.invalid" not in sql and "CREATE TABLE scholarships" in sql


def test_online_run_without_database_url_stops_with_guidance(monkeypatch: pytest.MonkeyPatch) -> None:
    # make sure a developer's real configuration can never be picked up (or used) by this test
    monkeypatch.setattr("app.core.config.get_settings", lambda: Settings(_env_file=None))
    with pytest.raises(SystemExit) as exc:
        command.upgrade(alembic_config(), "head")
    assert "DATABASE_URL is not set" in str(exc.value) and "--sql" in str(exc.value)
