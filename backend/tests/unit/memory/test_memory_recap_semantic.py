from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ai.embedding_config import legacy_space
from app.memory.recall import PreparedRecallQuery


@pytest.mark.asyncio
async def test_sql_recall_does_not_embed_missing_query() -> None:
    from app.memory.semantic import search_similar_facts

    db = AsyncMock()
    assert await search_similar_facts(uuid.uuid4(), "query", db) == []
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_sql_recall_uses_prepared_index_query() -> None:
    from app.memory.semantic import search_similar_facts

    campaign_id, index_id = uuid.uuid4(), uuid.uuid4()
    fact = MagicMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [fact]
    db = AsyncMock()
    db.execute.return_value = result
    prepared = PreparedRecallQuery(
        uuid.uuid4(), campaign_id, index_id, legacy_space(), 384, (0.25,) * 384
    )

    assert await search_similar_facts(campaign_id, "query", db, query_embedding=prepared) == [fact]
    db.execute.assert_awaited_once()
