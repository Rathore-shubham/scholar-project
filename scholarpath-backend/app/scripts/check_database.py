"""Check the database configuration step by step (read-only; never writes).

    python -m app.scripts.check_database

Exit code 0 only when PostgreSQL is reachable AND the migrations have been applied.
Never prints the connection URL, host or credentials.
"""

from __future__ import annotations

import sys
from typing import Sequence

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.db.session import DatabaseNotConfigured, engine_for


def main(_argv: Sequence[str] | None = None) -> int:
    settings = get_settings()
    try:
        engine = engine_for(settings)
    except DatabaseNotConfigured:
        print("[1/3] DATABASE_URL ........ NOT SET")
        print("      Copy .env.example to .env and fill in DATABASE_URL (README > 'Configure PostgreSQL Later').")
        return 2
    print("[1/3] DATABASE_URL ........ set (value not shown)")

    try:
        with engine.connect() as connection:
            version = connection.execute(text("SHOW server_version")).scalar_one()
    except SQLAlchemyError as exc:
        print(f"[2/3] Connection .......... FAILED ({type(exc).__name__})")
        print("      Check that the PostgreSQL service is running, and that the user, password, host, port and database in DATABASE_URL are right.")
        return 1
    print(f"[2/3] Connection .......... OK (PostgreSQL {version})")

    try:
        with engine.connect() as connection:
            revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
            tables = {
                row[0]
                for row in connection.execute(
                    text("SELECT table_name FROM information_schema.tables WHERE table_schema = current_schema()")
                )
            }
    except SQLAlchemyError:
        print("[3/3] Migrations .......... NOT APPLIED (no alembic_version table)")
        print("      Run: alembic upgrade head")
        return 1
    expected = {"scholarships", "scholarship_values", "scholarship_criteria", "import_runs"}
    missing = sorted(expected - tables)
    if missing:
        print(f"[3/3] Migrations .......... INCOMPLETE (revision {revision}; missing tables: {', '.join(missing)})")
        return 1
    print(f"[3/3] Migrations .......... OK (revision {revision}; tables present)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
