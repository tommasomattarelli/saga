"""One advisory-lock/transaction protocol for every online migration mutation.

The lock is session-scoped so it survives Alembic's per-run commits.  The outer
transaction is owned here, before the lock query, so cleanup never issues SQL
from inside a transaction context that has already been rolled back.  If
cleanup cannot complete the connection is invalidated: a pooled session must
never return while still holding the migration lock.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config_loader import load_saga_config
from app.migrations.errors import (
    MigrationConfigurationError,
    MigrationError,
    MigrationLockTimeoutError,
)

LOCK_KEY = (0x53414741, 1)  # "SAGA", slot 1
DEFAULT_LOCK_TIMEOUT_SECONDS = 30.0


def configured_lock_timeout(config: Config | None = None) -> float:
    raw: object | None = None
    if config is not None:
        raw = config.attributes.get("lock_timeout_seconds")
    if raw is None:
        try:
            migration_config = load_saga_config().get("migrations", {})
        except FileNotFoundError:
            migration_config = {}
        if not isinstance(migration_config, dict):
            raise MigrationConfigurationError("migrations must be a configuration mapping")
        raw = migration_config.get("lock_timeout_seconds", DEFAULT_LOCK_TIMEOUT_SECONDS)
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        raise MigrationConfigurationError(
            "migrations.lock_timeout_seconds must be a finite number"
        )
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise MigrationConfigurationError(
            "migrations.lock_timeout_seconds must be a finite number"
        ) from exc
    if not math.isfinite(value) or value <= 0:
        raise MigrationConfigurationError(
            "migrations.lock_timeout_seconds must be positive and finite"
        )
    return value


async def _acquire_lock(connection: AsyncConnection, timeout: float) -> None:
    milliseconds = max(1, int(timeout * 1000))
    await connection.execute(
        text("SELECT set_config('lock_timeout', :value, true)"), {"value": f"{milliseconds}ms"}
    )
    try:
        await connection.execute(
            text("SELECT pg_advisory_lock(:high, :low)"),
            {"high": LOCK_KEY[0], "low": LOCK_KEY[1]},
        )
    except DBAPIError as exc:
        if getattr(exc.orig, "sqlstate", None) == "55P03":
            raise MigrationLockTimeoutError(
                f"database migration lock was not acquired within {timeout:g}s"
            ) from None
        raise


async def _release_lock(connection: AsyncConnection) -> None:
    if connection.in_transaction():
        await connection.rollback()
    await connection.execute(
        text("SELECT pg_advisory_unlock(:high, :low)"),
        {"high": LOCK_KEY[0], "low": LOCK_KEY[1]},
    )
    await connection.commit()


@asynccontextmanager
async def migration_transaction(
    connection: AsyncConnection, *, lock_timeout_seconds: float | None = None
) -> AsyncIterator[None]:
    if connection.in_transaction():
        raise MigrationError(
            "migration transaction requires a connection with no active transaction"
        )
    timeout = (
        lock_timeout_seconds if lock_timeout_seconds is not None else configured_lock_timeout()
    )
    if not math.isfinite(timeout) or timeout <= 0:
        raise MigrationConfigurationError("migration lock timeout must be finite and positive")
    acquired = False
    body_failed = False
    try:
        async with connection.begin():
            await _acquire_lock(connection, timeout)
            acquired = True
            yield
    except BaseException:
        body_failed = True
        raise
    finally:
        if acquired:
            cleanup = asyncio.create_task(_release_lock(connection))
            try:
                await asyncio.shield(cleanup)
            except BaseException:
                try:
                    await connection.invalidate()
                except Exception:
                    pass
                if not body_failed:
                    raise
