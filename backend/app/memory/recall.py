from __future__ import annotations

import uuid
from collections.abc import Mapping
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
from app.ai.embeddings import embed_texts
from app.models.campaign import Campaign
from app.models.embedding_index import EmbeddingIndex
from app.models.memory_fact import MemoryFact
from app.models.source_embedding import EmbeddingSourceType, EmbeddingWorkState, SourceEmbedding


@dataclass(frozen=True)
class PreparedRecallQuery:
    owner_id: uuid.UUID
    campaign_id: uuid.UUID
    index_id: uuid.UUID
    space: EmbeddingSpace
    dimension: int
    vectors: Mapping[str, tuple[float, ...]]


@dataclass(frozen=True)
class RecallSnapshot:
    owner_id: uuid.UUID
    campaign_id: uuid.UUID
    index_id: uuid.UUID
    dimension: int
    space: EmbeddingSpace
    known_names: tuple[str, ...] = ()


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
    metadata_rows = (
        (
            await db.execute(
                select(MemoryFact.fact_metadata).where(
                    MemoryFact.campaign_id == campaign_id,
                    MemoryFact.fact_metadata.isnot(None),
                )
            )
        )
        .scalars()
        .all()
    )
    known_names = tuple(
        sorted(
            {
                entity.name
                for metadata in metadata_rows
                if metadata is not None
                for entity in metadata.entities
                if entity.name
            }
        )
    )
    return RecallSnapshot(owner_id, campaign_id, index.id, index.dimension, space, known_names)


async def embed_recall_query(
    snapshot: RecallSnapshot, action: str, anchor: str
) -> PreparedRecallQuery | None:
    composed = f"{action} {anchor}".strip()
    try:
        batch: EmbeddingBatch = await embed_texts(
            snapshot.space, [action, composed], user_id=snapshot.owner_id
        )
    except Exception:
        return None
    if (
        batch.dimension != snapshot.dimension
        or batch.space != snapshot.space
        or len(batch.vectors) != 2
        or any(len(vector) != snapshot.dimension for vector in batch.vectors)
    ):
        return None
    return PreparedRecallQuery(
        snapshot.owner_id,
        snapshot.campaign_id,
        snapshot.index_id,
        snapshot.space,
        snapshot.dimension,
        {"action": batch.vectors[0], "composed": batch.vectors[1]},
    )
