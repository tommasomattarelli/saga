from tests.integration.migrations.migration_db import DisposableDatabase


async def test_019_installs_and_removes_only_its_generation_guard() -> None:
    async with DisposableDatabase() as database:
        await database.upgrade("018_memory_terminal_reason")
        await database.upgrade("019_memory_payload_retention")

        assert await database.version() == "019_memory_payload_retention"
        assert await database.fetch_one(
            "SELECT to_regprocedure('public.saga_memory_generation_retention_guard()')"
        ) == ("saga_memory_generation_retention_guard()",)

        await database.downgrade("018_memory_terminal_reason")

        assert await database.version() == "018_memory_terminal_reason"
        assert await database.fetch_one(
            "SELECT to_regprocedure('public.saga_memory_generation_retention_guard()')"
        ) == (None,)
        assert await database.fetch_one(
            "SELECT to_regprocedure('public.saga_memory_generation_guard()')"
        ) == ("saga_memory_generation_guard()",)
