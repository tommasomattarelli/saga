"""Semantic memory search via pgvector — queries the MemoryFact corpus."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import generate_embedding
from app.models.memory_fact import MemoryFact


async def search_similar_facts(
    campaign_id: str | uuid.UUID,
    query: str,
    db: AsyncSession,
    limit: int = 3,
) -> list[MemoryFact]:
    """Find MemoryFacts semantically similar to the query via pgvector cosine distance."""
    query_embedding = await generate_embedding(query)
    if query_embedding is None:
        return []

    result = await db.execute(
        select(MemoryFact)
        .where(
            MemoryFact.campaign_id == campaign_id,
            MemoryFact.embedding.isnot(None),
        )
        .order_by(MemoryFact.embedding.cosine_distance(query_embedding))
        .limit(limit)
    )
    return list(result.scalars().all())
