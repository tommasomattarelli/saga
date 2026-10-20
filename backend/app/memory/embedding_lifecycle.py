"""ADR 0018 B — campaign embedding-index lifecycle.

Serializes per owner then per campaign: settings, ensure and retry all take the
user row lock first and revalidate the profile after acquiring it, so a profile
change can never race a job creation into a superseded profile. No provider call
is ever made while holding a lock or a DB session.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app import dependencies
from app.exceptions import NotFoundError, SagaError, ValidationError
from app.memory import embedding_queue
from app.models.embedding_index import EmbeddingIndex
from app.models.embedding_index import EmbeddingRebuildState as State

if TYPE_CHECKING:
    from app.ai.embedding_config import EmbeddingSpace, ResolvedEmbedding
    from app.memory.embedding_status import IndexStatus

OPEN_STATES = (State.QUEUED, State.RUNNING)
TERMINAL_STATES = (State.FAILED, State.CANCELLED)


def short_reason(exc: Exception) -> str:
    if isinstance(exc, SagaError):
        return exc.message[:500]
    return "The embedding provider call failed."


def wake_worker() -> None:
    from app.memory.embedding_worker import wake_embedding_worker

    wake_embedding_worker()


def space_matches_index(index: EmbeddingIndex, space: EmbeddingSpace) -> bool:
    return (
        index.provider == space.provider
        and index.model == space.model
        and (index.endpoint_name or None) == (space.endpoint_name or None)
        and (index.endpoint_identity or None) == (space.endpoint_identity or None)
        and index.pipeline_version == space.pipeline_version
    )


def new_index(campaign_id: uuid.UUID, space: EmbeddingSpace) -> EmbeddingIndex:
    return EmbeddingIndex(
        campaign_id=campaign_id,
        provider=space.provider,
        model=space.model,
        endpoint_name=space.endpoint_name,
        endpoint_identity=space.endpoint_identity,
        pipeline_version=space.pipeline_version,
        dimension=None,
        is_active=False,
        rebuild_state=State.QUEUED,
    )


async def lock_user(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(text("SELECT id FROM users WHERE id = :uid FOR UPDATE"), {"uid": user_id})


async def owned_campaign(
    db: AsyncSession, user_id: uuid.UUID, campaign_id: uuid.UUID, *, lock: bool
) -> None:
    statement = "SELECT id FROM campaigns WHERE id = :cid AND user_id = :uid"
    if lock:
        statement += " FOR UPDATE"
    row = await db.execute(text(statement), {"cid": campaign_id, "uid": user_id})
    if row.first() is None:
        raise NotFoundError("Campaign")


async def lock_campaign(db: AsyncSession, campaign_id: uuid.UUID) -> uuid.UUID | None:
    row = await db.execute(
        text("SELECT user_id FROM campaigns WHERE id = :cid FOR UPDATE"), {"cid": campaign_id}
    )
    result = row.first()
    return result[0] if result else None


async def open_index(db: AsyncSession, campaign_id: uuid.UUID) -> EmbeddingIndex | None:
    result = await db.execute(
        select(EmbeddingIndex).where(
            EmbeddingIndex.campaign_id == campaign_id,
            EmbeddingIndex.rebuild_state.in_(OPEN_STATES),
        )
    )
    return result.scalars().first()


async def active_index(db: AsyncSession, campaign_id: uuid.UUID) -> EmbeddingIndex | None:
    result = await db.execute(
        select(EmbeddingIndex).where(
            EmbeddingIndex.campaign_id == campaign_id, EmbeddingIndex.is_active.is_(True)
        )
    )
    return result.scalars().first()


async def latest_index(
    db: AsyncSession, campaign_id: uuid.UUID, *, terminal_only: bool = False
) -> EmbeddingIndex | None:
    statement = select(EmbeddingIndex).where(EmbeddingIndex.campaign_id == campaign_id)
    if terminal_only:
        statement = statement.where(EmbeddingIndex.rebuild_state.in_(TERMINAL_STATES))
    statement = statement.order_by(EmbeddingIndex.created_at.desc()).limit(1)
    result = await db.execute(statement)
    return result.scalars().first()


async def ensure_campaign_embedding_index(
    db: AsyncSession, *, user_id: uuid.UUID, campaign_id: uuid.UUID
) -> IndexStatus:
    """Idempotent: starts only the requested campaign. A failed/cancelled version
    at the current profile blocks a new job even while an older index is active."""
    await lock_user(db, user_id)
    await owned_campaign(db, user_id, campaign_id, lock=True)
    resolved = await _resolve_or_suspend(db, user_id, campaign_id)
    if resolved is None:
        return await _status(db, user_id, campaign_id)
    space = resolved.space

    open_target = await open_index(db, campaign_id)
    active = await active_index(db, campaign_id)
    if open_target is not None:
        matched = space_matches_index(open_target, space)
        await db.commit()
        if matched:
            wake_worker()
        return await _status(db, user_id, campaign_id)
    if active is not None and space_matches_index(active, space):
        await embedding_queue.reconcile_index_sources(db, active)
        await db.commit()
        wake_worker()
        return await _status(db, user_id, campaign_id)

    terminal = await latest_index(db, campaign_id, terminal_only=True)
    if terminal is not None and space_matches_index(terminal, space):
        await db.commit()
        return await _status(db, user_id, campaign_id)

    target = new_index(campaign_id, space)
    db.add(target)
    await db.flush()
    await embedding_queue.reconcile_index_sources(db, target)
    await db.commit()
    wake_worker()
    return await _status(db, user_id, campaign_id)


async def retry_campaign_embedding_index(
    db: AsyncSession, *, user_id: uuid.UUID, campaign_id: uuid.UUID
) -> IndexStatus:
    """Explicit retry: resumes a failed/cancelled version at the same profile,
    clears a suspended active maintenance, or creates a fresh target."""
    await lock_user(db, user_id)
    await owned_campaign(db, user_id, campaign_id, lock=True)
    resolved = await _resolve_or_suspend(db, user_id, campaign_id)
    if resolved is None:
        return await _status(db, user_id, campaign_id)
    space = resolved.space

    open_target = await open_index(db, campaign_id)
    if open_target is not None:
        matched = space_matches_index(open_target, space)
        await db.commit()
        if matched:
            wake_worker()
        return await _status(db, user_id, campaign_id)

    terminal = await latest_index(db, campaign_id, terminal_only=True)
    if terminal is not None and space_matches_index(terminal, space):
        terminal.rebuild_state = State.QUEUED
        terminal.last_error = None
        terminal.claim_token = None
        terminal.claimed_at = None
        await embedding_queue.reconcile_index_sources(db, terminal)
        await db.commit()
        wake_worker()
        return await _status(db, user_id, campaign_id)

    active = await active_index(db, campaign_id)
    if active is not None and active.last_error is not None:
        active.last_error = None
        await db.commit()
        wake_worker()
        return await _status(db, user_id, campaign_id)

    target = new_index(campaign_id, space)
    db.add(target)
    await db.flush()
    await embedding_queue.reconcile_index_sources(db, target)
    await db.commit()
    wake_worker()
    return await _status(db, user_id, campaign_id)


async def _resolve_or_suspend(
    db: AsyncSession, user_id: uuid.UUID, campaign_id: uuid.UUID
) -> ResolvedEmbedding | None:
    try:
        return await embedding_queue.resolve_embedding(user_id)
    except ValidationError as exc:
        await _persist_suspension(db, campaign_id, short_reason(exc))
        await db.commit()
        return None


async def _persist_suspension(db: AsyncSession, campaign_id: uuid.UUID, reason: str) -> None:
    index = await open_index(db, campaign_id)
    if index is None:
        return
    index.rebuild_state = State.FAILED
    index.last_error = reason
    index.claim_token = None
    index.claimed_at = None


async def cancel_campaign_embedding_index(
    db: AsyncSession, *, user_id: uuid.UUID, campaign_id: uuid.UUID
) -> IndexStatus:
    """Fence immediately: the open target dies and any claim token is cleared, so
    a late worker response can no longer write or cut over."""
    await lock_user(db, user_id)
    await owned_campaign(db, user_id, campaign_id, lock=True)
    indexes = (
        await db.execute(
            select(EmbeddingIndex)
            .where(EmbeddingIndex.campaign_id == campaign_id)
            .with_for_update()
        )
    ).scalars()
    for index in indexes:
        if index.rebuild_state in OPEN_STATES:
            index.rebuild_state = State.CANCELLED
        if index.claim_token is not None:
            index.claim_token = None
            index.claimed_at = None
    await db.commit()
    return await _status(db, user_id, campaign_id)


async def cleanup_superseded_indexes(
    db: AsyncSession, campaign_id: uuid.UUID, keep_id: uuid.UUID
) -> None:
    """Bounded cleanup of replaced/cancelled versions; never the active index."""
    await db.execute(
        text(
            "DELETE FROM embedding_indexes WHERE campaign_id = :cid AND id <> :keep"
            " AND NOT is_active AND rebuild_state IN ('completed','failed','cancelled')"
        ),
        {"cid": campaign_id, "keep": keep_id},
    )


async def recover_interrupted_rebuilds() -> int:
    """Reconcile persisted open/active indexes after a restart and wake the
    worker; a still-fresh lease is left to its live owner and picked up on
    expiry by the worker's finite scan."""
    async with dependencies.async_session() as db:
        campaign_ids = (
            (
                await db.execute(
                    text(
                        "SELECT DISTINCT campaign_id FROM embedding_indexes"
                        " WHERE rebuild_state IN ('queued','running') OR is_active"
                    )
                )
            )
            .scalars()
            .all()
        )
        for campaign_id in campaign_ids:
            indexes = (
                (
                    await db.execute(
                        select(EmbeddingIndex).where(EmbeddingIndex.campaign_id == campaign_id)
                    )
                )
                .scalars()
                .all()
            )
            for index in indexes:
                if index.rebuild_state in OPEN_STATES or index.is_active:
                    await embedding_queue.reconcile_index_sources(db, index)
        await db.commit()
    wake_worker()
    return len(campaign_ids)


async def _status(db: AsyncSession, user_id: uuid.UUID, campaign_id: uuid.UUID) -> IndexStatus:
    from app.memory.embedding_status import campaign_embedding_status

    return await campaign_embedding_status(db, user_id=user_id, campaign_id=campaign_id)
