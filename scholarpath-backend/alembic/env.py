"""Alembic environment.

* Online mode (``alembic upgrade head``) connects with ``DATABASE_URL`` from the environment / ``.env``.
* Offline mode (``alembic upgrade head --sql``) needs NO database and does not read ``DATABASE_URL``;
  it just prints the PostgreSQL SQL, which is how the migration can be reviewed before any database exists.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.core.config import get_settings
from app.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata
OFFLINE_DIALECT_URL = "postgresql+psycopg://"


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url") or OFFLINE_DIALECT_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = config.get_main_option("sqlalchemy.url")
    if not url:
        settings = get_settings()
        if settings.database_url is None:
            raise SystemExit(
                "DATABASE_URL is not set, so there is no database to migrate.\n"
                "Configure it in .env first (see README 'Configure PostgreSQL Later'), or run with --sql to "
                "only print the SQL."
            )
        url = settings.database_url.get_secret_value()
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
