from tests.integration.migrations.migration_db import DisposableDatabase


async def test_empty_downgrade_restores_the_legacy_schema() -> None:
    async with DisposableDatabase() as database:
        await database.upgrade()

        await database.downgrade("015_gen_format_prefs")

        assert await database.version() == "015_gen_format_prefs"
        assert await database.fetch_one(
            "SELECT to_regclass('public.uq_memory_generations_job_role_send')"
        ) == (None,)
        assert (
            await database.fetch_all(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='memory_jobs' "
                "AND column_name IN ('execution_identity', 'terminal_at') "
                "ORDER BY column_name"
            )
            == []
        )
        assert (
            await database.fetch_all(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='memory_generations' "
                "AND column_name IN ('format_mode', 'request_identity_hash')"
            )
            == []
        )
        assert await database.fetch_one(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='memory_generations' "
            "AND column_name='attempt_id'"
        ) == ("NO",)
        assert (
            "BEFORE DELETE OR UPDATE"
            in (
                await database.fetch_one(
                    "SELECT pg_get_triggerdef(oid) FROM pg_trigger "
                    "WHERE tgname='memory_generation_guard'"
                )
            )[0]
        )
