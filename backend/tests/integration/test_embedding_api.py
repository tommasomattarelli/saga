"""ADR 0018 B — authenticated lifecycle API and the profile-change guard."""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

from sqlalchemy import func, select, text

from app import dependencies
from app.memory.embedding_lifecycle import ensure_campaign_embedding_index
from app.models.campaign import Campaign, Difficulty
from app.models.embedding_index import EmbeddingIndex
from app.models.embedding_index import EmbeddingRebuildState as State
from app.models.user import User
from tests.integration.embedding_support import (
    create_user_campaign,
    fake_rebuild_config,
    fake_space,
    install_provider,
)


async def _owned_campaign(db, user_id: uuid.UUID) -> Campaign:
    campaign = Campaign(user_id=user_id, world_slug="w", name="mine", difficulty=Difficulty.MEDIUM)
    db.add(campaign)
    await db.commit()
    return campaign


async def _index_count(db, campaign_id: uuid.UUID) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(EmbeddingIndex)
            .where(EmbeddingIndex.campaign_id == campaign_id)
        )
    ).scalar_one()


async def test_ensure_and_status_are_idempotent_and_owned_only(
    auth_client, db_session, test_user, monkeypatch
) -> None:
    provider = install_provider(monkeypatch)
    campaign = await _owned_campaign(db_session, test_user["user"].id)
    _, foreign_campaign = await create_user_campaign(db_session)

    first = await auth_client.post(f"/api/campaigns/{campaign.id}/embedding-index/ensure")
    second = await auth_client.post(f"/api/campaigns/{campaign.id}/embedding-index/ensure")
    status = await auth_client.get(f"/api/campaigns/{campaign.id}/embedding-index")

    assert first.status_code == 200
    assert second.status_code == 200
    assert status.status_code == 200
    assert first.json()["target"]["state"] == "queued"
    assert await _index_count(db_session, campaign.id) == 1
    assert await _index_count(db_session, foreign_campaign.id) == 0
    assert provider.calls["embed"] == 0


async def test_cross_user_campaign_is_a_404(auth_client, db_session, monkeypatch) -> None:
    install_provider(monkeypatch)
    _, foreign_campaign = await create_user_campaign(db_session)

    for method, suffix in (
        ("get", ""),
        ("post", "/ensure"),
        ("post", "/retry"),
        ("post", "/cancel"),
    ):
        call = getattr(auth_client, method)
        response = await call(f"/api/campaigns/{foreign_campaign.id}/embedding-index{suffix}")
        assert response.status_code == 404


async def test_profile_change_is_rejected_while_a_rebuild_is_in_flight(
    auth_client, db_session, test_user, monkeypatch
) -> None:
    install_provider(monkeypatch)
    campaign = await _owned_campaign(db_session, test_user["user"].id)
    space = fake_space()
    db_session.add(
        EmbeddingIndex(
            campaign_id=campaign.id,
            provider=space.provider,
            model=space.model,
            endpoint_identity=space.endpoint_identity,
            pipeline_version=space.pipeline_version,
            is_active=False,
            rebuild_state=State.QUEUED,
        )
    )
    await db_session.commit()

    rejected = await auth_client.patch(
        "/api/settings",
        json={"embedding_provider": "google", "embedding_model": "text-embedding-004"},
    )
    allowed = await auth_client.put("/api/settings/api-keys", json={"openrouter": "sk-test-key"})

    assert rejected.status_code == 409
    assert await _index_count(db_session, campaign.id) == 1
    assert allowed.status_code == 200


async def test_settings_lock_serializes_with_ensure(db_session, monkeypatch) -> None:
    async def resolve(user_id, *, space=None):
        async with dependencies.async_session() as db:
            stored = await db.get(User, uuid.UUID(str(user_id)))
            provider = stored.embedding_provider or "openrouter"
            model = stored.embedding_model or "openai/text-embedding-3-small"
        return SimpleNamespace(
            space=fake_space(provider=provider, model=model),
            policy=fake_rebuild_config(),
        )

    install_provider(monkeypatch, resolve=resolve)
    user, campaign = await create_user_campaign(
        db_session, provider="openrouter", model="openai/text-embedding-3-small"
    )

    settings_session = dependencies.async_session()
    await settings_session.execute(
        text("SELECT id FROM users WHERE id = :uid FOR UPDATE"), {"uid": user.id}
    )
    await settings_session.execute(
        text(
            "UPDATE users SET embedding_provider = 'google',"
            " embedding_model = 'text-embedding-004' WHERE id = :uid"
        ),
        {"uid": user.id},
    )

    async def run_ensure() -> dict:
        async with dependencies.async_session() as db:
            return await ensure_campaign_embedding_index(
                db, user_id=user.id, campaign_id=campaign.id
            )

    task = asyncio.create_task(run_ensure())
    for _ in range(5):
        await asyncio.sleep(0)
    assert not task.done()

    await settings_session.commit()
    await settings_session.close()
    await task

    index = (
        await db_session.execute(
            select(EmbeddingIndex).where(EmbeddingIndex.campaign_id == campaign.id)
        )
    ).scalar_one()
    assert index.provider == "google"
    assert index.model == "text-embedding-004"
