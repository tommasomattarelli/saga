"""Semantic memory search via pgvector — queries the MemoryFact corpus."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.recall import PreparedRecallQuery
from app.models.memory_fact import MemoryFact
from app.models.source_embedding import EmbeddingWorkState, SourceEmbedding


async def search_similar_facts(
    campaign_id: str | uuid.UUID,
    query: str,
    db: AsyncSession,
    limit: int = 3,
    query_embedding: PreparedRecallQuery | None = None,
) -> list[MemoryFact]:
    """Find MemoryFacts semantically similar to the query via pgvector cosine distance.

    Pass `query_embedding` to reuse an embedding computed outside the DB session
    (rule 15) and skip the embedding API call here.
    """
    if query_embedding is None or uuid.UUID(str(campaign_id)) != query_embedding.campaign_id:
        return []

    result = await db.execute(
        select(MemoryFact)
        .where(
            MemoryFact.campaign_id == query_embedding.campaign_id,
            SourceEmbedding.index_id == query_embedding.index_id,
            SourceEmbedding.campaign_id == query_embedding.campaign_id,
            SourceEmbedding.memory_fact_id == MemoryFact.id,
            SourceEmbedding.work_state == EmbeddingWorkState.EMBEDDED,
            SourceEmbedding.embedding.isnot(None),
        )
        .where(func.vector_dims(SourceEmbedding.embedding) == query_embedding.dimension)
        .order_by(SourceEmbedding.embedding.cosine_distance(list(query_embedding.vector)))
        .limit(limit)
    )
    return list(result.scalars().all())
