"""ADR 0018 B — the persistent embedding queue and the single provider seam.

Pending rows in ``source_embeddings`` are the work queue: there is no separate
job framework. Writers enqueue inside their own transaction; the provider
boundary is reached only through the two call sites below, never with a DB
session open. The imports are deferred so this module stays importable while the
provider runtime is still landing; tests fake the boundary at these functions.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.embedding_index import EmbeddingIndex, EmbeddingRebuildState, text_hash
from app.models.source_embedding import (
    EmbeddingSourceType,
    EmbeddingWorkState,
    SourceEmbedding,
)

if TYPE_CHECKING:
    from app.ai.embedding_config import (
        EmbeddingBatch,
        EmbeddingRebuildConfig,
        EmbeddingSpace,
        ResolvedEmbedding,
    )

_OPEN_STATES = (EmbeddingRebuildState.QUEUED, EmbeddingRebuildState.RUNNING)


def get_rebuild_config() -> EmbeddingRebuildConfig:
    from app.ai.embedding_config import get_embedding_rebuild_config

    return get_embedding_rebuild_config()


async def resolve_embedding(
    user_id: uuid.UUID | str, *, space: EmbeddingSpace | None = None
) -> ResolvedEmbedding:
    from app.ai.router import get_user_embedding

    return await get_user_embedding(user_id, space=space)


async def embed_texts_via_provider(
    texts: list[str], resolved: ResolvedEmbedding
) -> EmbeddingBatch:
    from app.ai.embeddings import embed_batch

    return await embed_batch(texts, resolved)


async def enqueue_source_embedding(
    db: AsyncSession,
    *,
    campaign_id: uuid.UUID,
    source_type: EmbeddingSourceType,
    source_id: uuid.UUID,
    source_text: str | None,
) -> list[uuid.UUID]:
    """Persist work for a source in the caller's transaction (no network).

    Queues on the active index and on any open rebuild target, so a source that
    commits during a rebuild is not lost at cutover. Idempotent per hash.
    """
    if not source_text or not source_text.strip():
        return []
    if not await _lock_campaign(db, campaign_id):
        return []
    digest = text_hash(source_text)
    indexes = await _queueable_indexes(db, campaign_id)
    queued: list[uuid.UUID] = []
    for index in indexes:
        await _upsert_source(db, index, source_type, source_id, digest)
        queued.append(index.id)
    return queued


async def _lock_campaign(db: AsyncSession, campaign_id: uuid.UUID) -> bool:
    row = await db.execute(
        text("SELECT id FROM campaigns WHERE id = :cid FOR UPDATE"), {"cid": campaign_id}
    )
    return row.first() is not None


async def _queueable_indexes(db: AsyncSession, campaign_id: uuid.UUID) -> list[EmbeddingIndex]:
    result = await db.execute(
        select(EmbeddingIndex).where(
            EmbeddingIndex.campaign_id == campaign_id,
            or_(
                EmbeddingIndex.is_active.is_(True),
                EmbeddingIndex.rebuild_state.in_(_OPEN_STATES),
            ),
        )
    )
    return list(result.scalars().all())


async def _upsert_source(
    db: AsyncSession,
    index: EmbeddingIndex,
    source_type: EmbeddingSourceType,
    source_id: uuid.UUID,
    digest: str,
) -> None:
    is_turn = source_type is EmbeddingSourceType.TURN
    criterion = (
        SourceEmbedding.turn_id == source_id
        if is_turn
        else SourceEmbedding.memory_fact_id == source_id
    )
    existing = (
        await db.execute(
            select(SourceEmbedding).where(SourceEmbedding.index_id == index.id, criterion)
        )
    ).scalar_one_or_none()
    if existing is None:
        db.add(
            SourceEmbedding(
                index_id=index.id,
                campaign_id=index.campaign_id,
                source_type=source_type,
                turn_id=source_id if is_turn else None,
                memory_fact_id=None if is_turn else source_id,
                text_hash=digest,
                work_state=EmbeddingWorkState.PENDING,
            )
        )
        return
    if existing.text_hash == digest and existing.work_state == EmbeddingWorkState.EMBEDDED:
        return
    existing.text_hash = digest
    existing.work_state = EmbeddingWorkState.PENDING
    existing.embedding = None
    existing.last_error = None


_INCREMENTAL_TURN_INSERT = """
    INSERT INTO source_embeddings
        (id, index_id, campaign_id, source_type, turn_id, memory_fact_id, text_hash, work_state)
    SELECT gen_random_uuid(), :iid, t.campaign_id, 'turn', t.id, NULL,
           encode(sha256(convert_to(t.summary, 'UTF8')), 'hex'), 'pending'
    FROM turns t
    WHERE t.campaign_id = :cid AND t.summary IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM source_embeddings se
          WHERE se.index_id = :iid AND se.turn_id = t.id
      )
"""

_INCREMENTAL_FACT_INSERT = """
    INSERT INTO source_embeddings
        (id, index_id, campaign_id, source_type, turn_id, memory_fact_id, text_hash, work_state)
    SELECT gen_random_uuid(), :iid, mf.campaign_id, 'memory_fact', NULL, mf.id,
           encode(sha256(convert_to(mf.content, 'UTF8')), 'hex'), 'pending'
    FROM memory_facts mf
    WHERE mf.campaign_id = :cid AND mf.content IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM source_embeddings se
          WHERE se.index_id = :iid AND se.memory_fact_id = mf.id
      )
"""

_INCREMENTAL_TURN_REFRESH = """
    UPDATE source_embeddings se
    SET text_hash = encode(sha256(convert_to(t.summary, 'UTF8')), 'hex'),
        work_state = 'pending', embedding = NULL, last_error = NULL
    FROM turns t
    WHERE se.index_id = :iid AND se.turn_id = t.id
      AND se.text_hash <> encode(sha256(convert_to(t.summary, 'UTF8')), 'hex')
"""

_INCREMENTAL_FACT_REFRESH = """
    UPDATE source_embeddings se
    SET text_hash = encode(sha256(convert_to(mf.content, 'UTF8')), 'hex'),
        work_state = 'pending', embedding = NULL, last_error = NULL
    FROM memory_facts mf
    WHERE se.index_id = :iid AND se.memory_fact_id = mf.id
      AND se.text_hash <> encode(sha256(convert_to(mf.content, 'UTF8')), 'hex')
"""

_DROP_UNREPRESENTABLE = """
    DELETE FROM source_embeddings se
    WHERE se.index_id = :iid AND se.turn_id IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM turns t WHERE t.id = se.turn_id AND t.summary IS NOT NULL
      )
"""


async def reconcile_index_sources(db: AsyncSession, index: EmbeddingIndex) -> None:
    """Reconcile every committed source, not a turn_number watermark: facts
    arrive after the turn they reference, so late sources are picked up too."""
    params = {"iid": index.id, "cid": index.campaign_id}
    for statement in (
        _INCREMENTAL_TURN_INSERT,
        _INCREMENTAL_FACT_INSERT,
        _INCREMENTAL_TURN_REFRESH,
        _INCREMENTAL_FACT_REFRESH,
        _DROP_UNREPRESENTABLE,
    ):
        await db.execute(text(statement), params)
