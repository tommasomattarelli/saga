from tests.integration.migration_db import DisposableDatabase
from tests.integration.test_migration_chain import _insert_campaign, _insert_user


async def test_language_migration_backfills_existing_campaign_and_preserves_data() -> None:
    async with DisposableDatabase() as database:
        await database.upgrade("008_schema_reconciliation")
        await _insert_user(database)
        await _insert_campaign(
            database, name="Existing", world_slug="the-awakening", difficulty="MEDIUM"
        )
        await database.upgrade()
        row = await database.fetch_one("SELECT name, language FROM campaigns")
        assert tuple(row) == ("Existing", "en")
        await database.execute("UPDATE campaigns SET language='it'")
        await database.upgrade()
        assert (await database.fetch_one("SELECT language FROM campaigns"))[0] == "it"
        await database.downgrade("008_schema_reconciliation")
        assert (await database.fetch_one("SELECT name FROM campaigns"))[0] == "Existing"
