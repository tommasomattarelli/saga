"""Unit tests for app/memory/compressor.py."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestCompressTurnToSummary:
    @pytest.mark.asyncio
    async def test_basic_compression(self):
        from app.memory.compressor import compress_turn_to_summary

        result = await compress_turn_to_summary(
            narration="The hero entered the dungeon. It was dark.",
            player_action="enter dungeon",
        )
        assert "enter dungeon" in result
        assert "The hero entered the dungeon." in result

    @pytest.mark.asyncio
    async def test_narration_without_period_uses_truncation(self):
        from app.memory.compressor import compress_turn_to_summary

        result = await compress_turn_to_summary(
            narration="A" * 300,
            player_action="attack",
        )
        assert "attack" in result
        assert len(result) < 500

    @pytest.mark.asyncio
    async def test_long_action_is_truncated(self):
        from app.memory.compressor import compress_turn_to_summary

        long_action = "x" * 200
        result = await compress_turn_to_summary(narration="Some narration.", player_action=long_action)
        assert "x" * 100 in result


class TestShouldCompress:
    def test_active_window_returns_0(self):
        from app.memory.compressor import should_compress

        with patch("app.memory.compressor.get_gameplay_config") as mock_cfg:
            mock_cfg.return_value.context_window_turns = 10
            result = should_compress(turn_number=95, current_turn=100)
            assert result == 0

    def test_recent_outside_window_returns_1(self):
        from app.memory.compressor import should_compress

        with patch("app.memory.compressor.get_gameplay_config") as mock_cfg:
            mock_cfg.return_value.context_window_turns = 10
            result = should_compress(turn_number=60, current_turn=100)
            assert result == 1

    def test_old_turn_returns_2(self):
        from app.memory.compressor import should_compress

        with patch("app.memory.compressor.get_gameplay_config") as mock_cfg:
            mock_cfg.return_value.context_window_turns = 10
            result = should_compress(turn_number=1, current_turn=100)
            assert result == 2


class TestEnsureCompression:
    @pytest.mark.asyncio
    async def test_early_return_when_cutoff_zero(self):
        from app.memory.compressor import ensure_compression

        mock_db = AsyncMock()
        with patch("app.memory.compressor.get_gameplay_config") as mock_cfg:
            mock_cfg.return_value.context_window_turns = 100
            await ensure_compression("campaign-1", current_turn=5, db=mock_db)
            mock_db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_action_when_no_uncompressed_turns(self):
        from app.memory.compressor import ensure_compression

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        with patch("app.memory.compressor.get_gameplay_config") as mock_cfg:
            mock_cfg.return_value.context_window_turns = 5
            await ensure_compression("campaign-1", current_turn=20, db=mock_db)
            mock_db.flush.assert_not_called()

    @pytest.mark.asyncio
    async def test_heuristic_compression_when_llm_disabled(self):
        from app.memory.compressor import ensure_compression

        mock_turn = MagicMock()
        mock_turn.turn_number = 1
        mock_turn.player_action = "attack goblin"
        mock_turn.narration = "The player swings their sword."
        mock_turn.summary = None

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_turn]
        mock_db.execute.return_value = mock_result

        with patch("app.memory.compressor.get_gameplay_config") as mock_cfg:
            mock_cfg.return_value.context_window_turns = 5
            mock_cfg.return_value.compression_enabled = False
            await ensure_compression("campaign-1", current_turn=20, db=mock_db)

        assert mock_turn.summary is not None
        assert "attack goblin" in mock_turn.summary
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_llm_compression_when_enabled_and_succeeds(self):
        from app.memory.compressor import ensure_compression

        mock_turn = MagicMock()
        mock_turn.turn_number = 1
        mock_turn.player_action = "explore"
        mock_turn.narration = "The player explores the forest."
        mock_turn.summary = None

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_turn]
        mock_db.execute.return_value = mock_result

        with patch("app.memory.compressor.get_gameplay_config") as mock_cfg:
            mock_cfg.return_value.context_window_turns = 5
            mock_cfg.return_value.compression_enabled = True
            with patch("app.memory.compressor.compress_turns_batch_llm", new_callable=AsyncMock) as mock_llm:
                mock_llm.return_value = "Player explored the forest."
                await ensure_compression("campaign-1", current_turn=20, db=mock_db)

        assert mock_turn.summary == "Player explored the forest."
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    async def test_heuristic_fallback_when_llm_returns_none(self):
        from app.memory.compressor import ensure_compression

        mock_turn = MagicMock()
        mock_turn.turn_number = 1
        mock_turn.player_action = "cast spell"
        mock_turn.narration = "Magic fills the air."
        mock_turn.summary = None

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_turn]
        mock_db.execute.return_value = mock_result

        with patch("app.memory.compressor.get_gameplay_config") as mock_cfg:
            mock_cfg.return_value.context_window_turns = 5
            mock_cfg.return_value.compression_enabled = True
            with patch("app.memory.compressor.compress_turns_batch_llm", new_callable=AsyncMock) as mock_llm:
                mock_llm.return_value = None
                await ensure_compression("campaign-1", current_turn=20, db=mock_db)

        assert mock_turn.summary is not None
        assert "cast spell" in mock_turn.summary


class TestCompressTurnsBatchLlm:
    @pytest.mark.asyncio
    async def test_returns_stripped_text_on_success(self):
        from app.memory.compressor import compress_turns_batch_llm

        mock_turn = MagicMock()
        mock_turn.turn_number = 1
        mock_turn.player_action = "fight dragon"
        mock_turn.narration = "The dragon breathes fire."

        mock_model_cfg = MagicMock()
        mock_model_cfg.provider = "openai"
        mock_model_cfg.model = "gpt-4o-mini"

        with patch("app.memory.compressor.route_ai_call", new_callable=AsyncMock) as mock_route:
            mock_route.return_value = mock_model_cfg
            with patch("app.ai.providers.base.get_provider", return_value=MagicMock()):
                with patch("app.ai.providers.base.logged_generate", new_callable=AsyncMock) as mock_gen:
                    mock_gen.return_value = "  Summary text.  "
                    result = await compress_turns_batch_llm([mock_turn])

        assert result == "Summary text."

    @pytest.mark.asyncio
    async def test_returns_none_when_logged_generate_raises(self):
        from app.memory.compressor import compress_turns_batch_llm

        mock_turn = MagicMock()
        mock_turn.turn_number = 1
        mock_turn.player_action = "run"
        mock_turn.narration = "Player runs away."

        mock_model_cfg = MagicMock()
        mock_model_cfg.provider = "openai"
        mock_model_cfg.model = "gpt-4o-mini"

        with patch("app.memory.compressor.route_ai_call", new_callable=AsyncMock) as mock_route:
            mock_route.return_value = mock_model_cfg
            with patch("app.ai.providers.base.get_provider", return_value=MagicMock()):
                with patch("app.ai.providers.base.logged_generate", new_callable=AsyncMock) as mock_gen:
                    mock_gen.side_effect = RuntimeError("LLM error")
                    result = await compress_turns_batch_llm([mock_turn])

        assert result is None
