"""Unit tests for routing functions in app/core/dm/dm_graph.py."""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from app.core.dm.dm_graph import MAX_STEPS, route_after_dm, route_after_tools


def _make_state(**overrides) -> dict:
    base: dict = {
        "messages": [],
        "world_state": {},
        "char_data": {},
        "player_action": "look around",
        "campaign_id": "test-campaign",
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


class TestRouteAfterDm:
    def test_routes_to_tools_when_tool_calls_present(self):
        tc = {"id": "1", "name": "request_dice", "args": {}, "type": "tool_call"}
        ai_msg = AIMessage(content="", tool_calls=[tc])
        state = _make_state(messages=[ai_msg])
        assert route_after_dm(state) == "tools_node"

    def test_routes_to_post_process_when_no_tool_calls(self):
        ai_msg = AIMessage(content="The room is dark.", tool_calls=[])
        state = _make_state(messages=[ai_msg])
        assert route_after_dm(state) == "post_process_node"

    def test_routes_to_post_process_when_no_messages(self):
        state = _make_state(messages=[])
        assert route_after_dm(state) == "post_process_node"

    def test_only_looks_at_last_ai_message(self):
        tc = {"id": "1", "name": "request_dice", "args": {}, "type": "tool_call"}
        old_ai = AIMessage(content="old", tool_calls=[tc])
        new_ai = AIMessage(content="new narration", tool_calls=[])
        state = _make_state(messages=[old_ai, HumanMessage(content="action"), new_ai])
        assert route_after_dm(state) == "post_process_node"


class TestRouteAfterTools:
    def test_routes_to_post_process_when_max_steps_reached(self):
        ai_msg = AIMessage(content="", tool_calls=[])
        state = _make_state(messages=[ai_msg], step_count=MAX_STEPS, narration="some narration")
        assert route_after_tools(state) == "post_process_node"

    def test_routes_to_post_process_when_no_ai_message(self):
        state = _make_state(messages=[], step_count=1)
        assert route_after_tools(state) == "post_process_node"

    def test_routes_to_dm_node_for_meaningful_tool_invoke_npc(self):
        tc = {"id": "1", "name": "invoke_npc", "args": {}, "type": "tool_call"}
        ai_msg = AIMessage(content="", tool_calls=[tc])
        state = _make_state(messages=[ai_msg], step_count=1, narration="some narration")
        assert route_after_tools(state) == "dm_node"

    def test_routes_to_dm_node_for_meaningful_tool_request_dice(self):
        tc = {"id": "1", "name": "request_dice", "args": {}, "type": "tool_call"}
        ai_msg = AIMessage(content="", tool_calls=[tc])
        state = _make_state(messages=[ai_msg], step_count=1, narration="some narration")
        assert route_after_tools(state) == "dm_node"

    def test_routes_to_post_process_when_has_narration_and_silent_tools(self):
        tc = {"id": "1", "name": "update_world", "args": {}, "type": "tool_call"}
        ai_msg = AIMessage(content="", tool_calls=[tc])
        state = _make_state(messages=[ai_msg], step_count=1, narration="The hero steps forward.")
        assert route_after_tools(state) == "post_process_node"

    def test_routes_to_dm_node_when_no_narration_and_silent_tools(self):
        tc = {"id": "1", "name": "update_world", "args": {}, "type": "tool_call"}
        ai_msg = AIMessage(content="", tool_calls=[tc])
        state = _make_state(messages=[ai_msg], step_count=1, narration="")
        assert route_after_tools(state) == "dm_node"

    def test_routes_to_dm_node_when_narration_is_whitespace(self):
        # whitespace-only narration → strip() → empty → has_narration=False → dm_node
        tc = {"id": "1", "name": "update_world", "args": {}, "type": "tool_call"}
        ai_msg = AIMessage(content="", tool_calls=[tc])
        state = _make_state(messages=[ai_msg], step_count=1, narration="   ")
        assert route_after_tools(state) == "dm_node"
