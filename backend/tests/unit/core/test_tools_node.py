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
        "npc_dialogues": [],
        "called_npcs": [],
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


class TestToolsNodeEndCombat:
    @pytest.mark.asyncio
    async def test_end_combat_resets_combat_state(self):
        from app.core.dm.dm_tools_executor import tools_node

        tc = {"id": "tc1", "name": "end_combat", "args": {}, "type": "tool_call"}
        ai_msg = AIMessage(content="", tool_calls=[tc])

        mock_tool_cls = MagicMock()
        mock_tool_cls.visible.return_value = True

        state = _make_state(
            messages=[ai_msg],
            world_state={"combat_state": {"active": True}},
        )

        with patch("app.core.dm.dm_tools_executor.get_tool", return_value=mock_tool_cls):
            result = await tools_node(state)

        assert result["world_state"]["combat_state"]["active"] is False
        assert result["world_state"]["combat_state"]["round"] == 0

    @pytest.mark.asyncio
    async def test_end_combat_adds_to_tool_events_when_visible(self):
        from app.core.dm.dm_tools_executor import tools_node

        tc = {"id": "tc1", "name": "end_combat", "args": {}, "type": "tool_call"}
        ai_msg = AIMessage(content="", tool_calls=[tc])

        mock_tool_cls = MagicMock()
        mock_tool_cls.visible.return_value = True

        state = _make_state(messages=[ai_msg])

        with patch("app.core.dm.dm_tools_executor.get_tool", return_value=mock_tool_cls):
            result = await tools_node(state)

        assert len(result["tool_events"]) == 1
        assert result["tool_events"][0]["tool"] == "end_combat"


class TestToolsNodeRequestDice:
    @pytest.mark.asyncio
    async def test_request_dice_adds_to_dice_results(self):
        from app.core.dm.dm_tools_executor import tools_node

        tc = {
            "id": "tc1",
            "name": "request_dice",
            "args": {"dc": 12, "stat": "STR"},
            "type": "tool_call",
        }
        ai_msg = AIMessage(content="", tool_calls=[tc])

        mock_roll = MagicMock()
        mock_roll.expression = "1d20"
        mock_roll.rolls = [10]
        mock_roll.modifier = 0
        mock_roll.total = 10

        mock_dice_result = {
            "roll": mock_roll,
            "success": False,
            "outcome": "failure",
            "is_critical": False,
        }

        state = _make_state(messages=[ai_msg], char_data={"abilities": {"STR": 10}})

        with patch("app.core.dm.dm_tools_executor.ability_check", return_value=mock_dice_result):
            result = await tools_node(state)

        assert len(result["dice_results"]) == 1
        assert result["dice_results"][0]["step"] == 0  # step_count - 1


class TestToolsNodeRegularTool:
    @pytest.mark.asyncio
    async def test_regular_tool_execution(self):
        from app.core.dm.dm_tools_executor import tools_node

        tc = {
            "id": "tc1",
            "name": "update_world",
            "args": {"key": "weather", "value": "rainy"},
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

        mock_tool_result = MagicMock()
        mock_tool_result.world_state = {}
        mock_tool_result.char_data = {}
        mock_tool_result.description = "Time advanced."
        mock_tool_result.extra = {}

        mock_tool_cls = MagicMock()
        mock_tool_cls.visible.return_value = False

        state = _make_state(messages=[ai_msg], time_passed_minutes=10)

        with (
            patch("app.core.dm.dm_tools_executor.execute_tool", return_value=mock_tool_result),
            patch("app.core.dm.dm_tools_executor.get_tool", return_value=mock_tool_cls),
        ):
            result = await tools_node(state)

        assert result["time_passed_minutes"] == 40

    @pytest.mark.asyncio
    async def test_visible_tool_added_to_tool_events(self):
        from app.core.dm.dm_tools_executor import tools_node

        tc = {"id": "tc1", "name": "give_item", "args": {"item": "sword"}, "type": "tool_call"}
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
        assert result["tool_events"][0]["tool"] == "give_item"


class TestToolsNodeStartCombat:
    @pytest.mark.asyncio
    async def test_start_combat_invokes_combat_graph(self):
        from app.core.dm.dm_tools_executor import tools_node

        tc = {
            "id": "tc1",
            "name": "start_combat",
            "args": {"enemies": [{"name": "Goblin", "hp": 8}]},
            "type": "tool_call",
        }
        ai_msg = AIMessage(content="", tool_calls=[tc])

        mock_combat_result = {
            "world_state": {
                "combat_state": {
                    "active": True,
                    "round": 1,
                    "initiative_order": [],
                    "current_turn_index": 0,
                }
            }
        }

        mock_tool_cls = MagicMock()
        mock_tool_cls.visible.return_value = True

        state = _make_state(messages=[ai_msg])

        with patch("app.core.dm.dm_tools_executor.combat_graph") as mock_combat_graph:
            mock_combat_graph.ainvoke = AsyncMock(return_value=mock_combat_result)
            with patch("app.core.dm.dm_tools_executor.get_tool", return_value=mock_tool_cls):
                result = await tools_node(state)

        assert result["world_state"]["combat_state"]["active"] is True
        messages = result["messages"]
        assert any("Combat" in m.content for m in messages)

    @pytest.mark.asyncio
    async def test_start_combat_tool_event_added_when_visible(self):
        from app.core.dm.dm_tools_executor import tools_node

        tc = {"id": "tc1", "name": "start_combat", "args": {"enemies": []}, "type": "tool_call"}
        ai_msg = AIMessage(content="", tool_calls=[tc])

        mock_combat_result = {"world_state": {"combat_state": {"active": True}}}

        mock_tool_cls = MagicMock()
        mock_tool_cls.visible.return_value = True

        state = _make_state(messages=[ai_msg])

        with patch("app.core.dm.dm_tools_executor.combat_graph") as mock_combat_graph:
            mock_combat_graph.ainvoke = AsyncMock(return_value=mock_combat_result)
            with patch("app.core.dm.dm_tools_executor.get_tool", return_value=mock_tool_cls):
                result = await tools_node(state)

        assert len(result["tool_events"]) == 1
        assert result["tool_events"][0]["tool"] == "start_combat"


class TestToolsNodeInvokeNpc:
    @pytest.mark.asyncio
    async def test_already_called_npc_returns_early_message(self):
        from app.core.dm.dm_tools_executor import tools_node

        tc = {"id": "tc1", "name": "invoke_npc", "args": {"name": "Aria"}, "type": "tool_call"}
        ai_msg = AIMessage(content="", tool_calls=[tc])

        state = _make_state(messages=[ai_msg], called_npcs=["Aria"])
        result = await tools_node(state)

        messages = result["messages"]
        assert any("already spoken" in m.content for m in messages)

    @pytest.mark.asyncio
    async def test_invoke_npc_calls_npc_director(self):
        from app.core.dm.dm_tools_executor import tools_node

        tc = {
            "id": "tc1",
            "name": "invoke_npc",
            "args": {"name": "Guard", "context": "looking at gate"},
            "type": "tool_call",
        }
        ai_msg = AIMessage(content="", tool_calls=[tc])

        mock_npc_result = MagicMock()
        mock_npc_result.npc_name = "Guard"
        mock_npc_result.dialogue = "Stop right there!"
        mock_npc_result.action = None
        mock_npc_result.disposition_change = 0

        mock_campaign = MagicMock()

        mock_db = AsyncMock()
        mock_db_result = MagicMock()
        mock_db_result.scalar_one.return_value = mock_campaign
        mock_db.execute.return_value = mock_db_result

        mock_ctx = MagicMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_db)
        mock_ctx.__aexit__ = AsyncMock(return_value=False)

        state = _make_state(messages=[ai_msg])

        with patch(
            "app.core.dm.dm_tools_executor.invoke_npcs_parallel", new_callable=AsyncMock
        ) as mock_npc:
            mock_npc.return_value = [mock_npc_result]
            with patch("app.dependencies.get_db_context", return_value=mock_ctx):
                result = await tools_node(state)

        assert "Guard" in result["called_npcs"]
        assert len(result["npc_dialogues"]) == 1
