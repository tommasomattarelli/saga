from tests.integration.migrations.migration_db import DisposableDatabase
from tests.integration.migrations.test_migration_chain import _insert_user

USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


async def test_015_adds_nullable_preferences_without_backfilling_existing_users() -> None:
    async with DisposableDatabase() as database:
        await database.upgrade("014_turn_request_responses")
        await _insert_user(database, USER_ID)
        await database.execute(
            "UPDATE users SET generation_provider='openai', generation_model='legacy-model', "
            "openai_api_key_enc='ciphertext', preferred_language='it' WHERE id=:id",
            {"id": USER_ID},
        )

        await database.upgrade("015_gen_format_prefs")

        assert await database.fetch_one(
            "SELECT generation_allow_json_mode_fallback, "
            "generation_allow_prompt_only_fallback, generation_format_fingerprint, "
            "generation_provider, generation_model, openai_api_key_enc, preferred_language "
            "FROM users WHERE id=:id",
            {"id": USER_ID},
        ) == (None, None, None, "openai", "legacy-model", "ciphertext", "it")


async def test_fresh_upgrade_includes_generation_format_preferences() -> None:
    async with DisposableDatabase() as database:
        await database.upgrade()
        await database.require_model_schema()
