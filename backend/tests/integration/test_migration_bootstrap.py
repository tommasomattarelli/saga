"""Production startup, lock ownership and frozen-profile adoption."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app import dependencies, main
from app.migrations.errors import (
    AlreadyVersionedError,
    MigrationLockTimeoutError,
    SchemaMismatchError,
)
from app.migrations.lock import LOCK_KEY, migration_transaction
from app.migrations.profiles import load_profile, require_profile_match
from tests.integration.migration_db import DisposableDatabase

CURRENT_COMMIT = "5e9206da28a0be1d8e669dcc72ed0af6a3525eac"
FROZEN_006_COMMIT = "261ad5fb53003844efbe1d8097d9393469686291"
USER_ID = "11111111-1111-1111-1111-111111111111"
CAMPAIGN_ID = "22222222-2222-2222-2222-222222222222"
TURN_ID = "33333333-3333-3333-3333-333333333333"
FACT_ID = "44444444-4444-4444-4444-444444444444"


async def _seed_user(database: DisposableDatabase) -> None:
    await database.execute(
        "INSERT INTO users (id, username, email, hashed_password, is_active, is_admin,"
        " preferred_language) VALUES (:id, 'adopted', 'adopted@example.com', 'pw',"
        " true, false, 'en')",
        {"id": USER_ID},
    )


async def _seed_current_campaign(database: DisposableDatabase) -> None:
    await database.execute(
        "INSERT INTO campaigns (id, user_id, world_slug, name, status, difficulty, turn_number,"
        " character_data, world_state, quests) VALUES (:id, :user, 'world', 'Campaign',"
        " 'ACTIVE', 'MEDIUM', 0, '{}'::jsonb, '{}'::jsonb, '{}'::jsonb)",
        {"id": CAMPAIGN_ID, "user": USER_ID},
    )


async def _seed_frozen_006_rows(database: DisposableDatabase) -> None:
    await _seed_user(database)
    await _seed_current_campaign(database)
    vector = "[" + ",".join(["0.125"] * 384) + "]"
    await database.execute(
        "INSERT INTO turns (id, campaign_id, turn_number, player_action, narration, model_used,"
        " summary, embedding, importance_score, summarization_failed)"
        " VALUES (:id, :campaign, 1, 'hit', 'fled', 'test-model', 'The goblin fled.',"
        " (:embedding)::vector, 5, false)",
        {"id": TURN_ID, "campaign": CAMPAIGN_ID, "embedding": vector},
    )
    await database.execute(
        "INSERT INTO memory_facts (id, campaign_id, turn_number, entity_name, entity_type,"
        " content, embedding) VALUES (:id, :campaign, 1, 'Goblin', 'npc', 'The goblin fled.',"
        " (:embedding)::vector)",
        {"id": FACT_ID, "campaign": CAMPAIGN_ID, "embedding": vector},
    )


def _short_timeout_config(tmp_path: Path) -> Path:
    path = tmp_path / "saga.config.yaml"
    path.write_text("migrations:\n  lock_timeout_seconds: 0.15\n", encoding="utf-8")
    return path


@pytest.mark.parametrize("command", ["upgrade", "downgrade", "stamp", "ensure_version"])
async def test_direct_alembic_mutations_share_bounded_lock(command: str, tmp_path: Path) -> None:
    async with DisposableDatabase() as database:
        if command != "ensure_version":
            await database.upgrade("007_embedding_index")
        timeout_config = _short_timeout_config(tmp_path)
        args = {
            "upgrade": ("upgrade", "head"),
            "downgrade": ("downgrade", "-1"),
            "stamp": ("stamp", "007_embedding_index"),
            "ensure_version": ("ensure_version",),
        }[command]
        async with database.hold_lock():
            result = await database.run_alembic(*args, config_path=timeout_config)
        output = result.stdout + result.stderr
        assert result.returncode != 0
        assert "migration lock was not acquired" in output
        assert "saga_test" not in output
        if command == "upgrade":
            assert await database.version() == "007_embedding_index"

        if command == "upgrade":
            await database.upgrade()
            assert await database.version() == "008_schema_reconciliation"
        elif command == "ensure_version":
            assert not await database.table_exists("alembic_version")
            result = await database.run_alembic("ensure_version")
            assert result.returncode == 0, result.stdout + result.stderr
            assert await database.table_exists("alembic_version")


async def test_unversioned_stamp_has_no_validation_bypass() -> None:
    async with DisposableDatabase() as database:
        result = await database.run_alembic("stamp", "head")
        assert result.returncode != 0
        assert "direct stamp is disabled" in (result.stdout + result.stderr)
        assert await database.version() is None


async def test_startup_serializes_concurrent_upgrades_and_rechecks_head() -> None:
    async with DisposableDatabase() as database:
        await asyncio.gather(
            database.upgrade_via_app(),
            database.upgrade_via_app(),
        )
        assert await database.version() == "008_schema_reconciliation"
        require_profile_match(load_profile("current_post_pr1"), await database.snapshot())


async def test_lock_timeout_and_cancellation_do_not_leak_session_locks() -> None:
    async with DisposableDatabase() as database:
        async with database.hold_lock():
            with pytest.raises(MigrationLockTimeoutError):
                await database.upgrade_via_app(lock_timeout_seconds=0.15)
        await database.upgrade_via_app()
        assert await database.version() == "008_schema_reconciliation"

    async with DisposableDatabase() as database:
        engine = create_async_engine(database.url, poolclass=NullPool)
        entered = asyncio.Event()

        async def cancelled_migration() -> None:
            async with (
                engine.connect() as connection,
                migration_transaction(connection, lock_timeout_seconds=2),
            ):
                entered.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(cancelled_migration())
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        try:
            async with engine.connect() as connection, connection.begin():
                acquired = await connection.scalar(
                    text("SELECT pg_try_advisory_lock(:high, :low)"),
                    {"high": LOCK_KEY[0], "low": LOCK_KEY[1]},
                )
                assert acquired is True
                await connection.execute(
                    text("SELECT pg_advisory_unlock(:high, :low)"),
                    {"high": LOCK_KEY[0], "low": LOCK_KEY[1]},
                )
        finally:
            await engine.dispose()


async def _run_lifespan(
    monkeypatch: pytest.MonkeyPatch,
    database: DisposableDatabase,
    events: list[str],
) -> None:
    monkeypatch.setattr(dependencies, "engine", database._engine())
    monkeypatch.setattr(main, "validate_generation_config", lambda: None)
    monkeypatch.setattr(main, "validate_embedding_config", lambda: None)
    original_init = main.init_db

    async def run_migrations() -> None:
        await original_init()
        events.append("migration")

    async def recover() -> None:
        events.append("recovery")

    async def stop_worker() -> None:
        return None

    monkeypatch.setattr(main, "init_db", run_migrations)
    monkeypatch.setattr(main, "recover_interrupted_rebuilds", recover)
    monkeypatch.setattr(main, "start_embedding_worker", lambda: events.append("worker"))
    monkeypatch.setattr(main, "stop_embedding_worker", stop_worker)
    async with main.app.router.lifespan_context(main.app):
        pass


async def test_application_lifespan_migrates_before_recovery_and_workers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with DisposableDatabase() as database:
        events: list[str] = []
        await _run_lifespan(monkeypatch, database, events)
        assert events == ["migration", "recovery", "worker"]
        assert await database.version() == "008_schema_reconciliation"


async def test_current_schema_adoption_preserves_rows_and_converges() -> None:
    async with DisposableDatabase() as database:
        await database.build_frozen_schema(CURRENT_COMMIT)
        await _seed_user(database)
        await _seed_current_campaign(database)
        await database.adopt("current_post_pr1")
        assert await database.version() == "007_embedding_index"
        assert (await database.fetch_one("SELECT name FROM campaigns"))[0] == "Campaign"
        with pytest.raises(AlreadyVersionedError):
            await database.adopt("current_post_pr1")

        await database.upgrade_via_app()
        assert await database.version() == "008_schema_reconciliation"
        require_profile_match(load_profile("current_post_pr1"), await database.snapshot())


async def test_frozen_006_adoption_runs_real_007_backfill_and_converges() -> None:
    async with DisposableDatabase() as database:
        await database.build_frozen_schema(FROZEN_006_COMMIT)
        await _seed_frozen_006_rows(database)
        await database.adopt("frozen_006")
        assert await database.version() == "006_user_provider_settings"
        await database.upgrade()

        index = await database.fetch_one(
            "SELECT pipeline_version, dimension FROM embedding_indexes WHERE campaign_id = :id",
            {"id": CAMPAIGN_ID},
        )
        assert (index[0], index[1]) == ("embed-v1-legacy", 384)
        assert (await database.fetch_one("SELECT count(*) FROM source_embeddings"))[0] == 2
        assert (await database.fetch_one("SELECT count(*) FROM turns"))[0] == 1
        assert (await database.fetch_one("SELECT count(*) FROM memory_facts"))[0] == 1
        require_profile_match(load_profile("current_post_pr1"), await database.snapshot())


async def test_adoption_mismatch_leaves_versioning_untouched() -> None:
    async with DisposableDatabase() as database:
        await database.build_frozen_schema(CURRENT_COMMIT)
        await database.execute("CREATE TABLE unexpected (id integer PRIMARY KEY)")
        with pytest.raises(SchemaMismatchError) as error:
            await database.adopt("current_post_pr1")
        assert "public.unexpected is unexpected" in str(error.value)
        assert await database.version() is None
        assert await database.table_exists("unexpected")


async def test_adoption_rejects_invalid_concurrent_index_without_repair() -> None:
    async with DisposableDatabase() as database:
        await database.build_frozen_schema(CURRENT_COMMIT)
        await database.execute("DROP INDEX ix_users_username")
        for index in range(2):
            await database.execute(
                "INSERT INTO users (id, username, email, hashed_password, is_active, is_admin,"
                " preferred_language) VALUES (gen_random_uuid(), 'duplicate', :email, 'pw',"
                " true, false, 'en')",
                {"email": f"duplicate{index}@example.com"},
            )
        with pytest.raises(DBAPIError):
            await database.execute_autocommit(
                "CREATE UNIQUE INDEX CONCURRENTLY ix_users_username ON users (username)"
            )

        with pytest.raises(SchemaMismatchError) as error:
            await database.adopt("current_post_pr1")
        assert "ix_users_username" in str(error.value)
        assert "valid" in str(error.value)
        assert await database.version() is None
        index = await database.fetch_one(
            "SELECT i.indisvalid, i.indisready, i.indislive FROM pg_index i "
            "JOIN pg_class c ON c.oid = i.indexrelid WHERE c.relname = 'ix_users_username'"
        )
        assert index == (False, False, True)


async def test_adoption_rejects_column_collation_drift() -> None:
    async with DisposableDatabase() as database:
        await database.build_frozen_schema(CURRENT_COMMIT)
        await database.execute(
            'ALTER TABLE users ALTER COLUMN username TYPE varchar(50) COLLATE "C"'
        )
        with pytest.raises(SchemaMismatchError) as error:
            await database.adopt("current_post_pr1")
        assert "users column.username" in str(error.value)
        assert "COLLATE" in str(error.value)
        assert await database.version() is None
