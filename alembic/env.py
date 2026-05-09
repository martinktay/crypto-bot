import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import settings
from app.models import entities  # noqa: F401
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Prefer an explicit shell `DATABASE_URL`, then the same value the app loads from `.env`
# via `Settings` (Alembic does not load `.env` on its own). Finally use `alembic.ini`.
_env_db_url = os.environ.get("DATABASE_URL") or settings.database_url
if _env_db_url:
    # Normalise bare `postgres://`/`postgresql://` to the psycopg v3 driver, since
    # this project only installs psycopg[binary] (not psycopg2-binary). Neon copy
    # buttons hand out `postgresql://...` by default, which would otherwise crash.
    if _env_db_url.startswith("postgres://"):
        _env_db_url = "postgresql+psycopg://" + _env_db_url[len("postgres://"):]
    elif _env_db_url.startswith("postgresql://"):
        _env_db_url = "postgresql+psycopg://" + _env_db_url[len("postgresql://"):]
    config.set_main_option("sqlalchemy.url", _env_db_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)

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
