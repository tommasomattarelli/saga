from __future__ import annotations

from contextlib import contextmanager
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage

from app.ai.generation_contracts import (
    GenerationToolReceipt,
    RawGenerationReceipt,
    RawToolArguments,
)
from app.ai.generation_execution_ledger import GenerationRecoveryPolicy
from app.ai.providers.google_generation import _contents
from app.ai.providers.schemas import TEXT_SIGNATURE_KEY
from app.ai.router import ModelConfig
from app.core.dm.dm_helpers import messages_to_raw
from app.core.dm.dm_tools_executor import tools_node
from app.core.dm.game_state import GameState
from app.models.quest import QuestRegistry
from tests.unit.core.dm_generation_test_support import SequenceProvider


def _state() -> GameState:
    return cast(
        GameState,
        {
            "messages": [],
            "world_state": {
                "npcs": {
                    "npc-1": {
                        "name": "Mara",
                        "condition": "well",
                        "faction": "Ash",
                        "psychology": {},
                    }
                }
            },
            "char_data": {},
            "player_action": "Look at Mara.",
            "difficulty": "medium",
            "campaign_id": "campaign-1",
            "user_id": "user-1",
            "narration": "",
            "step_count": 1,
            "max_agent_steps": 8,
            "consecutive_empty_steps": 0,
            "tool_events": [],
            "dice_results": [],
            "npc_beats": [],
            "npc_lines": [],
            "narrative_observations": [],
            "quests": QuestRegistry(),
            "world_baseline": {},
            "scene_mood": "neutral",
            "time_passed_minutes": 0,
            "narration_segments": [],
            "progress_fingerprints": [],
        },
    )


@contextmanager
def _dm_dependencies(provider: SequenceProvider, allowed_tools: set[str]):
    with (
        patch(
            "app.core.dm.dm_nodes.get_user_generation",
            new=AsyncMock(
                return_value=(
                    provider,
                    ModelConfig(
                        provider="openai",
                        model="gpt-test",
                        max_tokens=1200,
                        destination_fingerprint="openai:test",
                    ),
                )
            ),
        ),
        patch(
            "app.core.dm.dm_nodes.get_generation_recovery_policy",
            return_value=GenerationRecoveryPolicy(max_sends_per_result=2),
        ),
        patch("app.core.dm.dm_nodes.step_tools", return_value=allowed_tools),
    ):
        yield


def _call(
    name: str | None,
    arguments: RawToolArguments,
    call_id: str | None = "call-1",
    signature: bytes | None = None,
) -> GenerationToolReceipt:
    return GenerationToolReceipt(call_id, name, arguments, signature)


@pytest.mark.parametrize(
    ("allowed_tools", "call"),
    [
        (
            {"request_dice"},
            _call("missing_tool", RawToolArguments.structured({"value": "x"})),
        ),
        (
            {"request_dice"},
            _call("set_scene_mood", RawToolArguments.structured({"mood": "tense"})),
        ),
        (
            {"request_dice"},
            _call("request_dice", RawToolArguments.raw_text("{broken")),
        ),
        (
            {"request_dice"},
            _call("request_dice", RawToolArguments.raw_text("[]")),
        ),
        (
            {"request_dice"},
            _call(
                "request_dice",
                RawToolArguments.structured(
                    {"check": "Stealth", "stat": "DEX", "difficulty": "impossible"}
                ),
            ),
        ),
    ],
)
@pytest.mark.asyncio
async def test_invalid_tool_call_is_corrected_before_node_admission(
    allowed_tools: set[str], call: GenerationToolReceipt
) -> None:
    from app.core.dm.dm_nodes import dm_node

    invalid = RawGenerationReceipt(
        text=None,
        tool_calls=(call,),
        raw_candidate='{"candidate":"invalid call"}',
    )
    provider = SequenceProvider(
        [invalid, RawGenerationReceipt(text='{"text":"Corrected narration."}')]
    )
    state = _state()

    with _dm_dependencies(provider, allowed_tools):
        result = await dm_node(state, config={})

    assert len(provider.requests) == 2
    assert "invalid call" in repr(provider.requests[1].messages)
    assert result["step_count"] == 2
    accepted = result["messages"][0]
    assert isinstance(accepted, AIMessage)
    assert accepted.content == "Corrected narration."
    assert accepted.tool_calls == []


@pytest.mark.asyncio
async def test_dm_node_appends_narration() -> None:
    from app.core.dm.dm_nodes import dm_node

    raw_text = '{"text":"A dragon appears!"}'
    provider = SequenceProvider(
        [RawGenerationReceipt(text=raw_text, text_signature=b"text-signature")]
    )
    state = _state()
    state["narration"] = "Previously: "

    with _dm_dependencies(provider, set()):
        result = await dm_node(state, config={})

    assert result["narration"] == "Previously: A dragon appears!"
    history = messages_to_raw(result["messages"])
    assert history[0]["content"] == raw_text
    assert history[0][TEXT_SIGNATURE_KEY] == b"text-signature"
    replayed = _contents(provider.requests[0].derive(messages=history))[0]["parts"][0]
    assert replayed == {"text": raw_text, "thought_signature": b"text-signature"}


@pytest.mark.parametrize(
    ("name", "wire_arguments", "canonical_arguments"),
    [
        (
            "update_npc",
            {
                "name": "Mara",
                "updates": [{"key": "condition", "value": "wounded"}],
            },
            {"name": "Mara", "updates": {"condition": "wounded"}, "create": False},
        ),
        (
            "change_npc_psychology",
            {
                "npc": "Mara",
                "changes": [{"key": "trust", "value": 5}],
            },
            {"npc": "Mara", "changes": {"trust": 5}, "reason": ""},
        ),
    ],
)
@pytest.mark.asyncio
async def test_wire_arguments_are_canonical_at_preflight_and_dispatch(
    name: str,
    wire_arguments: dict[str, object],
    canonical_arguments: dict[str, object],
) -> None:
    from app.core.dm.dm_nodes import dm_node

    provider = SequenceProvider(
        [
            RawGenerationReceipt(
                text=None,
                tool_calls=(
                    _call(
                        name,
                        RawToolArguments.structured(wire_arguments)
                        if name == "update_npc"
                        else RawToolArguments.raw_text(
                            '{"npc":"Mara","changes":[{"key":"trust","value":5}]}'
                        ),
                        signature=b"wire-signature",
                    ),
                ),
                raw_candidate='{"candidate":"wire call"}',
            )
        ]
    )
    state = _state()

    with _dm_dependencies(provider, {name}):
        generated = await dm_node(state, config={})

    ai_message = generated["messages"][0]
    assert isinstance(ai_message, AIMessage)
    assert ai_message.tool_calls[0]["args"] == canonical_arguments
    history = messages_to_raw([ai_message])
    next_request = provider.requests[0].derive(messages=history)
    replayed = _contents(next_request)[0]["parts"][0]
    assert replayed["function_call"]["args"] == wire_arguments
    assert replayed["thought_signature"] == b"wire-signature"

    tool_state = cast(
        GameState,
        {
            **state,
            **generated,
            "messages": [*state["messages"], *generated["messages"]],
        },
    )
    dispatched = await tools_node(tool_state)

    assert dispatched["operations"][0].payload.arguments == canonical_arguments
    assert len(provider.requests) == 1


@pytest.mark.asyncio
async def test_malformed_tool_receipt_is_not_admitted_before_correction() -> None:
    from app.core.dm.dm_nodes import dm_node

    malformed = RawToolArguments.raw_text('{"check":"Stealth","check":"Athletics"}')
    call = _call("request_dice", malformed)
    invalid = RawGenerationReceipt(
        text=None,
        tool_calls=(call,),
        raw_candidate='{"candidate":"duplicate tool key"}',
    )
    provider = SequenceProvider(
        [invalid, RawGenerationReceipt(text='{"text":"Corrected narration."}')]
    )
    state = _state()

    with _dm_dependencies(provider, {"request_dice"}):
        generated = await dm_node(state, config={})

    assert invalid.tool_calls[0].arguments.raw_text_value == (
        '{"check":"Stealth","check":"Athletics"}'
    )
    assert len(provider.requests) == 2
    accepted = generated["messages"][0]
    assert isinstance(accepted, AIMessage)
    assert accepted.tool_calls == []
