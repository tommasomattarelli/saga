"""Unit tests for app/memory/semantic.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSearchSimilarFacts:
    @pytest.mark.asyncio
    async def test_returns_empty_list_when_embedding_is_none(self):
        from app.memory.semantic import search_similar_facts

        mock_db = AsyncMock()

        with patch("app.memory.semantic.generate_embedding", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = None
            result = await search_similar_facts("campaign-1", "dragon attack", mock_db)

        assert result == []
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_executes_query_when_embedding_exists(self):
        from app.memory.semantic import search_similar_facts

        mock_fact = MagicMock()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_fact]
        mock_db.execute.return_value = mock_result

        with patch("app.memory.semantic.generate_embedding", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.1] * 384
            result = await search_similar_facts("campaign-1", "sword fight", mock_db)

        assert result == [mock_fact]
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_reuses_provided_embedding_without_calling_api(self):
        # B-M1: a precomputed embedding skips the in-session embedding API call.
        from app.memory.semantic import search_similar_facts

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [MagicMock()]
        mock_db.execute.return_value = mock_result

        with patch("app.memory.semantic.generate_embedding", new_callable=AsyncMock) as mock_embed:
            result = await search_similar_facts(
                "campaign-1", "sword fight", mock_db, query_embedding=[0.2] * 384
            )

        assert len(result) == 1
        mock_embed.assert_not_called()
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_list_of_facts(self):
        from app.memory.semantic import search_similar_facts

        facts = [MagicMock(), MagicMock()]
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = facts
        mock_db.execute.return_value = mock_result

        with patch("app.memory.semantic.generate_embedding", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.5] * 384
            result = await search_similar_facts("campaign-1", "quest", mock_db, limit=2)

        assert len(result) == 2
