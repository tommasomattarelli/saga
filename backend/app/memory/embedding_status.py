"""ADR 0018 B — read-only status view of a campaign's embedding index.

Progress is derived by counting persisted source rows; nothing here makes a
provider call or changes state.
"""

from __future__ import annotations

import uuid
from typing import TypedDict

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory import embedding_lifecycle as lifecycle
from app.models.embedding_index import EmbeddingIndex
from app.models.source_embedding import EmbeddingWorkState


class IndexSummary(TypedDict):
    id: uuid.UUID
    provider: str
    model: str
    endpoint_name: str | None
    pipeline_version: str
    dimension: int | None
    state: str
    last_error: str | None


class IndexProgress(TypedDict):
    total: int
    embedded: int
    pending: int
    failed: int
    turn_total: int
    fact_total: int


class IndexStatus(TypedDict):
    active: IndexSummary | None
    target: IndexSummary | None
    latest: IndexSummary | None
    progress: IndexProgress | None
    suspended_reason: str | None
    needs_retry: bool


def _summary(index: EmbeddingIndex | None) -> IndexSummary | None:
    if index is None:
        return None
    return {
        "id": index.id,
        "provider": index.provider,
        "model": index.model,
        "endpoint_name": index.endpoint_name,
        "pipeline_version": index.pipeline_version,
        "dimension": index.dimension,
        "state": str(index.rebuild_state),
        "last_error": index.last_error,
    }


async def _progress(db: AsyncSession, index: EmbeddingIndex | None) -> IndexProgress | None:
    if index is None:
        return None
    rows = await db.execute(
        text(
            "SELECT source_type, work_state, count(*) FROM source_embeddings"
            " WHERE index_id = :iid GROUP BY 1, 2"
        ),
        {"iid": index.id},
    )
    total = embedded = pending = failed = turns = facts = 0
    for source_type, work_state, count in rows.fetchall():
        total += count
        turns += count if source_type == "turn" else 0
        facts += count if source_type == "memory_fact" else 0
        if work_state == EmbeddingWorkState.EMBEDDED.value:
            embedded += count
        elif work_state == EmbeddingWorkState.PENDING.value:
            pending += count
        else:
            failed += count
    return {
        "total": total,
        "embedded": embedded,
        "pending": pending,
        "failed": failed,
        "turn_total": turns,
        "fact_total": facts,
    }


async def campaign_embedding_status(
    db: AsyncSession, *, user_id: uuid.UUID, campaign_id: uuid.UUID
) -> IndexStatus:
    await lifecycle.owned_campaign(db, user_id, campaign_id, lock=False)
    active = await lifecycle.active_index(db, campaign_id)
    target = await lifecycle.open_index(db, campaign_id)
    latest = await lifecycle.latest_index(db, campaign_id)
    terminal = await lifecycle.latest_index(db, campaign_id, terminal_only=True)
    reason = await _suspension_reason(db, user_id, active, target, terminal)
    progress = await _progress(db, target or active)
    suspended_active = active is not None and active.last_error is not None
    return {
        "active": _summary(active),
        "target": _summary(target),
        "latest": _summary(latest),
        "progress": progress,
        "suspended_reason": reason,
        "needs_retry": target is None and (terminal is not None or suspended_active),
    }


async def _suspension_reason(
    db: AsyncSession,
    user_id: uuid.UUID,
    active: EmbeddingIndex | None,
    target: EmbeddingIndex | None,
    terminal: EmbeddingIndex | None,
) -> str | None:
    if terminal is not None:
        if terminal.last_error:
            return terminal.last_error
        return "The last rebuild was cancelled; use retry to run it again."
    if target is not None:
        return None
    if active is not None:
        if active.last_error:
            return active.last_error
        return await _derived_suspension(db, user_id, active.provider)
    return await _derived_suspension(db, user_id)


async def _derived_suspension(
    db: AsyncSession, user_id: uuid.UUID, provider: str | None = None
) -> str | None:
    from app.ai.credentials import credential_source, effective_embedding_provider
    from app.models.user import User

    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user is None:
        return None
    provider = provider or effective_embedding_provider(user)
    if not provider:
        return "No embedding provider is configured. Choose one in settings."
    if credential_source(user, provider) == "missing":
        return (
            f"No embedding credential for `{provider}`. Add a personal key or enable"
            " consented server-key sharing in settings."
        )
    return None
