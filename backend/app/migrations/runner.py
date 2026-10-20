"""Startup migration runner: lock, inspect, then upgrade through Alembic."""

from __future__ import annotations

from alembic import command
from alembic.util import CommandError
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from app.migrations.config import alembic_config
from app.migrations.errors import MigrationError
from app.migrations.lock import migration_transaction
from app.migrations.state import guard_upgrade, inspect_state


def _upgrade_sync(connection: Connection) -> None:
    config = alembic_config(connection=connection, lock_already_held=True)
    command.upgrade(config, "head")


async def upgrade_database(
    engine: AsyncEngine | None = None, *, lock_timeout_seconds: float | None = None
) -> None:
    from app import dependencies

    active_engine = engine if engine is not None else dependencies.engine
    async with (
        active_engine.connect() as connection,
        migration_transaction(connection, lock_timeout_seconds=lock_timeout_seconds),
    ):
        config = alembic_config()
        state = await inspect_state(connection, config)
        guard_upgrade(state)
        if not state.needs_upgrade:
            return
        try:
            await connection.run_sync(_upgrade_sync)
        except CommandError as exc:
            raise MigrationError(str(exc)) from None
