"""Alembic env.py for Modern-Banking-App."""

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# make project root importable so we can import config and models
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# this reads alembic.ini
config = context.config

# Prefer SQLALCHEMY_DATABASE_URI from your app config or DATABASE_URL env var
try:
    from config import Config  # noqa: E402

    if getattr(Config, "SQLALCHEMY_DATABASE_URI", None):
        config.set_main_option("sqlalchemy.url", Config.SQLALCHEMY_DATABASE_URI)
except Exception:
    # fall back to alembic.ini / env var
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        config.set_main_option("sqlalchemy.url", db_url)

# set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# import your models metadata
from models import db  # noqa: E402

target_metadata = db.metadata


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
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
