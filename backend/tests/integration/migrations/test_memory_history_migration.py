from tests.integration.migrations.migration_db import HEAD_REVISION, DisposableDatabase
from tests.integration.migrations.test_migration_chain import _insert_campaign, _insert_user

USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
CAMPAIGN_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
TURN_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
FACT_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
SAVE_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"


async def _public_tables(database: DisposableDatabase) -> set[str]:
    rows = await database.fetch_all("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    return {str(row[0]) for row in rows}


async def _seed_legacy_rows(database: DisposableDatabase) -> None:
    await _insert_user(database, USER_ID)
    await _insert_campaign(
        database,
        campaign_id=CAMPAIGN_ID,
        user_id=USER_ID,
        turn_number=1,
        world_slug="legacy-world",
        difficulty="MEDIUM",
        global_summary="A legacy summary.",
    )
    await database.execute(
        "INSERT INTO turns (id, campaign_id, turn_number, player_action, narration, model_used,"
        " summary, importance_score, summarization_failed)"
        " VALUES (:id, :campaign, 1, 'Find the gate.', 'The gate opens.', 'legacy-model',"
        " 'A legacy turn summary.', 5, false)",
        {"id": TURN_ID, "campaign": CAMPAIGN_ID},
    )
    await database.execute(
        "INSERT INTO memory_facts (id, campaign_id, turn_number, entity_name, entity_type,"
        " content) VALUES (:id, :campaign, 1, 'Mira', 'npc', 'Mira opened the gate.')",
        {"id": FACT_ID, "campaign": CAMPAIGN_ID},
    )
    await database.execute(
        "INSERT INTO saves (id, campaign_id, name, turn_number, scene_summary, is_auto,"
        " campaign_snapshot) VALUES (:id, :campaign, 'Legacy save', 1, 'Before migration',"
        " false, '{\"quests\":{}}'::jsonb)",
        {"id": SAVE_ID, "campaign": CAMPAIGN_ID},
    )


async def _assert_legacy_rows_preserved(database: DisposableDatabase) -> None:
    assert await database.fetch_one(
        "SELECT world_slug, global_summary FROM campaigns WHERE id = :id", {"id": CAMPAIGN_ID}
    ) == ("legacy-world", "A legacy summary.")
    assert await database.fetch_one(
        "SELECT player_action, narration, summary FROM turns WHERE id = :id", {"id": TURN_ID}
    ) == ("Find the gate.", "The gate opens.", "A legacy turn summary.")
    assert await database.fetch_one(
        "SELECT entity_name, entity_type, content FROM memory_facts WHERE id = :id",
        {"id": FACT_ID},
    ) == ("Mira", "npc", "Mira opened the gate.")
    assert await database.fetch_one(
        "SELECT name, turn_number, scene_summary, campaign_snapshot FROM saves WHERE id = :id",
        {"id": SAVE_ID},
    ) == ("Legacy save", 1, "Before migration", {"quests": {}})


async def _assert_history_uninitialized(database: DisposableDatabase) -> set[str]:
    assert await database.fetch_one(
        "SELECT memory_policy_id, active_continuation_id, active_head_turn_id,"
        " active_memory_state_id, active_action_request_id"
        " FROM campaigns WHERE id = :id",
        {"id": CAMPAIGN_ID},
    ) == (None, None, None, None, None)
    assert await database.fetch_one(
        "SELECT continuation_id, parent_turn_id, history_depth FROM turns WHERE id = :id",
        {"id": TURN_ID},
    ) == (None, None, None)
    assert await database.fetch_one(
        "SELECT memory_policy_id, continuation_id, head_turn_id, global_checkpoint_id,"
        " last_compacted_batch_id FROM saves WHERE id = :id",
        {"id": SAVE_ID},
    ) == (None, None, None, None, None)
    assert await database.fetch_one(
        "SELECT batch_id, policy_id, ordinal, category, assertion_type, fact_metadata,"
        " generation_id FROM memory_facts WHERE id = :id",
        {"id": FACT_ID},
    ) == (None, None, None, None, None, None, None)

    tables = await _public_tables(database)
    assert {"history_continuations", "memory_policies"} <= tables
    return tables


async def _assert_new_tables_empty(database: DisposableDatabase, before: set[str]) -> set[str]:
    after = await _public_tables(database)
    new_tables = after - before
    assert new_tables
    for table in sorted(new_tables):
        count = await database.fetch_one(f'SELECT count(*) FROM "{table}"')
        assert count[0] == 0, f"migration populated new table {table}"
    return new_tables


async def test_009_to_head_preserves_legacy_memory_and_downgrade_round_trip() -> None:
    async with DisposableDatabase() as database:
        await database.upgrade("009_campaign_language")
        await _seed_legacy_rows(database)
        old_tables = await _public_tables(database)

        await database.upgrade(HEAD_REVISION)
        assert await database.version() == HEAD_REVISION
        await _assert_legacy_rows_preserved(database)
        await _assert_history_uninitialized(database)
        new_tables = await _assert_new_tables_empty(database, old_tables)

        await database.downgrade("009_campaign_language")
        assert await database.version() == "009_campaign_language"
        assert not (new_tables & await _public_tables(database))
        await _assert_legacy_rows_preserved(database)

        await database.upgrade(HEAD_REVISION)
        assert await database.version() == HEAD_REVISION
        await _assert_legacy_rows_preserved(database)
        await _assert_history_uninitialized(database)
        await _assert_new_tables_empty(database, old_tables)
