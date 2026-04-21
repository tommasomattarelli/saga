"""Unit tests for app/memory/global_summary.py."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_db_chain(campaign, turns):
    """Build a MagicMock AsyncSession whose two execute() calls return campaign then turns."""
    campaign_result = MagicMock()
    campaign_result.scalar_one_or_none.return_value = campaign

    turns_scalars = MagicMock()
    turns_scalars.all.return_value = turns
    turns_result = MagicMock()
    turns_result.scalars.return_value = turns_scalars

    db = AsyncMock()
    db.execute = AsyncMock(side_effect=[campaign_result, turns_result])
    return db


def _mock_cfg(enabled=True, interval=5):
    cfg = MagicMock()
    cfg.global_summary_enabled = enabled
    cfg.global_summary_update_every = interval
    return cfg


class TestUpdateGlobalSummary:
    @pytest.mark.asyncio
    async def test_noop_when_disabled(self):
        from app.memory.global_summary import update_global_summary

        db = AsyncMock()
        with patch("app.memory.global_summary.get_gameplay_config", return_value=_mock_cfg(enabled=False)):
            result = await update_global_summary(uuid.uuid4(), 5, db)

        assert result is None
        db.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_noop_when_campaign_missing(self):
        from app.memory.global_summary import update_global_summary

        campaign_result = MagicMock()
        campaign_result.scalar_one_or_none.return_value = None
        db = AsyncMock()
        db.execute = AsyncMock(return_value=campaign_result)

        with patch("app.memory.global_summary.get_gameplay_config", return_value=_mock_cfg()):
            result = await update_global_summary(uuid.uuid4(), 5, db)

        assert result is None

    @pytest.mark.asyncio
    async def test_uses_initial_prompt_when_no_existing_summary(self):
        from app.memory.global_summary import update_global_summary

        campaign = MagicMock()
        campaign.global_summary = None
        turn = MagicMock(turn_number=1, player_action="start", narration="You begin.")
        db = _mock_db_chain(campaign, [turn])

        with patch("app.memory.global_summary.get_gameplay_config", return_value=_mock_cfg()), \
             patch("app.memory.global_summary._generate_summary", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "The hero's adventure begins."
            result = await update_global_summary(uuid.uuid4(), 5, db)

        assert result == "The hero's adventure begins."
        assert campaign.global_summary == "The hero's adventure begins."
        # First call's prompt contains the INITIAL marker (no "Existing summary:" block)
        prompt_arg = mock_gen.call_args[0][0]
        assert "Existing summary:" not in prompt_arg

    @pytest.mark.asyncio
    async def test_uses_update_prompt_when_existing_summary(self):
        from app.memory.global_summary import update_global_summary

        campaign = MagicMock()
        campaign.global_summary = "Previous arc: the hero met the witch."
        turn = MagicMock(turn_number=6, player_action="attack", narration="Blades clash.")
        db = _mock_db_chain(campaign, [turn])

        with patch("app.memory.global_summary.get_gameplay_config", return_value=_mock_cfg()), \
             patch("app.memory.global_summary._generate_summary", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "Extended summary covering the new battle."
            result = await update_global_summary(uuid.uuid4(), 10, db)

        assert result == "Extended summary covering the new battle."
        prompt_arg = mock_gen.call_args[0][0]
        assert "Existing summary:" in prompt_arg
        assert "Previous arc" in prompt_arg

    @pytest.mark.asyncio
    async def test_returns_none_when_llm_fails(self):
        from app.memory.global_summary import update_global_summary

        campaign = MagicMock()
        campaign.global_summary = None
        turn = MagicMock(turn_number=1, player_action="x", narration="y")
        db = _mock_db_chain(campaign, [turn])

        with patch("app.memory.global_summary.get_gameplay_config", return_value=_mock_cfg()), \
             patch("app.memory.global_summary._generate_summary", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = None
            result = await update_global_summary(uuid.uuid4(), 5, db)

        assert result is None
        # Summary stays None — no partial write
        assert campaign.global_summary is None

    @pytest.mark.asyncio
    async def test_batch_respects_interval_window(self):
        from app.memory.global_summary import update_global_summary

        campaign = MagicMock()
        campaign.global_summary = None

        # Capture the turn query params
        captured = {}

        class FakeDb:
            async def execute(self, query):
                # Track which execute() call this is and inspect it
                captured.setdefault("calls", []).append(str(query))
                if len(captured["calls"]) == 1:
                    # Campaign lookup
                    r = MagicMock()
                    r.scalar_one_or_none.return_value = campaign
                    return r
                # Turns lookup
                scalars = MagicMock()
                scalars.all.return_value = [MagicMock(turn_number=10, player_action="a", narration="b")]
                r = MagicMock()
                r.scalars.return_value = scalars
                return r

            async def flush(self):
                pass

        db = FakeDb()
        with patch("app.memory.global_summary.get_gameplay_config", return_value=_mock_cfg(interval=5)), \
             patch("app.memory.global_summary._generate_summary", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "ok"
            await update_global_summary(uuid.uuid4(), 10, db)

        # Query was issued (batch bound to [6..10])
        assert len(captured["calls"]) == 2
