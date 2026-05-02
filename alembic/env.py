"""Alembic environment.

Loads the project's SQLAlchemy metadata and uses settings.DATABASE_URL so
migrations always target the same DB the app does.
"""
from __future__ import with_statement

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool
from alembic import context

# Make `api` importable when alembic is run from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.config import settings  # noqa: E402
from api.models.database import Base  # noqa: E402

# Import all model modules so Base.metadata is fully populated.
from api.models import (  # noqa: F401,E402
    customer,
    order,
    venue,
    itinerary,
    content,
    analytics_event,
    promo_code,
    social,
)

config = context.config
config.set_main_option(
    "sqlalchemy.url",
    os.environ.get("DATABASE_URL", settings.DATABASE_URL),
)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
