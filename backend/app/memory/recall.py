from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embedding_config import (
    LEGACY_BASE_URL,
    LEGACY_MODEL,
    EmbeddingBatch,
    EmbeddingSpace,
    build_space,
    legacy_space,
    local_space,
)
from app.ai.embeddings import embed_query_for_index
from app.models.campaign import Campaign
from app.models.embedding_index import EmbeddingIndex
from app.models.source_embedding import EmbeddingSourceType, EmbeddingWorkState, SourceEmbedding


@dataclass(frozen=True)
class PreparedRecallQuery:
    owner_id: uuid.UUID
    campaign_id: uuid.UUID
    index_id: uuid.UUID
    space: EmbeddingSpace
    dimension: int
    vector: tuple[float, ...]


@dataclass(frozen=True)
class RecallSnapshot:
    owner_id: uuid.UUID
    campaign_id: uuid.UUID
    index_id: uuid.UUID
    dimension: int
    space: EmbeddingSpace


async def snapshot_recall_query(db: AsyncSession, campaign_id: uuid.UUID) -> RecallSnapshot | None:
    row = (
        await db.execute(
            select(Campaign.user_id, EmbeddingIndex)
            .join(
                EmbeddingIndex,
                (EmbeddingIndex.campaign_id == Campaign.id) & EmbeddingIndex.is_active.is_(True),
            )
            .where(Campaign.id == campaign_id)
        )
    ).one_or_none()
    if row is None:
        return None
    owner_id, index = row
    if index.dimension is None:
        return None
    usable = await db.scalar(
        select(SourceEmbedding.id)
        .where(
            SourceEmbedding.index_id == index.id,
            SourceEmbedding.campaign_id == campaign_id,
            SourceEmbedding.work_state == EmbeddingWorkState.EMBEDDED,
            SourceEmbedding.source_type == EmbeddingSourceType.MEMORY_FACT,
            SourceEmbedding.embedding.is_not(None),
            func.vector_dims(SourceEmbedding.embedding) == index.dimension,
        )
        .limit(1)
    )
    if usable is None:
        return None
    try:
        if index.pipeline_version == "embed-v1-legacy":
            if (
                index.provider != "openai"
                or index.model != LEGACY_MODEL
                or index.endpoint_identity != LEGACY_BASE_URL
            ):
                return None
            space = legacy_space()
        elif index.provider == "local" and index.endpoint_name:
            space = local_space(index.endpoint_name, index.model)
        else:
            space = build_space(
                index.provider, index.model, pipeline_version=index.pipeline_version
            )
        if space.endpoint_identity != index.endpoint_identity:
            return None
    except ValueError:
        return None
    return RecallSnapshot(owner_id, campaign_id, index.id, index.dimension, space)


async def embed_recall_query(snapshot: RecallSnapshot, query: str) -> PreparedRecallQuery | None:
    try:
        batch: EmbeddingBatch = await embed_query_for_index(
            snapshot.space, query, user_id=snapshot.owner_id
        )
    except Exception:
        return None
    if (
        batch.dimension != snapshot.dimension
        or batch.space != snapshot.space
        or len(batch.vectors) != 1
        or len(batch.vectors[0]) != snapshot.dimension
    ):
        return None
    return PreparedRecallQuery(
        snapshot.owner_id,
        snapshot.campaign_id,
        snapshot.index_id,
        snapshot.space,
        snapshot.dimension,
        batch.vectors[0],
    )
