"""ADR 0018 B review hardening — fencing, suspension, pacing and manifest spaces."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import func, select, text

from app import dependencies
from app.ai.embeddings import reset_adapter_cache
from app.memory import embedding_batch as batch
from app.memory import embedding_queue, embedding_worker
from app.memory.embedding_lifecycle import (
    ensure_campaign_embedding_index,
    retry_campaign_embedding_index,
)
from app.memory.embedding_status import campaign_embedding_status
from app.models.embedding_index import EmbeddingIndex, text_hash
from app.models.embedding_index import EmbeddingRebuildState as State
from app.models.source_embedding import (
    EmbeddingSourceType,
    EmbeddingWorkState,
    SourceEmbedding,
)
from app.security.encryption import encrypt_api_key
from tests.integration.embedding_support import (
    DIMENSION,
    add_fact,
    add_turn,
    create_user_campaign,
    fake_rebuild_config,
    fake_space,
    install_provider,
)


@pytest.fixture(autouse=True)
def clean_worker_state():
    reset_adapter_cache()
    embedding_worker._stop.clear()
    embedding_worker._last_request_at = 0.0
    yield
    embedding_worker._stop.clear()
    reset_adapter_cache()


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


def _openai_response(count: int, dimension: int) -> SimpleNamespace:
    return SimpleNamespace(
        data=[SimpleNamespace(index=index, embedding=[0.1] * dimension) for index in range(count)],
        model_extra=None,
    )


async def _reload_index(db, index_id: uuid.UUID) -> EmbeddingIndex:
    return (
        await db.execute(
            select(EmbeddingIndex)
            .where(EmbeddingIndex.id == index_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


async def _row(db, turn_id: uuid.UUID) -> SourceEmbedding:
    return (
        await db.execute(
            select(SourceEmbedding)
            .where(SourceEmbedding.turn_id == turn_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


async def _prepared_campaign(db, monkeypatch, *, turns: int = 2):
    install_provider(monkeypatch)
    user, campaign = await create_user_campaign(db)
    created = []
    for number in range(1, turns + 1):
        created.append(await add_turn(db, campaign, number, f"Turn number {number}."))
    await db.commit()
    await ensure_campaign_embedding_index(db, user_id=user.id, campaign_id=campaign.id)
    await db.commit()
    return user, campaign, created


# --- lease expiry -----------------------------------------------------------


async def test_lease_expiry_during_call_blocks_save_cutover_and_renewal(
    db_session, monkeypatch
) -> None:
    user, campaign = await create_user_campaign(db_session)
    await add_turn(db_session, campaign, 1, "A quiet road.")
    await db_session.commit()
    expired = {"at": datetime.now(UTC) - timedelta(hours=2), "token": None}

    async def embed(texts, resolved):
        async with dependencies.async_session() as db:
            index = (
                await db.execute(
                    select(EmbeddingIndex).where(
                        EmbeddingIndex.campaign_id == campaign.id,
                        EmbeddingIndex.rebuild_state == State.RUNNING,
                    )
                )
            ).scalar_one()
            index.claimed_at = expired["at"]
            expired["token"] = index.claim_token
            await db.commit()
        return SimpleNamespace(vectors=[[1.0] * DIMENSION for _ in texts], dimension=DIMENSION)

    install_provider(monkeypatch, embed=embed)
    await ensure_campaign_embedding_index(db_session, user_id=user.id, campaign_id=campaign.id)
    await db_session.commit()

    await embedding_worker.process_campaign_once(campaign.id)

    index = (
        await db_session.execute(
            select(EmbeddingIndex)
            .where(EmbeddingIndex.campaign_id == campaign.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert index.claim_token == expired["token"]
    assert index.is_active is False
    assert index.claimed_at is not None
    assert index.claimed_at.timestamp() == pytest.approx(expired["at"].timestamp())
    row = (
        await db_session.execute(
            select(SourceEmbedding)
            .where(SourceEmbedding.index_id == index.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert row.work_state is EmbeddingWorkState.PENDING
    assert row.embedding is None


async def test_expired_lease_error_path_writes_nothing(db_session, monkeypatch) -> None:
    user, campaign = await create_user_campaign(db_session)
    await add_turn(db_session, campaign, 1, "A quiet road.")
    await db_session.commit()

    async def embed(texts, resolved):
        async with dependencies.async_session() as db:
            index = (
                await db.execute(
                    select(EmbeddingIndex).where(
                        EmbeddingIndex.campaign_id == campaign.id,
                        EmbeddingIndex.rebuild_state == State.RUNNING,
                    )
                )
            ).scalar_one()
            index.claimed_at = datetime.now(UTC) - timedelta(hours=2)
            await db.commit()
        raise RuntimeError("429")

    install_provider(monkeypatch, embed=embed)
    await ensure_campaign_embedding_index(db_session, user_id=user.id, campaign_id=campaign.id)
    await db_session.commit()

    await embedding_worker.process_campaign_once(campaign.id)

    index = (
        await db_session.execute(
            select(EmbeddingIndex)
            .where(EmbeddingIndex.campaign_id == campaign.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert index.rebuild_state is State.RUNNING
    assert index.last_error is None


# --- writer vs save ---------------------------------------------------------


async def test_writer_lock_serializes_with_save_and_hash_is_rechecked(
    db_session, monkeypatch
) -> None:
    user, campaign = await create_user_campaign(db_session)
    turn = await add_turn(db_session, campaign, 1, "Original text.")
    await db_session.commit()
    calls = {"count": 0}
    state: dict[str, object] = {}
    writer_started = asyncio.Event()

    async def embed(texts, resolved):
        calls["count"] += 1
        if calls["count"] == 1:
            writer = dependencies.async_session()
            await writer.execute(
                text("SELECT id FROM campaigns WHERE id = :cid FOR UPDATE"),
                {"cid": campaign.id},
            )
            await writer.execute(
                text("UPDATE turns SET summary = :summary WHERE id = :tid"),
                {"summary": "Changed during save", "tid": turn.id},
            )
            state["writer"] = writer
            writer_started.set()
            return SimpleNamespace(vectors=[[1.0] * DIMENSION for _ in texts], dimension=DIMENSION)
        return SimpleNamespace(vectors=[[2.0] * DIMENSION for _ in texts], dimension=DIMENSION)

    install_provider(monkeypatch, embed=embed)
    await ensure_campaign_embedding_index(db_session, user_id=user.id, campaign_id=campaign.id)
    await db_session.commit()

    task = asyncio.create_task(embedding_worker.process_campaign_once(campaign.id))
    try:
        await asyncio.wait_for(writer_started.wait(), timeout=5)
        assert "writer" in state
        assert not task.done()
        async with dependencies.async_session() as probe:
            barrier = (
                await probe.execute(
                    text(
                        "SELECT work_state, embedding FROM source_embeddings WHERE turn_id = :tid"
                    ),
                    {"tid": turn.id},
                )
            ).first()
        assert barrier is not None
        assert barrier[0] == "pending" and barrier[1] is None
    finally:
        writer = state.get("writer")
        if writer is not None:
            await writer.commit()
            await writer.close()
    await task

    index = (
        await db_session.execute(
            select(EmbeddingIndex)
            .where(EmbeddingIndex.campaign_id == campaign.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    row = await _row(db_session, turn.id)
    assert row.work_state is EmbeddingWorkState.EMBEDDED
    assert row.text_hash == text_hash("Changed during save")
    assert row.embedding is not None and row.embedding[0] == 2.0
    assert calls["count"] == 2
    assert index.is_active is True


# --- pacing and stop --------------------------------------------------------


async def test_single_pacing_gate_spans_campaigns(
    db_session, monkeypatch, assert_no_db_held
) -> None:
    sleeps: list[float] = []
    clock = [1000.0]
    monkeypatch.setattr(embedding_worker, "_monotonic", lambda: clock[0])

    async def fake_sleep(seconds: float) -> None:
        assert_no_db_held()
        sleeps.append(seconds)
        clock[0] += seconds

    monkeypatch.setattr(embedding_worker, "_sleep", fake_sleep)
    monkeypatch.setattr(embedding_worker, "_last_request_at", 0.0)
    install_provider(monkeypatch, policy=fake_rebuild_config(rebuild_min_interval_seconds=1))

    user, first = await create_user_campaign(db_session)
    await add_turn(db_session, first, 1, "First campaign.")
    await db_session.commit()
    await ensure_campaign_embedding_index(db_session, user_id=user.id, campaign_id=first.id)
    await db_session.commit()

    _, second = await create_user_campaign(db_session)
    await add_turn(db_session, second, 1, "Second campaign.")
    await db_session.commit()
    await ensure_campaign_embedding_index(
        db_session, user_id=second.user_id, campaign_id=second.id
    )
    await db_session.commit()

    await embedding_worker.process_campaign_once(first.id)
    await embedding_worker.process_campaign_once(second.id)

    assert any(abs(seconds - 1.0) < 1e-9 for seconds in sleeps)


async def test_stop_between_batches_releases_claim_and_keeps_work(db_session, monkeypatch) -> None:
    _, campaign, _ = await _prepared_campaign(db_session, monkeypatch)
    calls = {"count": 0}

    async def embed(texts, resolved):
        calls["count"] += 1
        if calls["count"] == 1:
            embedding_worker._stop.set()
        return SimpleNamespace(vectors=[[1.0] * DIMENSION for _ in texts], dimension=DIMENSION)

    install_provider(
        monkeypatch,
        policy=fake_rebuild_config(batch_size=1),
        embed=embed,
    )
    try:
        await embedding_worker.process_campaign_once(campaign.id)
    finally:
        embedding_worker._stop.clear()

    assert calls["count"] == 1
    index = (
        await db_session.execute(
            select(EmbeddingIndex)
            .where(EmbeddingIndex.campaign_id == campaign.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert index.rebuild_state is State.RUNNING
    assert index.claim_token is None
    pending = (
        await db_session.execute(
            select(func.count())
            .select_from(SourceEmbedding)
            .where(
                SourceEmbedding.index_id == index.id,
                SourceEmbedding.work_state == EmbeddingWorkState.PENDING,
            )
        )
    ).scalar_one()
    assert pending == 1


async def test_cutover_with_new_pending_releases_claim(db_session, monkeypatch) -> None:
    install_provider(monkeypatch)
    user, campaign = await create_user_campaign(db_session)
    await db_session.commit()
    await ensure_campaign_embedding_index(db_session, user_id=user.id, campaign_id=campaign.id)
    await db_session.commit()
    cfg = embedding_queue.get_rebuild_config()

    async with dependencies.async_session() as db:
        claim = await batch.claim_work(db, campaign.id, cfg)
        await db.commit()
    assert claim is not None
    assert claim.kind == "cutover"

    turn = await add_turn(db_session, campaign, 1, "Arrived after the claim.")
    await embedding_queue.enqueue_source_embedding(
        db_session,
        campaign_id=campaign.id,
        source_type=EmbeddingSourceType.TURN,
        source_id=turn.id,
        source_text=turn.summary,
    )
    await db_session.commit()

    async with dependencies.async_session() as db:
        acted = await embedding_worker.cutover(db, claim, cfg)
        await db.commit()
    assert acted is False

    index = (
        await db_session.execute(
            select(EmbeddingIndex)
            .where(EmbeddingIndex.campaign_id == campaign.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert index.claim_token is None
    assert index.rebuild_state is State.RUNNING


# --- active suspension ------------------------------------------------------


async def test_active_failure_suspends_without_a_paid_loop(db_session, monkeypatch) -> None:
    user, campaign, _ = await _prepared_campaign(db_session, monkeypatch, turns=1)
    await embedding_worker.process_campaign_once(campaign.id)
    active = (
        await db_session.execute(
            select(EmbeddingIndex)
            .where(EmbeddingIndex.campaign_id == campaign.id, EmbeddingIndex.is_active.is_(True))
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    fact = await add_fact(db_session, campaign, 2, "Late fact.")
    await db_session.commit()
    await embedding_queue.enqueue_source_embedding(
        db_session,
        campaign_id=campaign.id,
        source_type=EmbeddingSourceType.MEMORY_FACT,
        source_id=fact.id,
        source_text=fact.content,
    )
    await db_session.commit()
    calls = {"count": 0}

    async def fail(texts, resolved):
        calls["count"] += 1
        raise RuntimeError("429")

    install_provider(monkeypatch, embed=fail)
    await embedding_worker.process_campaign_once(campaign.id)
    active = await _reload_index(db_session, active.id)
    assert active.rebuild_state is State.COMPLETED
    assert active.last_error == "The embedding provider call failed."
    assert active.claim_token is None

    for _ in range(3):
        await embedding_worker.scan_once()
    assert calls["count"] == 1

    await ensure_campaign_embedding_index(db_session, user_id=user.id, campaign_id=campaign.id)
    active = await _reload_index(db_session, active.id)
    assert active.last_error is not None
    status = await campaign_embedding_status(db_session, user_id=user.id, campaign_id=campaign.id)
    assert status["needs_retry"] is True
    assert status["suspended_reason"] is not None

    await retry_campaign_embedding_index(db_session, user_id=user.id, campaign_id=campaign.id)
    active = await _reload_index(db_session, active.id)
    assert active.last_error is None


async def test_suspended_active_does_not_block_a_target(db_session, monkeypatch) -> None:
    _, campaign = await create_user_campaign(db_session)
    first = await add_turn(db_session, campaign, 1, "First.")
    active = _manual_index(
        campaign.id,
        is_active=True,
        rebuild_state=State.COMPLETED,
        dimension=DIMENSION,
        last_error="429",
    )
    db_session.add(active)
    await db_session.flush()
    db_session.add(
        SourceEmbedding(
            index_id=active.id,
            campaign_id=campaign.id,
            source_type=EmbeddingSourceType.TURN,
            turn_id=first.id,
            text_hash=text_hash(first.summary or ""),
            work_state=EmbeddingWorkState.PENDING,
        )
    )
    target = _manual_index(campaign.id, rebuild_state=State.QUEUED)
    db_session.add(target)
    await db_session.flush()
    second = await add_turn(db_session, campaign, 2, "Second.")
    db_session.add(
        SourceEmbedding(
            index_id=target.id,
            campaign_id=campaign.id,
            source_type=EmbeddingSourceType.TURN,
            turn_id=second.id,
            text_hash=text_hash(second.summary or ""),
            work_state=EmbeddingWorkState.PENDING,
        )
    )
    await db_session.commit()

    provider = install_provider(monkeypatch)
    await embedding_worker.scan_once()

    assert provider.calls["embed"] == 1
    refreshed = (
        await db_session.execute(
            select(EmbeddingIndex)
            .where(EmbeddingIndex.id == target.id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    assert refreshed.is_active is True
    assert refreshed.rebuild_state is State.COMPLETED


# --- real router, fake transport: manifest space ----------------------------


async def test_active_maintenance_uses_the_manifest_space_not_the_profile(
    db_session, assert_no_db_held
) -> None:
    user, campaign = await create_user_campaign(
        db_session, provider="google", model="gemini-embedding-2"
    )
    user.openrouter_api_key_enc = encrypt_api_key("openrouter-key")
    await db_session.commit()
    active = EmbeddingIndex(
        campaign_id=campaign.id,
        provider="openrouter",
        model="openai/text-embedding-3-small",
        endpoint_identity="https://openrouter.ai/api/v1",
        pipeline_version="embed-v1",
        dimension=DIMENSION,
        is_active=True,
        rebuild_state=State.COMPLETED,
    )
    db_session.add(active)
    await db_session.flush()
    turn = await add_turn(db_session, campaign, 1, "Maintenance source.")
    await embedding_queue.enqueue_source_embedding(
        db_session,
        campaign_id=campaign.id,
        source_type=EmbeddingSourceType.TURN,
        source_id=turn.id,
        source_text=turn.summary,
    )
    await db_session.commit()
    captured: dict[str, object] = {}

    async def create(*args, **kwargs):
        assert_no_db_held()
        captured.update(kwargs)
        return _openai_response(len(kwargs["input"]), DIMENSION)

    with patch("openai.resources.embeddings.AsyncEmbeddings.create", side_effect=create):
        await embedding_worker.process_campaign_once(campaign.id)

    assert captured["model"] == "openai/text-embedding-3-small"
    assert "dimensions" not in captured
    row = await _row(db_session, turn.id)
    assert row.work_state is EmbeddingWorkState.EMBEDDED


async def test_active_maintenance_uses_the_legacy_384_space(db_session, assert_no_db_held) -> None:
    user, campaign = await create_user_campaign(
        db_session, provider="openrouter", model="openai/text-embedding-3-small"
    )
    user.openai_api_key_enc = encrypt_api_key("openai-key")
    await db_session.commit()
    active = EmbeddingIndex(
        campaign_id=campaign.id,
        provider="openai",
        model="text-embedding-3-small",
        endpoint_identity="https://api.openai.com/v1",
        pipeline_version="embed-v1-legacy",
        dimension=384,
        is_active=True,
        rebuild_state=State.COMPLETED,
    )
    db_session.add(active)
    await db_session.flush()
    turn = await add_turn(db_session, campaign, 1, "Legacy source.")
    await embedding_queue.enqueue_source_embedding(
        db_session,
        campaign_id=campaign.id,
        source_type=EmbeddingSourceType.TURN,
        source_id=turn.id,
        source_text=turn.summary,
    )
    await db_session.commit()
    captured: dict[str, object] = {}

    async def create(*args, **kwargs):
        assert_no_db_held()
        captured.update(kwargs)
        return _openai_response(len(kwargs["input"]), 384)

    with patch("openai.resources.embeddings.AsyncEmbeddings.create", side_effect=create):
        await embedding_worker.process_campaign_once(campaign.id)

    assert captured["model"] == "text-embedding-3-small"
    assert captured["dimensions"] == 384
    row = await _row(db_session, turn.id)
    assert row.work_state is EmbeddingWorkState.EMBEDDED
