"""Real-PostgreSQL data transitions and 008 reconciliation guards."""

from __future__ import annotations

import pytest

from tests.integration.migration_db import DisposableDatabase

USER_ID = "11111111-1111-1111-1111-111111111111"
CAMPAIGN_ID = "22222222-2222-2222-2222-222222222222"
TURN_ID = "33333333-3333-3333-3333-333333333333"
FACT_ID = "44444444-4444-4444-4444-444444444444"


async def _insert_user(database: DisposableDatabase, user_id: str = USER_ID) -> None:
    await database.execute(
        "INSERT INTO users (id, username, email, hashed_password, is_active, is_admin,"
        " preferred_language) VALUES (:id, :username, :email, 'pw', true, false, 'en')",
        {"id": user_id, "username": f"user_{user_id[:8]}", "email": f"{user_id[:8]}@example.com"},
    )


async def _insert_campaign(
    database: DisposableDatabase,
    *,
    campaign_id: str = CAMPAIGN_ID,
    user_id: str = USER_ID,
    world_state: str = "{}",
    **extra: str | int,
) -> None:
    columns = {
        "id": campaign_id,
        "user_id": user_id,
        "name": "Campaign",
        "status": "ACTIVE",
        "turn_number": 0,
        "character_data": "{}",
        "world_state": world_state,
        "quests": "{}",
        **extra,
    }
    names = ", ".join(columns)
    values = ", ".join(f":{name}" for name in columns)
    await database.execute(
        f"INSERT INTO campaigns ({names}) VALUES ({values})",  # noqa: S608 - fixed columns
        columns,
    )


async def _column(
    database: DisposableDatabase, table: str, column: str
) -> tuple[str, str, str | None] | None:
    rows = await database.fetch_all(
        "SELECT data_type, is_nullable, column_default FROM information_schema.columns"
        " WHERE table_schema = 'public' AND table_name = :table AND column_name = :column",
        {"table": table, "column": column},
    )
    row = rows[0] if rows else None
    return (str(row[0]), str(row[1]), row[2]) if row is not None else None


async def test_003_backfills_npc_disposition_and_downgrades() -> None:
    async with DisposableDatabase() as database:
        await database.upgrade("002_narration_segments")
        await _insert_user(database)
        await _insert_campaign(
            database,
            world_state='{"npcs":{"Goblin":{"disposition":3,"mood":"angry"}}}',
            template_id="legacy-template",
            death_mode="DESTINO",
        )

        await database.upgrade("003_normalize_npc_disposition")
        row = await database.fetch_one(
            "SELECT world_state->'npcs'->'Goblin'->>'disposition_toward_player',"
            " world_state->'npcs'->'Goblin' ? 'disposition' FROM campaigns"
        )
        assert (row[0], row[1]) == ("3", False)

        await database.downgrade("002_narration_segments")
        row = await database.fetch_one(
            "SELECT world_state->'npcs'->'Goblin'->>'disposition',"
            " world_state->'npcs'->'Goblin' ? 'disposition_toward_player' FROM campaigns"
        )
        assert (row[0], row[1]) == ("3", False)


async def test_004_preserves_the_world_identity_and_drops_templates() -> None:
    async with DisposableDatabase() as database:
        await database.upgrade("003_normalize_npc_disposition")
        await _insert_user(database)
        await _insert_campaign(database, template_id="legacy-template", death_mode="DESTINO")
        await database.execute(
            "INSERT INTO templates (id, slug, name, description, author, version, difficulty,"
            " tags, content) VALUES (gen_random_uuid(), 't', 'T', 'D', 'A', '1', 5,"
            " '{}'::jsonb, '{}'::jsonb)"
        )

        await database.upgrade("004_world_model")
        row = await database.fetch_one(
            "SELECT world_slug, world_version, world_baseline FROM campaigns"
        )
        assert row[0] == "legacy-template"
        assert row[1] is None and row[2] is None
        assert not await database.table_exists("templates")

        await database.downgrade("003_normalize_npc_disposition")
        row = await database.fetch_one("SELECT template_id FROM campaigns")
        assert row[0] == "legacy-template"
        assert not await database.table_exists("templates")


async def test_005_renames_difficulty_and_fate_counter_both_ways() -> None:
    async with DisposableDatabase() as database:
        await database.upgrade("004_world_model")
        await _insert_user(database)
        for death_mode, campaign_id in [
            ("CRONISTA", "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            ("DESTINO", "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            ("IRONMAN", "cccccccc-cccc-cccc-cccc-cccccccccccc"),
        ]:
            await _insert_campaign(
                database,
                campaign_id=campaign_id,
                world_slug="legacy-world",
                death_mode=death_mode,
                world_state='{"destino_lives":2}',
            )

        await database.upgrade("005_campaign_difficulty")
        rows = await database.fetch_all(
            "SELECT difficulty::text, world_state->>'fate_interventions_left'"
            " FROM campaigns ORDER BY id"
        )
        assert [(row[0], row[1]) for row in rows] == [
            ("EASY", "2"),
            ("MEDIUM", "2"),
            ("HARD", "2"),
        ]
        assert (await database.fetch_one("SELECT to_regtype('difficulty')"))[0] is not None
        assert (await database.fetch_one("SELECT to_regtype('deathmode')"))[0] is None

        await database.downgrade("004_world_model")
        rows = await database.fetch_all(
            "SELECT death_mode::text, world_state->>'destino_lives' FROM campaigns ORDER BY id"
        )
        assert [(row[0], row[1]) for row in rows] == [
            ("CRONISTA", "2"),
            ("DESTINO", "2"),
            ("IRONMAN", "2"),
        ]


async def test_006_adds_provider_columns_without_touching_rows() -> None:
    async with DisposableDatabase() as database:
        await database.upgrade("005_campaign_difficulty")
        await _insert_user(database)
        await database.upgrade("006_user_provider_settings")
        assert await _column(database, "users", "generation_provider") is not None
        assert (await database.fetch_one("SELECT username FROM users"))[0] == "user_11111111"

        await database.downgrade("005_campaign_difficulty")
        assert await _column(database, "users", "generation_provider") is None
        assert (await database.fetch_one("SELECT username FROM users"))[0] == "user_11111111"


async def test_008_reconciles_schema_and_preserves_rows() -> None:
    async with DisposableDatabase() as database:
        await database.upgrade("007_embedding_index")
        await _insert_user(database)
        await _insert_campaign(database, world_slug="legacy-world", difficulty="MEDIUM")
        await database.execute(
            "INSERT INTO turns (id, campaign_id, turn_number, player_action, narration,"
            " model_used, importance_score, summary) VALUES (:id, :campaign, 1, 'a', 'n',"
            " 'model', 5, 'summary')",
            {"id": TURN_ID, "campaign": CAMPAIGN_ID},
        )
        await database.execute(
            "INSERT INTO memory_facts (id, campaign_id, turn_number, entity_name, entity_type,"
            " content) VALUES (:id, :campaign, 1, 'Goblin', 'npc', 'fled')",
            {"id": FACT_ID, "campaign": CAMPAIGN_ID},
        )

        await database.upgrade()
        assert await database.version() == "008_schema_reconciliation"
        assert await _column(database, "campaigns", "global_summary") == ("text", "YES", None)
        assert await _column(database, "turns", "summarization_failed") == (
            "boolean",
            "NO",
            None,
        )
        assert (await _column(database, "memory_facts", "created_at"))[1] == "NO"
        for table, column in (
            ("embedding_indexes", "is_active"),
            ("embedding_indexes", "rebuild_state"),
            ("source_embeddings", "work_state"),
        ):
            assert (await _column(database, table, column))[2] is None
        assert not await database.table_exists("achievements")
        assert not await database.table_exists("profile_stats")
        assert (await database.fetch_one("SELECT count(*) FROM campaigns"))[0] == 1
        assert (await database.fetch_one("SELECT count(*) FROM turns"))[0] == 1
        assert (await database.fetch_one("SELECT count(*) FROM memory_facts"))[0] == 1


async def _prepare_008(  # noqa: PLR0913 - explicit fixture data beats a builder
    database: DisposableDatabase,
    *,
    null_timestamps: bool = False,
    wrong_column: bool = False,
    dependent_view: bool = False,
    unexpected_default: bool = False,
) -> None:
    await database.upgrade("007_embedding_index")
    await _insert_user(database)
    await _insert_campaign(database, world_slug="legacy-world", difficulty="MEDIUM")
    if null_timestamps:
        await database.execute(
            "INSERT INTO memory_facts (id, campaign_id, turn_number, entity_name, entity_type,"
            " content, created_at, updated_at) VALUES (:id, :campaign, 1, 'Goblin', 'npc',"
            " 'fled', NULL, NULL)",
            {"id": FACT_ID, "campaign": CAMPAIGN_ID},
        )
    if wrong_column:
        await database.execute("ALTER TABLE campaigns ADD COLUMN global_summary INTEGER")
    if dependent_view:
        await database.execute("CREATE VIEW legacy_achievements AS SELECT id FROM achievements")
    if unexpected_default:
        await database.execute(
            "ALTER TABLE embedding_indexes ALTER COLUMN rebuild_state SET DEFAULT 'failed'"
        )


@pytest.mark.parametrize(
    "setup",
    ["null_timestamps", "wrong_column", "dependent_view", "unexpected_default"],
)
async def test_008_refuses_incompatible_state_atomically(setup: str) -> None:
    async with DisposableDatabase() as database:
        await _prepare_008(database, **{setup: True})
        result = await database.run_alembic("upgrade", "head")
        assert result.returncode != 0
        assert await database.version() == "007_embedding_index"
        if setup == "wrong_column":
            assert await _column(database, "campaigns", "global_summary") == (
                "integer",
                "YES",
                None,
            )
        else:
            assert await _column(database, "campaigns", "global_summary") is None
        assert await _column(database, "turns", "summarization_failed") is None


async def test_008_downgrade_refuses_to_recreate_dropped_data() -> None:
    async with DisposableDatabase() as database:
        await database.upgrade()
        result = await database.run_alembic("downgrade", "007_embedding_index")
        assert result.returncode != 0
        assert "cannot restore rows dropped" in (result.stdout + result.stderr)
        assert await database.version() == "008_schema_reconciliation"
        assert not await database.table_exists("achievements")
        assert not await database.table_exists("profile_stats")
