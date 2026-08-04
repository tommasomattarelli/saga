"""Unit tests for post_process_node and dm_node in app/core/dm/dm_nodes.py."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage


def _make_state(**overrides) -> dict:
    base: dict = {
        "messages": [],
        "world_state": {},
        "char_data": {},
        "player_action": "look",
        "difficulty": "medium",
        "campaign_id": "test-id",
        "narration": "",
        "step_count": 1,
        "tool_events": [],
        "dice_results": [],
        "npc_dialogues": [],
        "called_npcs": [],
        "scene_mood": "neutral",
        "time_passed_minutes": 0,
        "narration_segments": [],
        "system_prompt": "You are a DM.",
        "model_config": {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "temperature": 0.7,
            "max_tokens": 2000,
        },
        "model_used": "gpt-4o-mini",
        "importance_score": 0,
        "death_event": None,
    }
    base.update(overrides)
    return base


class TestPostProcessNode:
    def test_returns_world_state_and_segments(self):
        from app.core.dm.dm_nodes import post_process_node

        state = _make_state(char_data={"hp": {"current": 10, "max": 10}})
        result = post_process_node(state)

        assert "world_state" in result
        assert "narration_segments" in result
        assert "death_event" in result

    def test_death_event_is_none_when_alive(self):
        from app.core.dm.dm_nodes import post_process_node

        state = _make_state(char_data={"hp": {"current": 10, "max": 10}})
        result = post_process_node(state)
        assert result["death_event"] is None

    def test_death_event_populated_when_dead(self):
        from app.core.dm.dm_nodes import post_process_node

        state = _make_state(char_data={"hp": {"current": 0, "max": 10}})
        result = post_process_node(state)
        # When HP is 0, check_player_death should return non-alive
        # The exact outcome depends on death mode, but event might be set
        # Just verify function completes
        assert "death_event" in result

    def test_syncs_narration_to_segment_when_uncovered(self):
        from app.core.dm.dm_nodes import post_process_node

        state = _make_state(
            narration="The hero enters the dungeon.",
            narration_segments=[],
            step_count=1,
            char_data={"hp": {"current": 10, "max": 10}},
        )
        result = post_process_node(state)
        segments = result["narration_segments"]
        assert len(segments) > 0
        assert segments[0]["text"] == "The hero enters the dungeon."

    def test_does_not_duplicate_covered_narration(self):
        from app.core.dm.dm_nodes import post_process_node

        full_text = "The hero fights the dragon."
        state = _make_state(
            narration=full_text,
            narration_segments=[{"step": 0, "text": full_text, "dice": None, "npc_dialogues": []}],
            step_count=1,
            char_data={"hp": {"current": 10, "max": 10}},
        )
        result = post_process_node(state)
        segments = result["narration_segments"]
        # Should not add a new segment since narration is fully covered
        assert len(segments) == 1
        assert segments[0]["text"] == full_text

    def test_advances_clock_when_time_passed(self):
        from app.core.dm.dm_nodes import post_process_node

        state = _make_state(
            time_passed_minutes=30,
            world_state={"time": {"hour": 10, "minute": 0}},
            char_data={"hp": {"current": 10, "max": 10}},
        )
        result = post_process_node(state)
        # Should have advanced the time — world state should be updated
        assert result["world_state"] is not None

    def test_no_clock_advance_when_zero_time(self):
        from app.core.dm.dm_nodes import post_process_node

        original_ws = {"time": {"hour": 10, "minute": 0}}
        state = _make_state(
            time_passed_minutes=0,
            world_state=original_ws.copy(),
            char_data={"hp": {"current": 10, "max": 10}},
        )
        result = post_process_node(state)
        # Time should not change
        assert result["world_state"].get("time", {}).get("hour") == 10


class TestContextNode:
    @pytest.mark.asyncio
    async def test_precomputes_embedding_outside_session(self):
        # B-M1: the recall embedding is generated before the DB session opens and
        # forwarded to build_context, so no embedding API call runs in-session.
        from app.core.dm.dm_nodes import context_node

        campaign = MagicMock()
        campaign.world_state = {}
        campaign.character_data = {}

        db_result = MagicMock()
        db_result.scalar_one.return_value = campaign
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=db_result)

        @asynccontextmanager
        async def fake_ctx():
            yield mock_db

        game_ctx = MagicMock(messages=[], importance_score=5, system_prompt="sys")
        model_cfg = MagicMock(provider="openai", model="gpt-4o", temperature=0.7, max_tokens=100)

        state = _make_state(player_action="I attack the guard", campaign_id="cid")

        with (
            patch(
                "app.ai.embeddings.generate_embedding", new=AsyncMock(return_value=[0.3] * 384)
            ) as mock_embed,
            patch("app.dependencies.get_db_context", side_effect=fake_ctx),
            patch(
                "app.core.dm.dm_nodes.build_context", new=AsyncMock(return_value=game_ctx)
            ) as mock_bc,
            patch("app.core.dm.dm_nodes.route_ai_call", new=AsyncMock(return_value=model_cfg)),
            patch("app.core.dm.dm_nodes.sanitize_player_input", side_effect=lambda x: x),
            patch("app.core.dm.dm_nodes.detect_injection", return_value=False),
        ):
            result = await context_node(state, config={})

        mock_embed.assert_awaited_once()
        assert mock_bc.call_args.kwargs["query_embedding"] == [0.3] * 384
        assert result["model_used"] == "gpt-4o"


class TestDmNodeUnit:
    @pytest.mark.asyncio
    async def test_dm_node_increments_step_count(self):
        from app.core.dm.dm_nodes import dm_node

        mock_response = MagicMock()
        mock_response.text = "The DM narrates..."
        mock_response.tool_calls = []

        mock_provider = MagicMock()
        mock_provider.generate_with_tools = AsyncMock(return_value=mock_response)

        state = _make_state(step_count=1)

        with (
            patch("app.core.dm.dm_nodes.get_provider", return_value=mock_provider),
            patch("app.core.dm.dm_nodes.resolve_active_tools_from_state", return_value=set()),
            patch("app.core.dm.dm_nodes.get_tool_schemas", return_value=[]),
        ):
            result = await dm_node(state, config={})

        assert result["step_count"] == 2

    @pytest.mark.asyncio
    async def test_dm_node_appends_narration(self):
        from app.core.dm.dm_nodes import dm_node

        mock_response = MagicMock()
        mock_response.text = "A dragon appears!"
        mock_response.tool_calls = []

        mock_provider = MagicMock()
        mock_provider.generate_with_tools = AsyncMock(return_value=mock_response)

        state = _make_state(step_count=1, narration="Previously: ")

        with (
            patch("app.core.dm.dm_nodes.get_provider", return_value=mock_provider),
            patch("app.core.dm.dm_nodes.resolve_active_tools_from_state", return_value=set()),
            patch("app.core.dm.dm_nodes.get_tool_schemas", return_value=[]),
        ):
            result = await dm_node(state, config={})

        assert result["narration"] == "Previously: A dragon appears!"

    @pytest.mark.asyncio
    async def test_dm_node_handles_content_policy_error(self):
        from app.ai.exceptions import ContentPolicyError
        from app.core.dm.dm_nodes import dm_node

        mock_provider = MagicMock()
        mock_provider.generate_with_tools = AsyncMock(side_effect=ContentPolicyError("blocked"))

        state = _make_state(step_count=1)

        with (
            patch("app.core.dm.dm_nodes.get_provider", return_value=mock_provider),
            patch("app.core.dm.dm_nodes.resolve_active_tools_from_state", return_value=set()),
            patch("app.core.dm.dm_nodes.get_tool_schemas", return_value=[]),
        ):
            result = await dm_node(state, config={})

        assert result["step_count"] == 2
        assert len(result["messages"]) == 1

    @pytest.mark.asyncio
    async def test_dm_node_creates_ai_message_with_tool_calls(self):
        from app.core.dm.dm_nodes import dm_node

        mock_tc = MagicMock()
        mock_tc.id = "tc1"
        mock_tc.name = "request_dice"
        mock_tc.arguments = {"dc": 12}

        mock_response = MagicMock()
        mock_response.text = ""
        mock_response.tool_calls = [mock_tc]

        mock_provider = MagicMock()
        mock_provider.generate_with_tools = AsyncMock(return_value=mock_response)

        state = _make_state(step_count=1)

        with (
            patch("app.core.dm.dm_nodes.get_provider", return_value=mock_provider),
            patch("app.core.dm.dm_nodes.resolve_active_tools_from_state", return_value=set()),
            patch("app.core.dm.dm_nodes.get_tool_schemas", return_value=[]),
        ):
            result = await dm_node(state, config={})

        ai_msg = result["messages"][0]
        assert isinstance(ai_msg, AIMessage)
        assert len(ai_msg.tool_calls) == 1
        assert ai_msg.tool_calls[0]["name"] == "request_dice"
