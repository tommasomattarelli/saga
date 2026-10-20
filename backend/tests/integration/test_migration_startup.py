"""Startup schema refusal and credential-safe online configuration."""

import pytest

from app.config import settings
from app.migrations.errors import UnknownRevisionError, UnversionedSchemaError
from tests.integration.migration_db import DisposableDatabase


async def test_startup_refuses_unversioned_and_unknown_schemas() -> None:
    async with DisposableDatabase() as database:
        await database.execute("CREATE TABLE unexpected (id integer PRIMARY KEY)")
        with pytest.raises(UnversionedSchemaError):
            await database.upgrade_via_app()
        assert await database.version() is None

    async with DisposableDatabase() as database:
        await database.upgrade()
        await database.execute("UPDATE alembic_version SET version_num = '999_future'")
        with pytest.raises(UnknownRevisionError):
            await database.upgrade_via_app()
        assert await database.version() == "999_future"
        result = await database.run_alembic("stamp", "head")
        assert result.returncode != 0
        assert "direct stamp is disabled" in (result.stdout + result.stderr)
        assert await database.version() == "999_future"


async def test_startup_refuses_enum_only_unversioned_schema_atomically() -> None:
    async with DisposableDatabase() as database:
        await database.execute("CREATE TYPE campaignstatus AS ENUM ('BROKEN')")
        with pytest.raises(UnversionedSchemaError):
            await database.upgrade_via_app()
        assert await database.version() is None
        assert not await database.table_exists("users")
        assert await database.fetch_all(
            "SELECT enumlabel FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid "
            "WHERE t.typname = 'campaignstatus' ORDER BY e.enumsortorder"
        ) == [("BROKEN",)]


async def test_injected_startup_accepts_percent_encoded_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with DisposableDatabase() as database:
        monkeypatch.setattr(
            settings,
            "database_url",
            "postgresql+asyncpg://saga:pa%40ss@localhost/saga",
        )
        await database.upgrade_via_app()
        assert await database.version() == "008_schema_reconciliation"


async def test_direct_alembic_accepts_percent_encoded_test_password() -> None:
    async with DisposableDatabase() as database:
        encoded_url = database.url.replace("saga_test:saga_test@", "saga_test:%73aga_test@")
        result = await database.run_alembic("upgrade", "head", database_url=encoded_url)
        assert result.returncode == 0, result.stdout + result.stderr
        assert await database.version() == "008_schema_reconciliation"


async def test_direct_alembic_error_does_not_expose_encoded_credentials() -> None:
    async with DisposableDatabase() as database:
        encoded_url = database.url.replace("saga_test:saga_test@", "saga_test:fake%40secret@")
        result = await database.run_alembic("upgrade", "head", database_url=encoded_url)
        output = result.stdout + result.stderr
        assert result.returncode != 0
        assert "fake%40secret" not in output
        assert "fake@secret" not in output
        assert encoded_url not in output
