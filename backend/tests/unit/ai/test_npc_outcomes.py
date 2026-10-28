import json
from unittest.mock import AsyncMock

import pytest

from app.ai.npc_director import invoke_single_npc
from app.ai.router import ModelConfig


@pytest.mark.parametrize(
    "raw",
    [
        '{"action":"Looks away.","axis_changes":{"trust":5}}',
        '{"status":"speaking","lines":[]}',
        '{"status":"speaking","lines":["", "...", "…", "   "]}',
        '{"status":"silent","lines":["Not silent"]}',
        '{"status":"speaking","lines":"hello"}',
        '{"status":"speaking","lines":[42]}',
        "[]",
        "null",
        '{"status":"silent","action":42}',
        '{"status":"speaking","lines":["hello [[npc:Lyra:1]]"]}',
        '{"status":"speaking","lines":["hello"],"action":"[[npc:Lyra:"}',
        '{"status":"silent","action":"[[NPC"}',
    ],
)
async def test_unusable_actor_output_is_failure_not_a_conversation(monkeypatch, raw):
    provider = AsyncMock()
    provider.generate.return_value = raw
    monkeypatch.setattr(
        "app.ai.npc_director.get_generation",
        AsyncMock(return_value=(provider, ModelConfig("local", "test", 60000))),
    )
    result = await invoke_single_npc("Lyra", {"name": "Lyra"}, "Hello", "A clearing.")
    assert getattr(result, "status", None) == "failure"
    assert not getattr(result, "lines", ())
    assert not getattr(result, "axis_changes", {})
    assert provider.generate.await_count == 1


async def test_speaking_keeps_verbatim_lines_and_configured_cap(monkeypatch):
    provider = AsyncMock()
    provider.generate.return_value = json.dumps(
        {
            "status": "speaking",
            "lines": ["...", "  First.  ", "Second.", "Third."],
            "action": "[a gesture]",
            "axis_changes": {"trust": 3},
        }
    )
    monkeypatch.setenv("SAGA_GAMEPLAY_NPC_MAX_LINES", "2")
    monkeypatch.setattr(
        "app.ai.npc_director.get_generation",
        AsyncMock(return_value=(provider, ModelConfig("local", "test", 60000))),
    )
    result = await invoke_single_npc("Lyra", {"name": "Lyra"}, "Hello", "A clearing.")
    assert getattr(result, "status", None) == "speaking"
    assert result.lines == ("  First.  ", "Second.")
    assert result.action == "[a gesture]"
    assert result.axis_changes == {"trust": 3}
    assert provider.generate.call_args.kwargs["max_tokens"] == 60000


async def test_explicit_silence_is_a_valid_actor_choice(monkeypatch):
    provider = AsyncMock()
    provider.generate.return_value = (
        '{"status":"silent","lines":[],"action":"Prepares to strike.","axis_changes":{"fear":2}}'
    )
    monkeypatch.setattr(
        "app.ai.npc_director.get_generation",
        AsyncMock(return_value=(provider, ModelConfig("local", "test", 60000))),
    )
    result = await invoke_single_npc("Lyra", {"name": "Lyra"}, "Hello", "A clearing.")
    assert getattr(result, "status", None) == "silent"
    assert result.lines == ()
    assert result.axis_changes == {"fear": 2}


async def test_actor_prompt_keeps_distinct_inputs_and_bounded_narrative(monkeypatch):
    from app.ai.prompts.npc import build_npc_prompt

    monkeypatch.setenv("SAGA_GAMEPLAY_NPC_NARRATIVE_MAX_CHARS", "1000")
    action = "PLAYER ACTION " + "x" * 1100
    context = "INVOCATION CONTEXT " + "z" * 1100
    prompt = build_npc_prompt(
        {"name": "Lyra"},
        player_action=action,
        invocation_context=context,
        dm_narration="old" * 500 + "TAIL" * 250,
        observed_beats="Public earlier beat.",
    )
    assert action in prompt and context in prompt
    assert "TAIL" * 250 in prompt and "old" * 200 not in prompt
    assert "Public earlier beat." in prompt
