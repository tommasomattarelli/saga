from uuid import UUID, uuid4

import pytest
from eval.memory_capture import capture_campaign
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from tests.integration.migrations.migration_db import DisposableDatabase
from tests.integration.migrations.test_migration_chain import _insert_campaign, _insert_user


def _engine(database: DisposableDatabase) -> AsyncEngine:
    assert database.engine is not None
    return database.engine


async def _seed(database: DisposableDatabase, *, duplicate: bool = False) -> tuple[str, str]:
    user_id, campaign_id = str(uuid4()), str(uuid4())
    await _insert_user(database, user_id)
    await _insert_campaign(
        database,
        campaign_id=campaign_id,
        user_id=user_id,
        world_slug="legacy-world",
        difficulty="MEDIUM",
    )
    await database.execute(
        "INSERT INTO turns (id, campaign_id, turn_number, player_action, narration, model_used,"
        " importance_score, summarization_failed) VALUES (:id, :campaign, 1, 'Wait.', '', 'model',"
        " 5, false)",
        {"id": str(uuid4()), "campaign": campaign_id},
    )
    if duplicate:
        await database.execute(
            "INSERT INTO turns (id, campaign_id, turn_number, player_action, narration, model_used,"
            " importance_score, summarization_failed) VALUES (:id, :campaign, 1, 'Again.', 'Text',"
            " 'model', 5, false)",
            {"id": str(uuid4()), "campaign": campaign_id},
        )
    await database.execute(
        "UPDATE campaigns SET turn_number = 1 WHERE id = :id", {"id": campaign_id}
    )
    return campaign_id, user_id


async def test_009_capture_requires_read_only_repeatable_read_and_preserves_legacy_source() -> (
    None
):
    async with DisposableDatabase() as database:
        await database.run_alembic("upgrade", "009_campaign_language")
        campaign_id, _ = await _seed(database)
        async with _engine(database).connect() as connection, connection.begin():
            await connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            async with AsyncSession(bind=connection) as session:
                captured = await capture_campaign(session, UUID(campaign_id))
        assert captured.language == "en"
        assert len(captured.turns) == 1
        assert captured.turns[0].narration == ""
        assert captured.turns[0].operations is None


async def test_009_capture_rejects_ambiguous_display_numbers() -> None:
    async with DisposableDatabase() as database:
        await database.run_alembic("upgrade", "009_campaign_language")
        campaign_id, _ = await _seed(database, duplicate=True)
        async with _engine(database).connect() as connection, connection.begin():
            await connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            async with AsyncSession(bind=connection) as session:
                with pytest.raises(ValueError, match="duplicate display turn numbers"):
                    await capture_campaign(session, UUID(campaign_id))


async def test_capture_rejects_default_read_write_session() -> None:
    async with DisposableDatabase() as database:
        await database.run_alembic("upgrade", "009_campaign_language")
        campaign_id, _ = await _seed(database)
        async with AsyncSession(bind=_engine(database)) as session, session.begin():
            with pytest.raises(RuntimeError, match="READ ONLY"):
                await capture_campaign(session, UUID(campaign_id))


async def test_current_history_schema_is_rejected() -> None:
    async with DisposableDatabase() as database:
        await database.upgrade()
        async with _engine(database).connect() as connection, connection.begin():
            await connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            async with AsyncSession(bind=connection) as session:
                with pytest.raises(RuntimeError, match="History-aware campaign capture"):
                    await capture_campaign(session, uuid4())


async def test_legacy_restore_cannot_silently_include_a_stored_future() -> None:
    async with DisposableDatabase() as database:
        await database.run_alembic("upgrade", "009_campaign_language")
        campaign_id, _ = await _seed(database)
        await database.execute(
            "UPDATE campaigns SET turn_number = 0 WHERE id = :id", {"id": campaign_id}
        )
        async with _engine(database).connect() as connection, connection.begin():
            await connection.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            async with AsyncSession(bind=connection) as session:
                with pytest.raises(ValueError, match="stored future"):
                    await capture_campaign(session, UUID(campaign_id))
