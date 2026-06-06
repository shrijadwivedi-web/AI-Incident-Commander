"""Alembic environment configuration for AI Incident Commander.

This module is the entry-point for all Alembic migration operations.  It
is responsible for:

1. Bootstrapping sys.path so that the *shared* Python package is importable.
2. Importing the SQLAlchemy ``Base`` metadata so that ``--autogenerate`` can
   diff the live database schema against the ORM model definitions.
3. Providing both *offline* (SQL script) and *online* (live connection) migration
   execution paths as required by Alembic.

Design decisions
----------------
* ``DATABASE_URL`` is read from the ``DATABASE_URL`` environment variable first,
  then falls back to the value in ``config.settings`` so that CI/CD pipelines
  can override it without touching the codebase.
* ``include_schemas = False`` — we use a single schema (``public``) which is the
  default for PostgreSQL.
* ``compare_type = True`` — Alembic will detect column type changes between
  revisions, preventing silent drift.
* ``compare_server_default = True`` — ensures server-side defaults (e.g.
  ``func.now()``) are also compared.
"""

from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# ---------------------------------------------------------------------------
# sys.path bootstrap
# ---------------------------------------------------------------------------
# Alembic runs from the *script_location* directory (migrations/).  We need
# the parent of that directory (shared/python/) on the path so that
# `from common.domain.models import Base` works correctly.
_HERE = Path(__file__).resolve().parent          # shared/python/migrations/
_SHARED_PYTHON = _HERE.parent                    # shared/python/
if str(_SHARED_PYTHON) not in sys.path:
    sys.path.insert(0, str(_SHARED_PYTHON))

# ---------------------------------------------------------------------------
# Import application metadata
# ---------------------------------------------------------------------------
# All SQLAlchemy model modules *must* be imported before Base.metadata is
# passed to Alembic, otherwise autogenerate won't see the tables.
from common.domain.models import Base  # noqa: E402  (import after sys.path patch)

target_metadata = Base.metadata

# ---------------------------------------------------------------------------
# Alembic config
# ---------------------------------------------------------------------------
config = context.config

# Override sqlalchemy.url with the env-var value if present.
# This allows docker-compose / CI to inject the real DSN without code changes.
_db_url = os.environ.get("DATABASE_URL")
if _db_url:
    config.set_main_option("sqlalchemy.url", _db_url)
elif not config.get_main_option("sqlalchemy.url", fallback=None):
    # Fall back to the pydantic settings default (useful for local dev)
    from config.settings import get_settings  # noqa: E402
    config.set_main_option("sqlalchemy.url", get_settings().database_url)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# ---------------------------------------------------------------------------
# Migration helpers
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """Run migrations in *offline* mode (emits SQL to stdout / file).

    This is useful for generating migration scripts for review before applying
    them to a production database.
    """
    url = config.get_main_option("sqlalchemy.url")
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
    """Run migrations in *online* mode against a live database connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
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
