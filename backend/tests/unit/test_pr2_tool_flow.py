"""PR2 — Tool Flow critical tests (C3, C5, C6, I8, I9, I10)."""

from __future__ import annotations

from langchain_core.messages import AIMessage


def _make_state(**overrides) -> dict:
    base: dict = {
        "messages": [],
        "world_state": {},
        "char_data": {},
        "player_action": "look around",
        "campaign_id": "test-campaign",
        "narration": "",
        "step_count": 1,
        "consecutive_empty_steps": 0,
        "tool_events": [],
        "dice_results": [],
        "npc_dialogues": [],
        "called_npcs": [],
        "scene_mood": "neutral",
        "time_passed_minutes": 0,
        "narration_segments": [],
        "system_prompt": "",
        "model_config": {},
        "model_used": "test",
        "importance_score": 0,
        "death_event": None,
    }
    base.update(overrides)
    return base


# ── C3 — consecutive_empty_steps ─────────────────────────────────────────────

class TestConsecutiveEmptySteps:
    def test_loop_exits_after_consecutive_empty_steps_max(self):
        """route_after_tools exits when counter >= configured max (default 2)."""
        from app.core.dm.dm_graph import route_after_tools

        tc = {"id": "1", "name": "move_to", "args": {"location": "forest"}, "type": "tool_call"}
        ai_msg = AIMessage(content="", tool_calls=[tc])
        state = _make_state(
            messages=[ai_msg],
            step_count=2,
            narration="",
            consecutive_empty_steps=2,
        )
        assert route_after_tools(state) == "post_process_node"

    def test_loop_continues_before_reaching_max(self):
        """route_after_tools keeps looping when counter is still below max."""
        from app.core.dm.dm_graph import route_after_tools

        tc = {"id": "1", "name": "move_to", "args": {"location": "forest"}, "type": "tool_call"}
        ai_msg = AIMessage(content="", tool_calls=[tc])
        state = _make_state(
            messages=[ai_msg],
            step_count=1,
            narration="",
            consecutive_empty_steps=1,
        )
        assert route_after_tools(state) == "dm_node"

    async def test_tools_node_increments_counter_when_no_narration(self):
        """tools_node increments consecutive_empty_steps when narration is empty."""
        from unittest.mock import MagicMock, patch

        from app.core.dm.dm_tools_executor import tools_node

        tc = {"id": "1", "name": "log_event", "args": {"description": "x"}, "type": "tool_call"}
        ai_msg = AIMessage(content="", tool_calls=[tc])

        mock_result = MagicMock()
        mock_result.world_state = {}
        mock_result.char_data = {}
        mock_result.description = "Event logged."
        mock_result.extra = {}

        mock_tool_cls = MagicMock()
        mock_tool_cls.visible.return_value = False

        state = _make_state(messages=[ai_msg], narration="", consecutive_empty_steps=0)

        with patch("app.core.dm.dm_tools_executor.execute_tool", return_value=mock_result):
            with patch("app.core.dm.dm_tools_executor.get_tool", return_value=mock_tool_cls):
                result = await tools_node(state)

        assert result["consecutive_empty_steps"] == 1

    async def test_tools_node_resets_counter_when_narration_present(self):
        """tools_node resets consecutive_empty_steps when narration has been produced."""
        from unittest.mock import MagicMock, patch

        from app.core.dm.dm_tools_executor import tools_node

        tc = {"id": "1", "name": "log_event", "args": {"description": "x"}, "type": "tool_call"}
        ai_msg = AIMessage(content="", tool_calls=[tc])

        mock_result = MagicMock()
        mock_result.world_state = {}
        mock_result.char_data = {}
        mock_result.description = "Event logged."
        mock_result.extra = {}

        mock_tool_cls = MagicMock()
        mock_tool_cls.visible.return_value = False

        state = _make_state(
            messages=[ai_msg],
            narration="The hero steps forward.",
            consecutive_empty_steps=2,
        )

        with patch("app.core.dm.dm_tools_executor.execute_tool", return_value=mock_result):
            with patch("app.core.dm.dm_tools_executor.get_tool", return_value=mock_tool_cls):
                result = await tools_node(state)

        assert result["consecutive_empty_steps"] == 0


# ── I8 — _MEANINGFUL_TOOLS includes start_combat + end_combat ────────────────

class TestMeaningfulTools:
    def test_start_combat_triggers_loop_back(self):
        """start_combat is treated as meaningful → loop back to dm_node."""
        from app.core.dm.dm_graph import route_after_tools

        tc = {"id": "1", "name": "start_combat", "args": {}, "type": "tool_call"}
        ai_msg = AIMessage(content="", tool_calls=[tc])
        state = _make_state(messages=[ai_msg], step_count=1, narration="", consecutive_empty_steps=0)
        assert route_after_tools(state) == "dm_node"

    def test_end_combat_triggers_loop_back(self):
        """end_combat is treated as meaningful → loop back to dm_node."""
        from app.core.dm.dm_graph import route_after_tools

        tc = {"id": "1", "name": "end_combat", "args": {}, "type": "tool_call"}
        ai_msg = AIMessage(content="", tool_calls=[tc])
        state = _make_state(messages=[ai_msg], step_count=1, narration="", consecutive_empty_steps=0)
        assert route_after_tools(state) == "dm_node"


# ── C6 — NPC pre-hook ─────────────────────────────────────────────────────────

class TestNpcPrehook:
    def test_invoke_npc_absent_auto_creates_with_standard_detail(self):
        """Missing NPC is auto-created and added to world_state.npcs."""
        from app.ai.router import GameplayConfig
        from app.core.dm.npc_prehook import validate_or_create_npc

        world_state: dict = {"npcs": {}}
        config = GameplayConfig(auto_create_npcs=True, npc_auto_create_detail="standard")

        ok, error = validate_or_create_npc("Aria", world_state, config)

        assert ok is True
        assert error == ""
        assert "Aria" in world_state["npcs"]
        assert world_state["npcs"]["Aria"]["role"] == "Commoner"

    def test_invoke_npc_absent_minimal_detail(self):
        """Auto-created minimal NPC has only base fields."""
        from app.ai.router import GameplayConfig
        from app.core.dm.npc_prehook import validate_or_create_npc

        world_state: dict = {"npcs": {}}
        config = GameplayConfig(auto_create_npcs=True, npc_auto_create_detail="minimal")

        ok, _ = validate_or_create_npc("Bob", world_state, config)

        assert ok is True
        assert "role" not in world_state["npcs"]["Bob"]

    def test_invoke_npc_absent_auto_create_disabled_returns_error(self):
        """When auto_create_npcs=False, missing NPC returns (False, error)."""
        from app.ai.router import GameplayConfig
        from app.core.dm.npc_prehook import validate_or_create_npc

        world_state: dict = {"npcs": {}}
        config = GameplayConfig(auto_create_npcs=False, npc_auto_create_detail="standard")

        ok, error = validate_or_create_npc("Ghost", world_state, config)

        assert ok is False
        assert "Ghost" in error
        assert "Ghost" not in world_state["npcs"]

    def test_invoke_npc_wrong_location_skips(self):
        """NPC at different location returns (False, error) mentioning location."""
        from app.ai.router import GameplayConfig
        from app.core.dm.npc_prehook import validate_or_create_npc

        world_state = {
            "npcs": {"Guard": {"name": "Guard", "location": "Castle"}},
            "meta": {"current_location": "Tavern"},
        }
        config = GameplayConfig(auto_create_npcs=True, npc_auto_create_detail="standard")

        ok, error = validate_or_create_npc("Guard", world_state, config)

        assert ok is False
        assert "Castle" in error

    def test_invoke_npc_no_location_field_passes(self):
        """NPC without location field is not blocked (location unknown = not blocking)."""
        from app.ai.router import GameplayConfig
        from app.core.dm.npc_prehook import validate_or_create_npc

        world_state = {
            "npcs": {"Innkeeper": {"name": "Innkeeper", "role": "merchant"}},
            "meta": {"current_location": "Tavern"},
        }
        config = GameplayConfig(auto_create_npcs=True, npc_auto_create_detail="standard")

        ok, error = validate_or_create_npc("Innkeeper", world_state, config)

        assert ok is True
        assert error == ""

    def test_invoke_npc_dead_returns_error(self):
        """Dead NPC returns (False, error)."""
        from app.ai.router import GameplayConfig
        from app.core.dm.npc_prehook import validate_or_create_npc

        world_state = {"npcs": {"Elder": {"name": "Elder", "is_dead": True}}}
        config = GameplayConfig(auto_create_npcs=True, npc_auto_create_detail="standard")

        ok, error = validate_or_create_npc("Elder", world_state, config)

        assert ok is False
        assert "dead" in error.lower()


# ── I9 — tool call sort order ────────────────────────────────────────────────

class TestToolCallSortOrder:
    def test_request_dice_sorted_before_invoke_npc(self):
        """_sort_tool_calls places request_dice before invoke_npc."""
        from app.core.dm.dm_tools_executor import _sort_tool_calls

        tool_calls = [
            {"id": "1", "name": "invoke_npc", "args": {}, "type": "tool_call"},
            {"id": "2", "name": "move_to", "args": {}, "type": "tool_call"},
            {"id": "3", "name": "request_dice", "args": {}, "type": "tool_call"},
        ]
        sorted_calls = _sort_tool_calls(tool_calls)
        names = [tc["name"] for tc in sorted_calls]

        assert names[0] == "request_dice"
        assert names.index("request_dice") < names.index("invoke_npc")

    def test_other_tools_between_dice_and_npc(self):
        """Silent tools land between request_dice and invoke_npc."""
        from app.core.dm.dm_tools_executor import _sort_tool_calls

        tool_calls = [
            {"id": "1", "name": "invoke_npc", "args": {}, "type": "tool_call"},
            {"id": "2", "name": "request_dice", "args": {}, "type": "tool_call"},
        ]
        sorted_calls = _sort_tool_calls(tool_calls)
        names = [tc["name"] for tc in sorted_calls]
        assert names == ["request_dice", "invoke_npc"]


# ── I10 — sanitize tool error messages ───────────────────────────────────────

class TestToolErrorSanitized:
    def test_error_has_no_newlines(self):
        """execute_tool error description contains no newlines (no stack trace)."""
        from app.ai.tools.dm_tools import execute_tool

        result = execute_tool("update_quest", {"bad_field": "x"}, {}, {})
        assert "\n" not in result.description

    def test_error_is_truncated_to_reasonable_length(self):
        """execute_tool error description is capped at a reasonable length."""
        from app.ai.tools.dm_tools import execute_tool

        result = execute_tool("update_quest", {"bad_field": "x"}, {}, {})
        assert len(result.description) <= 200

    def test_error_does_not_contain_traceback(self):
        """execute_tool error description does not expose Python internals."""
        from app.ai.tools.dm_tools import execute_tool

        result = execute_tool("update_quest", {"bad_field": "x"}, {}, {})
        assert "Traceback" not in result.description
        assert "File " not in result.description
