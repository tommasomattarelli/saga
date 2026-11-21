from tests.integration.migrations.migration_db import HEAD_REVISION, DisposableDatabase
from tests.integration.migrations.test_migration_chain import _insert_campaign, _insert_user

USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
CAMPAIGN_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
TURN_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"


async def test_012_upgrade_preserves_legacy_turn_without_inventing_operations() -> None:
    async with DisposableDatabase() as database:
        await database.upgrade("012_memory_jobs")
        await _insert_user(database, USER_ID)
        await _insert_campaign(
            database,
            campaign_id=CAMPAIGN_ID,
            user_id=USER_ID,
            world_slug="legacy-world",
            difficulty="MEDIUM",
        )
        await database.execute(
            "INSERT INTO turns (id, campaign_id, turn_number, player_action, narration, model_used,"
            " importance_score, summarization_failed)"
            " VALUES (:id, :campaign, 1, 'Open the door.', 'The door opens.', 'legacy-model', 5,"
            " false)",
            {"id": TURN_ID, "campaign": CAMPAIGN_ID},
        )

        await database.upgrade(HEAD_REVISION)

        assert await database.fetch_one(
            "SELECT player_action, narration, operations_version, operation_count"
            " FROM turns WHERE id = :id",
            {"id": TURN_ID},
        ) == ("Open the door.", "The door opens.", None, None)
        assert await database.fetch_one("SELECT count(*) FROM turn_operations") == (0,)


async def test_empty_upgrade_matches_models_and_downgrade_round_trips() -> None:
    async with DisposableDatabase() as database:
        await database.upgrade(HEAD_REVISION)
        await database.require_model_schema()
        await database.downgrade("012_memory_jobs")
        assert not await database.table_exists("turn_operations")
        await database.upgrade(HEAD_REVISION)
        await database.require_model_schema()


async def test_downgrade_refuses_recorded_zero_operation_turn() -> None:
    async with DisposableDatabase() as database:
        await database.upgrade(HEAD_REVISION)
        await _insert_user(database, USER_ID)
        await _insert_campaign(
            database,
            campaign_id=CAMPAIGN_ID,
            user_id=USER_ID,
            world_slug="legacy-world",
            difficulty="MEDIUM",
        )
        await database.execute(
            "INSERT INTO turns (id, campaign_id, turn_number, player_action, narration, model_used,"
            " importance_score, summarization_failed, operations_version, operation_count)"
            " VALUES (:id, :campaign, 1, 'Wait.', 'Nothing.', 'model', 5, false, 1, 0)",
            {"id": TURN_ID, "campaign": CAMPAIGN_ID},
        )

        result = await database.run_alembic("downgrade", "012_memory_jobs")

        assert result.returncode != 0
        assert "Cannot discard recorded turn operation sources." in result.stdout + result.stderr
        assert await database.version() == HEAD_REVISION
        assert await database.fetch_one(
            "SELECT operations_version, operation_count FROM turns WHERE id = :id",
            {"id": TURN_ID},
        ) == (1, 0)
