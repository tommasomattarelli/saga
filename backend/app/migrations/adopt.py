"""Validated adoption for the two frozen unversioned schema profiles.

This is the only path that may stamp a database without running the migration
chain.  It never repairs, converts or drops anything: the complete catalog must
match a committed profile exactly, otherwise the transaction rolls back without
creating alembic_version.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from alembic import command
from alembic.util import CommandError
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from app.migrations.config import alembic_config
from app.migrations.errors import (
    AlreadyVersionedError,
    MigrationConfigurationError,
    MigrationError,
)
from app.migrations.introspect import introspect_connection
from app.migrations.lock import migration_transaction
from app.migrations.profiles import PROFILE_IDS, load_profile, require_profile_match
from app.migrations.state import inspect_state


def _stamp_sync(connection: Connection, target: str) -> None:
    config = alembic_config(connection=connection, lock_already_held=True)
    command.stamp(config, target)


async def adopt_unversioned_database(profile_id: str, engine: AsyncEngine | None = None) -> None:
    from app import dependencies

    profile = load_profile(profile_id)
    target = str(profile["target_revision"])
    active_engine = engine if engine is not None else dependencies.engine
    async with active_engine.connect() as connection, migration_transaction(connection):
        config = alembic_config()
        state = await inspect_state(connection, config)
        if state.revisions:
            raise AlreadyVersionedError(
                "database already has an alembic revision; adoption only applies to "
                "unversioned databases"
            )
        if target not in state.known_revisions:
            raise MigrationConfigurationError(
                f"profile {profile_id!r} targets unknown revision {target!r}"
            )
        snapshot = await connection.run_sync(introspect_connection)
        require_profile_match(profile, snapshot)
        try:
            await connection.run_sync(lambda sync_connection: _stamp_sync(sync_connection, target))
        except CommandError as exc:
            raise MigrationError(str(exc)) from None


def main() -> None:
    parser = argparse.ArgumentParser(description="Adopt a frozen unversioned SAGA schema")
    parser.add_argument("--profile", required=True, choices=PROFILE_IDS)
    args = parser.parse_args()
    try:
        asyncio.run(adopt_unversioned_database(args.profile))
    except MigrationError as exc:
        print(f"adoption refused: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
