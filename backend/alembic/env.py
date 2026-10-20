"""Alembic environment configuration.

Every online mutation takes the same advisory lock and outer transaction used by
startup and adoption.  The external-connection branch is only for callers that
already own that transaction; env.py must never start Alembic recursively.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from alembic.util import CommandError
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import settings
from app.migrations.errors import MigrationError
from app.migrations.lock import configured_lock_timeout, migration_transaction
from app.migrations.state import (
    DatabaseState,
    guard_downgrade,
    guard_stamp,
    guard_upgrade,
    inspect_state,
)
from app.models import *  # noqa: F401, F403 - import all models for autogenerate
from app.models.base import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url.replace("%", "%%"))

if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
_MUTATING_COMMANDS = {"upgrade", "downgrade", "stamp", "ensure_version"}


def run_migrations_offline() -> None:
    """Generate SQL without a connection; online commands own locking."""
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
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def _direct_command() -> str | None:
    command = getattr(config.cmd_opts, "cmd", None)
    return getattr(command[0], "__name__", None) if command else None


def _guard_direct_command(command: str | None, state: DatabaseState) -> None:
    if command in (None, "upgrade"):
        guard_upgrade(state)
    elif command == "downgrade":
        guard_downgrade(state)
    elif command == "stamp":
        guard_stamp(state)


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    try:
        async with connectable.connect() as connection:
            command = _direct_command()
            if command not in _MUTATING_COMMANDS and command is not None:
                await connection.run_sync(do_run_migrations)
                return
            try:
                async with migration_transaction(
                    connection, lock_timeout_seconds=configured_lock_timeout(config)
                ):
                    state = await inspect_state(connection, config)
                    _guard_direct_command(command, state)
                    await connection.run_sync(do_run_migrations)
            except MigrationError as exc:
                raise CommandError(str(exc)) from None
    finally:
        await connectable.dispose()


def run_migrations_online() -> None:
    external = config.attributes.get("connection")
    if external is not None:
        if not isinstance(external, Connection):
            raise CommandError(
                "external migration connection must be a synchronous SQLAlchemy connection"
            )
        if not config.attributes.get("lock_already_held"):
            raise CommandError(
                "external migration connection requires an already-held migration transaction"
            )
        if not external.in_transaction():
            raise CommandError(
                "external migration connection must be inside the migration transaction"
            )
        do_run_migrations(external)
        return
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
