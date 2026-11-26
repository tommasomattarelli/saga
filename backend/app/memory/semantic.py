"""Semantic memory search via pgvector — queries the MemoryFact corpus."""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass

from pgvector.sqlalchemy import Vector
from sqlalchemy import Integer, Text, bindparam, exists, func, select, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.document_contracts import FactMetadata
from app.memory.recall import PreparedRecallQuery
from app.models.memory_batch import MemoryBatchTurn
from app.models.memory_fact import MemoryFact
from app.models.source_embedding import EmbeddingWorkState, SourceEmbedding


async def search_similar_facts(
    campaign_id: str | uuid.UUID,
    query: str,
    db: AsyncSession,
    limit: int = 3,
    query_embedding: PreparedRecallQuery | None = None,
    ancestry_turn_ids: tuple[uuid.UUID, ...] = (),
) -> list[MemoryFact]:
    """Find MemoryFacts semantically similar to the query via pgvector cosine distance.

    Pass `query_embedding` to reuse an embedding computed outside the DB session
    (rule 15) and skip the embedding API call here.
    """
    if (
        query_embedding is None
        or not ancestry_turn_ids
        or uuid.UUID(str(campaign_id)) != query_embedding.campaign_id
    ):
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
        .where(
            ~exists(
                select(1).where(
                    MemoryBatchTurn.batch_id == MemoryFact.batch_id,
                    MemoryBatchTurn.campaign_id == MemoryFact.campaign_id,
                    MemoryBatchTurn.turn_id.not_in(ancestry_turn_ids),
                )
            )
        )
        .where(
            exists(
                select(1).where(
                    MemoryBatchTurn.batch_id == MemoryFact.batch_id,
                    MemoryBatchTurn.campaign_id == MemoryFact.campaign_id,
                )
            )
        )
        .order_by(
            SourceEmbedding.embedding.cosine_distance(list(query_embedding.vectors["action"]))
        )
        .limit(limit)
    )
    return list(result.scalars().all())


@dataclass(frozen=True)
class HybridHit:
    fact_id: uuid.UUID
    content: str
    category: str | None
    assertion_type: str | None
    fact_metadata: FactMetadata | None
    score: float


_ANCESTRY_GUARD = """
    AND EXISTS (
        SELECT 1 FROM memory_batch_turns bt
        WHERE bt.batch_id = f.batch_id AND bt.campaign_id = f.campaign_id
    )
    AND NOT EXISTS (
        SELECT 1 FROM memory_batch_turns bt
        WHERE bt.batch_id = f.batch_id
          AND bt.campaign_id = f.campaign_id
          AND bt.turn_id <> ALL(:ancestry)
    )
"""

_HYBRID_SQL = text(
    """
WITH
action_dense AS (
    SELECT f.id AS fact_id,
           row_number() OVER (ORDER BY se.embedding <=> :action_vector) AS rank
    FROM memory_facts f
    JOIN source_embeddings se
      ON se.memory_fact_id = f.id AND se.campaign_id = f.campaign_id
    WHERE :use_action
      AND f.campaign_id = :campaign_id
      AND se.index_id = :index_id
      AND se.campaign_id = :campaign_id
      AND se.work_state = 'embedded'
      AND se.embedding IS NOT NULL
      AND vector_dims(se.embedding) = :dimension"""
    + _ANCESTRY_GUARD
    + """
    ORDER BY se.embedding <=> :action_vector
    LIMIT :pool
),
composed_dense AS (
    SELECT f.id AS fact_id,
           row_number() OVER (ORDER BY se.embedding <=> :composed_vector) AS rank
    FROM memory_facts f
    JOIN source_embeddings se
      ON se.memory_fact_id = f.id AND se.campaign_id = f.campaign_id
    WHERE :use_composed
      AND f.campaign_id = :campaign_id
      AND se.index_id = :index_id
      AND se.campaign_id = :campaign_id
      AND se.work_state = 'embedded'
      AND se.embedding IS NOT NULL
      AND vector_dims(se.embedding) = :dimension"""
    + _ANCESTRY_GUARD
    + """
    ORDER BY se.embedding <=> :composed_vector
    LIMIT :pool
),
lexical AS (
    SELECT f.id AS fact_id,
           row_number() OVER (
               ORDER BY ts_rank_cd(f.search_vector, to_tsquery('simple', :lexical_query)) DESC
           ) AS rank
    FROM memory_facts f
    WHERE :use_lexical
      AND f.campaign_id = :campaign_id
      AND f.search_vector @@ to_tsquery('simple', :lexical_query)"""
    + _ANCESTRY_GUARD
    + """
    LIMIT :pool
),
fused AS (
    SELECT fact_id, sum(1.0 / (:rrf_k + rank)) AS score
    FROM (
        SELECT fact_id, rank FROM action_dense
        UNION ALL SELECT fact_id, rank FROM composed_dense
        UNION ALL SELECT fact_id, rank FROM lexical
    ) candidates
    GROUP BY fact_id
)
SELECT f.id AS fact_id, f.content, f.category, f.assertion_type, f.fact_metadata, fused.score
FROM fused
JOIN memory_facts f ON f.id = fused.fact_id
ORDER BY fused.score DESC, f.id
LIMIT :pool
"""
).bindparams(
    bindparam("campaign_id", type_=PG_UUID(as_uuid=True)),
    bindparam("index_id", type_=PG_UUID(as_uuid=True)),
    bindparam("ancestry", type_=ARRAY(PG_UUID(as_uuid=True))),
    bindparam("action_vector", type_=Vector()),
    bindparam("composed_vector", type_=Vector()),
    bindparam("dimension", type_=Integer),
    bindparam("pool", type_=Integer),
    bindparam("rrf_k", type_=Integer),
    bindparam("lexical_query", type_=Text),
)


async def search_hybrid_facts(
    db: AsyncSession,
    *,
    campaign_id: uuid.UUID,
    index_id: uuid.UUID | None,
    dimension: int | None,
    vectors: Mapping[str, tuple[float, ...]],
    lexical_query: str,
    ancestry_turn_ids: tuple[uuid.UUID, ...],
    pool: int,
    rrf_k: int,
    use_action: bool = True,
    use_composed: bool = True,
    use_lexical: bool = True,
) -> list[HybridHit]:
    if not ancestry_turn_ids:
        return []
    zero = (0.0,) * (dimension or 1)
    result = await db.execute(
        _HYBRID_SQL,
        {
            "campaign_id": campaign_id,
            "index_id": index_id,
            "dimension": dimension,
            "action_vector": list(vectors.get("action", zero)),
            "composed_vector": list(vectors.get("composed", zero)),
            "ancestry": list(ancestry_turn_ids),
            "lexical_query": lexical_query,
            "pool": pool,
            "rrf_k": rrf_k,
            "use_action": use_action,
            "use_composed": use_composed,
            "use_lexical": use_lexical,
        },
    )
    return [
        HybridHit(
            fact_id=row.fact_id,
            content=row.content,
            category=row.category,
            assertion_type=row.assertion_type,
            fact_metadata=(
                FactMetadata.model_validate(row.fact_metadata) if row.fact_metadata else None
            ),
            score=float(row.score),
        )
        for row in result.mappings()
    ]
