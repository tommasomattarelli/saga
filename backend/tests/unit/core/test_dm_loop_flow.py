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
        "npc_beats": [],
        "npc_lines": [],
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
    def test_stalls_force_a_closing_call_instead_of_cutting_off_results(self):
        from app.core.dm.dm_graph import route_after_tools

        tc = {"id": "1", "name": "move_to", "args": {"location": "forest"}, "type": "tool_call"}
        ai_msg = AIMessage(content="", tool_calls=[tc])
        state = _make_state(
            messages=[ai_msg],
            step_count=2,
            narration="",
            consecutive_empty_steps=2,
        )
        from app.core.dm.loop_policy import closing_step

        assert route_after_tools(state) == "dm_node"
        assert closing_step(state)

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

        with (
            patch("app.core.dm.dm_tools_executor.execute_tool", return_value=mock_result),
            patch("app.core.dm.dm_tools_executor.get_tool", return_value=mock_tool_cls),
        ):
            result = await tools_node(state)

        assert result["consecutive_empty_steps"] == 1

    async def test_prose_cannot_hide_no_progress_tools(self):
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

        with (
            patch("app.core.dm.dm_tools_executor.execute_tool", return_value=mock_result),
            patch("app.core.dm.dm_tools_executor.get_tool", return_value=mock_tool_cls),
        ):
            result = await tools_node(state)

        assert result["consecutive_empty_steps"] == 3


# ── Every non-terminal-safe tool gets result narration ─────────────────────


class TestMeaningfulTools:
    def test_move_to_triggers_loop_back(self):
        from app.core.dm.dm_graph import route_after_tools

        tc = {"id": "1", "name": "move_to", "args": {}, "type": "tool_call"}
        ai_msg = AIMessage(content="", tool_calls=[tc])
        state = _make_state(
            messages=[ai_msg], step_count=1, narration="", consecutive_empty_steps=0
        )
        assert route_after_tools(state) == "dm_node"

    def test_update_quest_triggers_loop_back(self):
        from app.core.dm.dm_graph import route_after_tools

        tc = {"id": "1", "name": "update_quest", "args": {}, "type": "tool_call"}
        ai_msg = AIMessage(content="", tool_calls=[tc])
        state = _make_state(
            messages=[ai_msg], step_count=1, narration="", consecutive_empty_steps=0
        )
        assert route_after_tools(state) == "dm_node"


# ── C6 — NPC pre-hook ─────────────────────────────────────────────────────────


class TestNpcPrehook:
    def test_prepares_created_npc_and_seeds_baseline_taxonomy(self):
        from app.ai.router import GameplayConfig
        from app.core.dm.npc_prehook import prepare_npc_calls

        world_state = {"meta": {"current_location": "square"}, "npcs": {}}
        baseline = {
            "taxonomy": {
                "psychology": {
                    "axes": {
                        "honor": {
                            "range": [-50, 50],
                            "default": 10,
                            "bands": [
                                {"min": -50, "label": "shamed"},
                                {"min": 0, "label": "honored"},
                            ],
                        }
                    }
                }
            }
        }
        prepared, notes = prepare_npc_calls(
            [{"id": "one", "args": {"name": "Kira", "context": "nearby"}}],
            world_state,
            GameplayConfig(auto_create_npcs=True, npc_auto_create_detail="standard"),
            baseline,
        )
        assert not notes
        assert len(prepared) == 1
        kira = world_state["npcs"][prepared[0].npc_id]
        assert prepared[0].name == "Kira"
        assert kira["psychology"] == {"honor": 10}
        assert kira["location"] == "square"

    def test_rejects_missing_disabled_and_wrong_location_npcs(self):
        from app.ai.router import GameplayConfig
        from app.core.dm.npc_prehook import prepare_npc_calls

        world_state = {
            "meta": {"current_location": "Tavern"},
            "npcs": {
                "guard-id": {"name": "Guard", "location": "Castle"},
            },
        }
        prepared, notes = prepare_npc_calls(
            [
                {"id": "missing", "args": {"name": "Ghost"}},
                {"id": "away", "args": {"name": "Guard"}},
            ],
            world_state,
            GameplayConfig(auto_create_npcs=False),
            {},
        )
        assert prepared == []
        assert "Ghost" in notes[0]
        assert "not present" in notes[1]

    def test_cap_is_applied_before_creating_unselected_npc(self):
        from app.ai.router import GameplayConfig
        from app.core.dm.npc_prehook import prepare_npc_calls

        world_state = {"npcs": {}}
        prepared, notes = prepare_npc_calls(
            [
                {"id": "first", "args": {"name": "A"}},
                {"id": "second", "args": {"name": "B"}},
                {"id": "third", "args": {"name": "C"}},
            ],
            world_state,
            GameplayConfig(auto_create_npcs=True, npc_verbosity="low"),
            {},
        )
        assert [item.name for item in prepared] == ["A", "B"]
        assert "limit" in notes[2]
        assert {npc["name"] for npc in world_state["npcs"].values()} == {"A", "B"}

    def test_aliases_resolve_to_same_identity_and_presence_is_strict(self):
        from app.ai.router import GameplayConfig
        from app.core.dm.npc_prehook import prepare_npc_calls

        world_state = {
            "meta": {"current_location": "Tavern"},
            "npcs": {
                "guard-id": {"name": "The Guard", "slug": "guard", "location": "Tavern"},
            },
        }
        prepared, notes = prepare_npc_calls(
            [{"id": "a", "args": {"name": "The Guard"}}, {"id": "b", "args": {"name": "guard"}}],
            world_state,
            GameplayConfig(auto_create_npcs=False),
            {},
        )
        assert [item.npc_id for item in prepared] == ["guard-id"]
        assert "already selected" in notes[1]


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
