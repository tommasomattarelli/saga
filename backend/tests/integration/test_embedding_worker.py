"""ADR 0018 B — worker batches, fencing, cutover and active maintenance."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import select

from app import dependencies
from app.memory import embedding_queue, embedding_worker
from app.memory.embedding_lifecycle import ensure_campaign_embedding_index
from app.models.embedding_index import EmbeddingIndex, text_hash
from app.models.embedding_index import EmbeddingRebuildState as State
from app.models.memory_fact import MemoryFact
from app.models.source_embedding import (
    EmbeddingSourceType,
    EmbeddingWorkState,
    SourceEmbedding,
)
from app.models.turn import Turn
from tests.integration.embedding_support import (
    DIMENSION,
    add_fact,
    add_turn,
    create_user_campaign,
    fake_space,
    install_provider,
)


def _manual_index(campaign_id: uuid.UUID, **overrides) -> EmbeddingIndex:
    space = fake_space()
    values = {
        "campaign_id": campaign_id,
        "provider": space.provider,
        "model": space.model,
        "endpoint_name": space.endpoint_name,
        "endpoint_identity": space.endpoint_identity,
        "pipeline_version": space.pipeline_version,
        "dimension": None,
        "is_active": False,
        "rebuild_state": State.QUEUED,
    }
    values.update(overrides)
    return EmbeddingIndex(**values)


async def _active(db, campaign_id: uuid.UUID) -> EmbeddingIndex | None:
    return (
        await db.execute(
            select(EmbeddingIndex)
            .where(
                EmbeddingIndex.campaign_id == campaign_id,
                EmbeddingIndex.is_active.is_(True),
            )
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()


async def _sources(db, index_id: uuid.UUID) -> list[SourceEmbedding]:
    return list(
        (
            await db.execute(
                select(SourceEmbedding)
                .where(SourceEmbedding.index_id == index_id)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )


async def test_worker_embeds_and_activates_the_target(db_session, monkeypatch) -> None:
    provider = install_provider(monkeypatch)
    user, campaign = await create_user_campaign(db_session)
    await add_turn(db_session, campaign, 1, "A quiet road.")
    await add_fact(db_session, campaign, 1, "The inn is closed.")
    await db_session.commit()
    await ensure_campaign_embedding_index(db_session, user_id=user.id, campaign_id=campaign.id)

    await embedding_worker.process_campaign_once(campaign.id)

    index = await _active(db_session, campaign.id)
    assert index is not None
    assert index.rebuild_state is State.COMPLETED
    assert index.dimension == DIMENSION
    assert provider.calls["embed"] == 1
    rows = await _sources(db_session, index.id)
    assert len(rows) == 2
    assert all(row.work_state is EmbeddingWorkState.EMBEDDED for row in rows)


async def test_new_source_after_cutover_uses_the_active_completed_index(
    db_session, monkeypatch
) -> None:
    install_provider(monkeypatch)
    user, campaign = await create_user_campaign(db_session)
    await add_turn(db_session, campaign, 1, "A quiet road.")
    await db_session.commit()
    await ensure_campaign_embedding_index(db_session, user_id=user.id, campaign_id=campaign.id)
    await embedding_worker.process_campaign_once(campaign.id)
    active = await _active(db_session, campaign.id)
    assert active is not None
    active_id = active.id

    fact = await add_fact(db_session, campaign, 2, "A late fact.")
    await db_session.commit()
    await embedding_queue.enqueue_source_embedding(
        db_session,
        campaign_id=campaign.id,
        source_type=EmbeddingSourceType.MEMORY_FACT,
        source_id=fact.id,
        source_text=fact.content,
    )
    await db_session.commit()

    await embedding_worker.process_campaign_once(campaign.id)

    refreshed = await _active(db_session, campaign.id)
    assert refreshed is not None and refreshed.id == active_id
    assert refreshed.rebuild_state is State.COMPLETED
    rows = await _sources(db_session, active_id)
    assert len(rows) == 2
    assert all(row.work_state is EmbeddingWorkState.EMBEDDED for row in rows)


async def test_provider_failure_stops_the_job_without_false_progress(
    db_session, monkeypatch
) -> None:
    async def explode(texts, resolved):
        raise RuntimeError("upstream exploded")

    install_provider(monkeypatch, embed=explode)
    user, campaign = await create_user_campaign(db_session)
    await add_turn(db_session, campaign, 1, "A quiet road.")
    await db_session.commit()
    await ensure_campaign_embedding_index(db_session, user_id=user.id, campaign_id=campaign.id)

    await embedding_worker.process_campaign_once(campaign.id)

    index = (
        await db_session.execute(
            select(EmbeddingIndex)
            .where(EmbeddingIndex.campaign_id == campaign.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert index.rebuild_state is State.FAILED
    assert index.last_error == "The embedding provider call failed."
    assert index.is_active is False
    rows = await _sources(db_session, index.id)
    assert rows and all(row.work_state is EmbeddingWorkState.PENDING for row in rows)


async def test_stolen_claim_discards_the_late_result(db_session, monkeypatch) -> None:
    user, campaign = await create_user_campaign(db_session)
    await add_turn(db_session, campaign, 1, "A quiet road.")
    await db_session.commit()
    install_provider(monkeypatch)
    await ensure_campaign_embedding_index(db_session, user_id=user.id, campaign_id=campaign.id)

    async def steal(texts, resolved):
        async with dependencies.async_session() as db:
            index = (
                await db.execute(
                    select(EmbeddingIndex).where(
                        EmbeddingIndex.campaign_id == campaign.id,
                        EmbeddingIndex.rebuild_state == State.RUNNING,
                    )
                )
            ).scalar_one()
            index.claim_token = uuid.uuid4()
            await db.commit()
        return SimpleNamespace(vectors=[[9.0] * DIMENSION for _ in texts], dimension=DIMENSION)

    install_provider(monkeypatch, embed=steal)
    await embedding_worker.process_campaign_once(campaign.id)

    index = (
        await db_session.execute(
            select(EmbeddingIndex)
            .where(EmbeddingIndex.campaign_id == campaign.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert index.is_active is False
    rows = await _sources(db_session, index.id)
    assert rows and all(row.work_state is EmbeddingWorkState.PENDING for row in rows)


async def test_expired_lease_is_resumed_by_the_scan(db_session, monkeypatch) -> None:
    install_provider(monkeypatch)
    user, campaign = await create_user_campaign(db_session)
    turn = await add_turn(db_session, campaign, 1, "A quiet road.")
    index = _manual_index(campaign.id, rebuild_state=State.RUNNING)
    index.claim_token = uuid.uuid4()
    index.claimed_at = datetime.now(UTC) - timedelta(hours=1)
    db_session.add(index)
    await db_session.flush()
    db_session.add(
        SourceEmbedding(
            index_id=index.id,
            campaign_id=campaign.id,
            source_type=EmbeddingSourceType.TURN,
            turn_id=turn.id,
            text_hash=text_hash(turn.summary or ""),
            work_state=EmbeddingWorkState.PENDING,
        )
    )
    await db_session.commit()

    await embedding_worker.scan_once()

    refreshed = await _active(db_session, campaign.id)
    assert refreshed is not None and refreshed.id == index.id
    assert refreshed.rebuild_state is State.COMPLETED


async def test_changed_text_discards_the_stale_vector(db_session, monkeypatch) -> None:
    user, campaign = await create_user_campaign(db_session)
    turn = await add_turn(db_session, campaign, 1, "Original text.")
    await db_session.commit()
    calls = {"count": 0}

    async def embed(texts, resolved):
        calls["count"] += 1
        if calls["count"] == 1:
            async with dependencies.async_session() as db:
                stored = await db.get(Turn, turn.id)
                stored.summary = "Changed text."
                await db.commit()
            return SimpleNamespace(vectors=[[1.0] * DIMENSION for _ in texts], dimension=DIMENSION)
        return SimpleNamespace(vectors=[[2.0] * DIMENSION for _ in texts], dimension=DIMENSION)

    install_provider(monkeypatch, embed=embed)
    await ensure_campaign_embedding_index(db_session, user_id=user.id, campaign_id=campaign.id)
    await embedding_worker.process_campaign_once(campaign.id)

    index = await _active(db_session, campaign.id)
    assert index is not None
    row = (await _sources(db_session, index.id))[0]
    assert row.work_state is EmbeddingWorkState.EMBEDDED
    assert row.text_hash == text_hash("Changed text.")
    assert row.embedding is not None and row.embedding[0] == 2.0
    assert calls["count"] == 2


async def test_late_fact_is_embedded_before_cutover(db_session, monkeypatch) -> None:
    user, campaign = await create_user_campaign(db_session)
    await add_turn(db_session, campaign, 1, "A quiet road.")
    await db_session.commit()
    observed: dict[str, object] = {"inserted": False, "active_during_call": "unset"}

    async def embed(texts, resolved):
        if not observed["inserted"]:
            observed["inserted"] = True
            async with dependencies.async_session() as db:
                active = await _active(db, campaign.id)
                observed["active_during_call"] = None if active is None else active.id
                fact = MemoryFact(
                    campaign_id=campaign.id,
                    turn_number=2,
                    entity_name="Late",
                    entity_type="npc",
                    content="A fact that arrived between batches.",
                )
                db.add(fact)
                await db.flush()
                await embedding_queue.enqueue_source_embedding(
                    db,
                    campaign_id=campaign.id,
                    source_type=EmbeddingSourceType.MEMORY_FACT,
                    source_id=fact.id,
                    source_text=fact.content,
                )
                await db.commit()
        return SimpleNamespace(vectors=[[3.0] * DIMENSION for _ in texts], dimension=DIMENSION)

    install_provider(monkeypatch, embed=embed)
    await ensure_campaign_embedding_index(db_session, user_id=user.id, campaign_id=campaign.id)
    await embedding_worker.process_campaign_once(campaign.id)

    assert observed["active_during_call"] is None
    index = await _active(db_session, campaign.id)
    assert index is not None
    rows = await _sources(db_session, index.id)
    assert len(rows) == 2
    assert all(row.work_state is EmbeddingWorkState.EMBEDDED for row in rows)


async def test_cancel_during_the_call_fences_the_result(db_session, monkeypatch) -> None:
    user, campaign = await create_user_campaign(db_session)
    await add_turn(db_session, campaign, 1, "A quiet road.")
    await db_session.commit()
    install_provider(monkeypatch)
    await ensure_campaign_embedding_index(db_session, user_id=user.id, campaign_id=campaign.id)

    async def cancel_midway(texts, resolved):
        async with dependencies.async_session() as db:
            index = (
                await db.execute(
                    select(EmbeddingIndex).where(
                        EmbeddingIndex.campaign_id == campaign.id,
                        EmbeddingIndex.rebuild_state == State.RUNNING,
                    )
                )
            ).scalar_one()
            index.rebuild_state = State.CANCELLED
            index.claim_token = None
            await db.commit()
        return SimpleNamespace(vectors=[[4.0] * DIMENSION for _ in texts], dimension=DIMENSION)

    install_provider(monkeypatch, embed=cancel_midway)
    await embedding_worker.process_campaign_once(campaign.id)

    index = (
        await db_session.execute(
            select(EmbeddingIndex)
            .where(EmbeddingIndex.campaign_id == campaign.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert index.rebuild_state is State.CANCELLED
    assert index.is_active is False
    rows = await _sources(db_session, index.id)
    assert rows and all(row.work_state is EmbeddingWorkState.PENDING for row in rows)


async def test_deleting_the_campaign_during_the_call_leaves_no_orphans(
    db_session, monkeypatch
) -> None:
    user, campaign = await create_user_campaign(db_session)
    await add_turn(db_session, campaign, 1, "A quiet road.")
    await db_session.commit()
    install_provider(monkeypatch)
    await ensure_campaign_embedding_index(db_session, user_id=user.id, campaign_id=campaign.id)

    async def delete_midway(texts, resolved):
        async with dependencies.async_session() as db:
            stored = await db.get(type(campaign), campaign.id)
            await db.delete(stored)
            await db.commit()
        return SimpleNamespace(vectors=[[5.0] * DIMENSION for _ in texts], dimension=DIMENSION)

    install_provider(monkeypatch, embed=delete_midway)
    await embedding_worker.process_campaign_once(campaign.id)

    indexes = (
        (
            await db_session.execute(
                select(EmbeddingIndex)
                .where(EmbeddingIndex.campaign_id == campaign.id)
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )
    assert list(indexes) == []


async def test_no_db_session_spans_a_provider_call(
    db_session, monkeypatch, assert_no_db_held
) -> None:
    user, campaign = await create_user_campaign(db_session)
    await add_turn(db_session, campaign, 1, "A quiet road.")
    await db_session.commit()

    async def embed(texts, resolved):
        assert_no_db_held()
        return SimpleNamespace(vectors=[[6.0] * DIMENSION for _ in texts], dimension=DIMENSION)

    install_provider(monkeypatch, embed=embed)
    await ensure_campaign_embedding_index(db_session, user_id=user.id, campaign_id=campaign.id)
    await db_session.commit()
    await embedding_worker.process_campaign_once(campaign.id)

    assert await _active(db_session, campaign.id) is not None


async def test_empty_campaign_activates_without_a_paid_probe(db_session, monkeypatch) -> None:
    provider = install_provider(monkeypatch)
    user, campaign = await create_user_campaign(db_session)

    await ensure_campaign_embedding_index(db_session, user_id=user.id, campaign_id=campaign.id)
    await db_session.commit()
    await embedding_worker.process_campaign_once(campaign.id)

    index = await _active(db_session, campaign.id)
    assert index is not None
    assert index.rebuild_state is State.COMPLETED
    assert index.dimension is None
    assert provider.calls["embed"] == 0
