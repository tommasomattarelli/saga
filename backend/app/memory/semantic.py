"""Semantic memory search via pgvector."""

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.embeddings import generate_embedding
from app.models.turn import Turn


async def search_similar_turns(
    campaign_id: str,
    query: str,
    db: AsyncSession,
    limit: int = 5,
) -> list[Turn]:
    """Find turns semantically similar to the query using pgvector."""
    query_embedding = await generate_embedding(query)
    if query_embedding is None:
        return []

    # Use pgvector cosine distance operator
    result = await db.execute(
        select(Turn)
        .where(Turn.campaign_id == campaign_id, Turn.embedding.isnot(None))
        .order_by(Turn.embedding.cosine_distance(query_embedding))
        .limit(limit)
    )
    return list(result.scalars().all())
