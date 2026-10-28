"""Unit tests for tools_node in app/core/dm/dm_tools_executor.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage


def _make_state(**overrides) -> dict:
    base: dict = {
        "messages": [],
        "world_state": {},
        "char_data": {},
        "player_action": "attack",
        "campaign_id": "test-campaign-id",
        "narration": "",
        "step_count": 1,
        "tool_events": [],
        "dice_results": [],
        "npc_beats": [],
        "npc_lines": [],
        "user_id": "11111111-1111-1111-1111-111111111111",
        "scene_mood": "neutral",
        "time_passed_minutes": 0,
        "narration_segments": [],
        "system_prompt": "",
        "model_config": {},
        "model_used": "gpt-4",
        "importance_score": 0,
        "death_event": None,
    }
    base.update(overrides)
    return base


class TestToolsNodeNoMessages:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_ai_message(self):
        from app.core.dm.dm_tools_executor import tools_node

        state = _make_state(messages=[])
        result = await tools_node(state)
        assert result == {}

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_tool_calls(self):
        from app.core.dm.dm_tools_executor import tools_node

        ai_msg = AIMessage(content="Just narration", tool_calls=[])
        state = _make_state(messages=[ai_msg])
        result = await tools_node(state)
        assert result == {}


class TestToolsNodeRequestDice:
    @pytest.mark.asyncio
    async def test_request_dice_adds_to_dice_results(self):
        from app.core.dm.dm_tools_executor import tools_node

        tc = {
            "id": "tc1",
            "name": "request_dice",
            "args": {"difficulty": "hard", "stat": "STR", "check": "Athletics"},
            "type": "tool_call",
        }
        ai_msg = AIMessage(content="", tool_calls=[tc])

        state = _make_state(messages=[ai_msg], char_data={"abilities": {"STR": 10}})
        result = await tools_node(state)

        assert len(result["dice_results"]) == 1
        assert result["dice_results"][0]["step"] == 0  # step_count - 1


class TestToolsNodeRegularTool:
    @pytest.mark.asyncio
    async def test_regular_tool_execution(self):
        from app.core.dm.dm_tools_executor import tools_node

        tc = {
            "id": "tc1",
            "name": "set_scene_mood",
            "args": {"mood": "dread_horror"},
            "type": "tool_call",
        }
        ai_msg = AIMessage(content="", tool_calls=[tc])

        mock_tool_result = MagicMock()
        mock_tool_result.world_state = {"weather": "rainy"}
        mock_tool_result.char_data = {}
        mock_tool_result.description = "World updated."
        mock_tool_result.extra = {}

        mock_tool_cls = MagicMock()
        mock_tool_cls.visible.return_value = False

        state = _make_state(messages=[ai_msg])

        with (
            patch("app.core.dm.dm_tools_executor.execute_tool", return_value=mock_tool_result),
            patch("app.core.dm.dm_tools_executor.get_tool", return_value=mock_tool_cls),
        ):
            result = await tools_node(state)

        assert result["world_state"] == {"weather": "rainy"}
        messages = result["messages"]
        assert any(m.content == "World updated." for m in messages)

    @pytest.mark.asyncio
    async def test_set_scene_mood_tool_updates_mood(self):
        from app.core.dm.dm_tools_executor import tools_node

        tc = {
            "id": "tc1",
            "name": "set_scene_mood",
            "args": {"mood": "tense"},
            "type": "tool_call",
        }
        ai_msg = AIMessage(content="", tool_calls=[tc])

        mock_tool_result = MagicMock()
        mock_tool_result.world_state = {}
        mock_tool_result.char_data = {}
        mock_tool_result.description = "Mood set."
        mock_tool_result.extra = {"mood": "tense"}

        mock_tool_cls = MagicMock()
        mock_tool_cls.visible.return_value = False

        state = _make_state(messages=[ai_msg])

        with (
            patch("app.core.dm.dm_tools_executor.execute_tool", return_value=mock_tool_result),
            patch("app.core.dm.dm_tools_executor.get_tool", return_value=mock_tool_cls),
        ):
            result = await tools_node(state)

        assert result["scene_mood"] == "tense"

    @pytest.mark.asyncio
    async def test_advance_time_tool_adds_minutes(self):
        from app.core.dm.dm_tools_executor import tools_node

        tc = {"id": "tc1", "name": "advance_time", "args": {"minutes": 30}, "type": "tool_call"}
        ai_msg = AIMessage(content="", tool_calls=[tc])

        state = _make_state(
            messages=[ai_msg],
            time_passed_minutes=10,
            world_state={"clock": {"total_minutes": 490}},
        )
        result = await tools_node(state)

        assert result["time_passed_minutes"] == 40
        assert result["world_state"]["clock"]["total_minutes"] == 520

    @pytest.mark.asyncio
    async def test_visible_tool_added_to_tool_events(self):
        from app.core.dm.dm_tools_executor import tools_node

        tc = {"id": "tc1", "name": "add_item", "args": {"name": "sword"}, "type": "tool_call"}
        ai_msg = AIMessage(content="", tool_calls=[tc])

        mock_tool_result = MagicMock()
        mock_tool_result.world_state = {}
        mock_tool_result.char_data = {}
        mock_tool_result.description = "Item given."
        mock_tool_result.extra = {"item": "sword"}

        mock_tool_cls = MagicMock()
        mock_tool_cls.visible.return_value = True

        state = _make_state(messages=[ai_msg])

        with (
            patch("app.core.dm.dm_tools_executor.execute_tool", return_value=mock_tool_result),
            patch("app.core.dm.dm_tools_executor.get_tool", return_value=mock_tool_cls),
        ):
            result = await tools_node(state)

        assert len(result["tool_events"]) == 1
        assert result["tool_events"][0]["tool"] == "add_item"


class TestToolsNodeInvokeNpc:
    @pytest.mark.asyncio
    async def test_invoke_npc_adds_public_beat_and_lines(self):
        from app.core.dm.dm_tools_executor import tools_node

        tc = {
            "id": "tc1",
            "name": "invoke_npc",
            "args": {"name": "Guard", "context": "looking at gate"},
            "type": "tool_call",
        }
        ai_msg = AIMessage(content="", tool_calls=[tc])

        from app.ai.npc_outcomes import NPCSpeaking

        state = _make_state(
            messages=[ai_msg],
            world_state={
                "meta": {"current_location": "gate"},
                "npcs": {"guard-id": {"name": "Guard", "location": "gate", "psychology": {}}},
            },
        )
        with patch(
            "app.core.dm.npc_beat.invoke_npcs_parallel",
            new_callable=AsyncMock,
            return_value=[NPCSpeaking("Guard", ("Stop right there!",))],
        ):
            result = await tools_node(state)
        assert result["npc_beats"][0].results[0].npc_name == "Guard"
        assert result["npc_beats"][0].results[0].lines == ("Stop right there!",)
        assert result["npc_lines"][0].part.dialogue == "Stop right there!"
