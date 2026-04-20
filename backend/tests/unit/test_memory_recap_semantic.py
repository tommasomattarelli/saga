"""Unit tests for app/memory/recap.py and app/memory/semantic.py."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestGenerateRecap:
    @pytest.mark.asyncio
    async def test_returns_begin_message_when_no_turns(self):
        from app.memory.recap import generate_recap

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        mock_campaign = MagicMock()
        mock_campaign.id = "campaign-1"

        result = await generate_recap(mock_campaign, mock_db)
        assert result == "Your adventure is about to begin..."

    @pytest.mark.asyncio
    async def test_includes_turn_summaries(self):
        from app.memory.recap import generate_recap

        mock_turn = MagicMock()
        mock_turn.summary = "The hero slew the goblin."
        mock_turn.narration = "Long narration text here..."

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_turn]
        mock_db.execute.return_value = mock_result

        mock_campaign = MagicMock()
        mock_campaign.id = "campaign-1"

        result = await generate_recap(mock_campaign, mock_db)
        assert "When last we left our story" in result
        assert "The hero slew the goblin." in result

    @pytest.mark.asyncio
    async def test_falls_back_to_narration_when_no_summary(self):
        from app.memory.recap import generate_recap

        mock_turn = MagicMock()
        mock_turn.summary = None
        mock_turn.narration = "The player entered the cave and found treasure."

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_turn]
        mock_db.execute.return_value = mock_result

        mock_campaign = MagicMock()
        mock_campaign.id = "campaign-1"

        result = await generate_recap(mock_campaign, mock_db)
        assert "The player entered the cave" in result

    @pytest.mark.asyncio
    async def test_multiple_turns_all_included(self):
        from app.memory.recap import generate_recap

        turns = []
        for i in range(3):
            t = MagicMock()
            t.summary = f"Summary {i}"
            t.narration = f"Narration {i}"
            turns.append(t)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = turns
        mock_db.execute.return_value = mock_result

        mock_campaign = MagicMock()
        mock_campaign.id = "campaign-1"

        result = await generate_recap(mock_campaign, mock_db)
        assert "Summary 0" in result
        assert "Summary 1" in result
        assert "Summary 2" in result


class TestSearchSimilarTurns:
    @pytest.mark.asyncio
    async def test_returns_empty_list_when_embedding_is_none(self):
        from app.memory.semantic import search_similar_turns

        mock_db = AsyncMock()

        with patch("app.memory.semantic.generate_embedding", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = None
            result = await search_similar_turns("campaign-1", "dragon attack", mock_db)

        assert result == []
        mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_executes_query_when_embedding_exists(self):
        from app.memory.semantic import search_similar_turns

        mock_turn = MagicMock()
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_turn]
        mock_db.execute.return_value = mock_result

        with patch("app.memory.semantic.generate_embedding", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.1] * 1536
            result = await search_similar_turns("campaign-1", "sword fight", mock_db)

        assert result == [mock_turn]
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_list_of_turns(self):
        from app.memory.semantic import search_similar_turns

        turns = [MagicMock(), MagicMock()]
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = turns
        mock_db.execute.return_value = mock_result

        with patch("app.memory.semantic.generate_embedding", new_callable=AsyncMock) as mock_embed:
            mock_embed.return_value = [0.5] * 1536
            result = await search_similar_turns("campaign-1", "quest", mock_db, limit=2)

        assert len(result) == 2
