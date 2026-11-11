from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai import router
from app.exceptions import ValidationError
from app.security.encryption import encrypt_api_key
from tests.integration.migrations.migration_db import DisposableDatabase
from tests.integration.migrations.test_migration_chain import _insert_campaign, _insert_user


@pytest.mark.asyncio
async def test_generation_profile_does_not_load_legacy_campaign_columns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with DisposableDatabase() as database:
        await database.run_alembic("upgrade", "009_campaign_language")
        user_id, campaign_id = str(uuid4()), str(uuid4())
        await _insert_user(database, user_id)
        await _insert_campaign(
            database,
            campaign_id=campaign_id,
            user_id=user_id,
            world_slug="legacy-world",
            difficulty="MEDIUM",
        )
        encrypted = encrypt_api_key("sk-fake-personal-key")
        await database.execute(
            "UPDATE users SET generation_provider = 'openrouter', generation_model = 'test-model',"
            " openrouter_api_key_enc = :key WHERE id = :id",
            {"key": encrypted, "id": user_id},
        )

        statements: list[str] = []

        def record_sql(
            _connection: object, _cursor: object, statement: str, *_args: object
        ) -> None:
            statements.append(statement.lower())

        assert database.engine is not None
        event.listen(database.engine.sync_engine, "before_cursor_execute", record_sql)

        @asynccontextmanager
        async def db_context() -> AsyncIterator[AsyncSession]:
            async with AsyncSession(database.engine) as session:
                await session.execute(text("SET TRANSACTION READ ONLY"))
                yield session

        fake_provider = object()
        provider_calls: list[tuple[str, str | None]] = []

        def build_provider(
            name: str, *, api_key: str | None, base_url: str | None = None
        ) -> object:
            provider_calls.append((name, api_key))
            return fake_provider

        monkeypatch.setattr(router, "get_db_context", db_context)
        monkeypatch.setattr(router, "get_provider", build_provider)
        monkeypatch.setattr(
            router,
            "_load_config",
            lambda: {
                "generation": {
                    "default": {"provider": "openrouter", "model": "default-model"},
                    "max_output_tokens": 1000,
                    "openrouter_session_affinity": False,
                }
            },
        )

        provider, config = await router.get_user_generation(user_id)
        with pytest.raises(ValidationError, match="settings are unavailable"):
            await router.get_user_generation(str(uuid4()))

        event.remove(database.engine.sync_engine, "before_cursor_execute", record_sql)
        assert provider is fake_provider
        assert (config.provider, config.model) == ("openrouter", "test-model")
        assert provider_calls == [("openrouter", "sk-fake-personal-key")]
        user_queries = [sql for sql in statements if "from users" in sql]
        assert len(user_queries) == 2
        assert not any("from campaigns" in sql for sql in statements)
        assert (await database.fetch_one("SELECT version_num FROM alembic_version"))[
            0
        ] == "009_campaign_language"
        assert (
            str(
                (
                    await database.fetch_one(
                        "SELECT id FROM campaigns WHERE id = :id", {"id": campaign_id}
                    )
                )[0]
            )
            == campaign_id
        )
