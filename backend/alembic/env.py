import asyncio
from logging.config import fileConfig

from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from app.core.config import get_settings
from app.core.database import Base
from app.models import *  # noqa: F401,F403
# Agents module models (always loaded so migrations stay in sync; the
# feature itself is gated at runtime by AGENTS_ENABLED).
from app.agents.models import *  # noqa: F401,F403

config = context.config
settings = get_settings()

config.set_main_option("sqlalchemy.url", settings.database_url)

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


def do_run_migrations(connection: Connection) -> None:
    # Acquire an advisory lock to prevent concurrent Alembic runs (e.g. multiple
    # pods starting at the same time).  The lock is automatically released when
    # the connection is closed.
    connection.execute(text("SELECT pg_advisory_lock(42)"))
    # Safety timeouts so a blocked migration doesn't hang forever.
    connection.execute(text("SET lock_timeout = '30s'"))
    connection.execute(text("SET statement_timeout = '300s'"))

    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()

    connection.execute(text("SELECT pg_advisory_unlock(42)"))
    # The advisory-lock statement above autobegins a transaction that Alembic then treats as
    # "outer" and never commits; without this the whole upgrade is rolled back on close.
    connection.commit()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
