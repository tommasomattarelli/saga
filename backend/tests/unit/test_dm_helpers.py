"""Unit tests for app/core/dm/dm_helpers.py."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.core.dm.dm_helpers import (
    get_or_create_segment,
    last_ai_message,
    messages_to_raw,
    raw_history_to_lc,
    sync_narration_to_segment,
    tool_calls_from_ai_message,
)


class TestToolCallsFromAiMessage:
    def test_returns_empty_list_when_no_tool_calls(self):
        msg = AIMessage(content="hello", tool_calls=[])
        assert tool_calls_from_ai_message(msg) == []

    def test_returns_tool_calls_list(self):
        tc = {"id": "123", "name": "some_tool", "args": {"x": 1}, "type": "tool_call"}
        msg = AIMessage(content="", tool_calls=[tc])
        result = tool_calls_from_ai_message(msg)
        assert len(result) == 1
        assert result[0]["name"] == "some_tool"

    def test_returns_empty_when_tool_calls_none(self):
        msg = AIMessage(content="hello")
        msg.tool_calls = None  # type: ignore[assignment]
        assert tool_calls_from_ai_message(msg) == []


class TestLastAiMessage:
    def test_returns_none_for_empty_list(self):
        assert last_ai_message([]) is None

    def test_returns_last_ai_message(self):
        msgs = [
            HumanMessage(content="action"),
            AIMessage(content="first"),
            HumanMessage(content="follow"),
            AIMessage(content="second"),
        ]
        result = last_ai_message(msgs)
        assert result is not None
        assert result.content == "second"

    def test_returns_none_when_no_ai_message(self):
        msgs = [HumanMessage(content="hi"), HumanMessage(content="bye")]
        assert last_ai_message(msgs) is None

    def test_ignores_non_ai_after_ai(self):
        msgs = [AIMessage(content="ai"), HumanMessage(content="human")]
        result = last_ai_message(msgs)
        assert result is not None
        assert result.content == "ai"


class TestRawHistoryToLc:
    def test_converts_user_messages(self):
        raw = [{"role": "user", "content": "hello"}]
        result = raw_history_to_lc(raw)
        assert len(result) == 1
        assert isinstance(result[0], HumanMessage)
        assert result[0].content == "hello"

    def test_converts_assistant_messages(self):
        raw = [{"role": "assistant", "content": "world"}]
        result = raw_history_to_lc(raw)
        assert len(result) == 1
        assert isinstance(result[0], AIMessage)
        assert result[0].content == "world"

    def test_skips_unknown_roles(self):
        raw = [{"role": "system", "content": "ignore"}, {"role": "user", "content": "keep"}]
        result = raw_history_to_lc(raw)
        assert len(result) == 1
        assert isinstance(result[0], HumanMessage)

    def test_empty_content_defaults_to_empty_string(self):
        raw = [{"role": "user"}]
        result = raw_history_to_lc(raw)
        assert result[0].content == ""

    def test_empty_input(self):
        assert raw_history_to_lc([]) == []


class TestMessagesToRaw:
    def test_converts_human_message(self):
        msgs = [HumanMessage(content="test")]
        result = messages_to_raw(msgs)
        assert result == [{"role": "user", "content": "test"}]

    def test_converts_ai_message_without_tool_calls(self):
        msgs = [AIMessage(content="response", tool_calls=[])]
        result = messages_to_raw(msgs)
        assert len(result) == 1
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == "response"
        assert "tool_calls" not in result[0]

    def test_converts_ai_message_with_tool_calls(self):
        tc = {"id": "abc", "name": "my_tool", "args": {"k": "v"}, "type": "tool_call"}
        msgs = [AIMessage(content="", tool_calls=[tc])]
        result = messages_to_raw(msgs)
        assert len(result) == 1
        raw_tcs = result[0]["tool_calls"]
        assert len(raw_tcs) == 1
        assert raw_tcs[0]["function"]["name"] == "my_tool"
        assert raw_tcs[0]["id"] == "abc"

    def test_converts_tool_message(self):
        msgs = [ToolMessage(content="ok", tool_call_id="abc", name="my_tool")]
        result = messages_to_raw(msgs)
        assert result[0]["role"] == "tool"
        assert result[0]["tool_call_id"] == "abc"
        assert result[0]["content"] == "ok"

    def test_passthrough_dict(self):
        raw_dict = {"role": "system", "content": "sys prompt"}
        result = messages_to_raw([raw_dict])
        assert result[0] is raw_dict

    def test_empty_input(self):
        assert messages_to_raw([]) == []


class TestGetOrCreateSegment:
    def test_creates_new_segment(self):
        segments: list[dict] = []
        seg = get_or_create_segment(segments, step=0)
        assert seg["step"] == 0
        assert seg["text"] == ""
        assert seg["dice"] is None
        assert seg["npc_dialogues"] == []
        assert len(segments) == 1

    def test_returns_existing_segment(self):
        segments = [{"step": 1, "text": "existing", "dice": None, "npc_dialogues": []}]
        seg = get_or_create_segment(segments, step=1)
        assert seg["text"] == "existing"
        assert len(segments) == 1

    def test_creates_new_when_step_differs(self):
        segments = [{"step": 0, "text": "first", "dice": None, "npc_dialogues": []}]
        seg = get_or_create_segment(segments, step=1)
        assert seg["step"] == 1
        assert len(segments) == 2


class TestSyncNarrationToSegment:
    def test_sets_text_when_empty(self):
        segments: list[dict] = []
        sync_narration_to_segment(segments, step=0, full_narration="The dragon roars.")
        assert segments[0]["text"] == "The dragon roars."

    def test_skips_when_text_already_set(self):
        segments = [{"step": 0, "text": "already set", "dice": None, "npc_dialogues": []}]
        sync_narration_to_segment(segments, step=0, full_narration="new narration")
        assert segments[0]["text"] == "already set"

    def test_skips_when_narration_empty(self):
        segments: list[dict] = []
        sync_narration_to_segment(segments, step=0, full_narration="")
        assert segments[0]["text"] == ""
