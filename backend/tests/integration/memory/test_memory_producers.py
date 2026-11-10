import json
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage
from sqlalchemy import func, select

from app.ai.generation_context import generation_context
from app.ai.router import ModelConfig
from app.core.dm.dm_nodes import post_process_node
from app.core.dm.dm_tools_executor import tools_node
from app.memory.batch_input import load_batch_input
from app.memory.producer_contracts import MemoryOutputError
from app.memory.producer_prompts import prepare_request
from app.memory.producers import generate_memory
from app.models.memory_document import MemoryGlobalCheckpoint, MemorySummary
from app.models.memory_fact import MemoryFact
from app.models.quest import QuestRegistry
from tests.integration.memory.batch_input_support import recorded_turn
from tests.integration.memory.storage_support import HistoryFixture
from tests.integration.memory.test_batch_storage import batch


def tool_state(*, user_id: str, calls: list[dict]) -> dict:
    return {
        "messages": [AIMessage(content="", tool_calls=calls)],
        "world_state": {"meta": {"current_location": "Village"}, "npcs": {}},
        "char_data": {
            "name": "Adventurer",
            "hp": {"current": 10, "max": 20},
            "abilities": {"dexterity": 10},
            "inventory": [],
        },
        "quests": QuestRegistry(),
        "player_action": "Ask Mira about the key",
        "campaign_id": str(uuid4()),
        "user_id": user_id,
        "narration": "",
        "step_count": 1,
        "tool_events": [],
        "dice_results": [],
        "npc_beats": [],
        "npc_lines": [],
        "scene_mood": "neutral",
        "time_passed_minutes": 0,
        "narration_segments": [],
        "operations": [],
        "closing_step": False,
        "allowed_tools": ["invoke_npc", "update_quest"],
        "difficulty": "medium",
        "world_baseline": {},
        "narrative_observations": [],
        "max_agent_steps": 5,
        "consecutive_empty_steps": 0,
        "progress_fingerprints": [],
        "followup_required": False,
        "death_event": None,
        "model_used": "test",
        "importance_score": 0,
    }


def memory_output(npc_name: str, *, facts: list[dict] | None = None) -> str:
    return json.dumps(
        {
            "summary": {"text": "Mira revealed where she hid the key."},
            "facts": facts
            if facts is not None
            else [
                {
                    "content": "Mira said she hid the key beneath the altar.",
                    "category": "information",
                    "assertion_type": "statement",
                    "entities": [{"name": npc_name, "type": "npc", "role": "speaker"}],
                    "attribution": [0],
                    "source_turns": ["t1"],
                    "temporal_references": [],
                    "importance": {"level": "ordinary", "reason": "A useful clue."},
                }
            ],
        }
    )


async def recorded_batch(f: HistoryFixture, provider: AsyncMock, monkeypatch: pytest.MonkeyPatch):
    user_id = str(f.campaign.user_id)
    config = ModelConfig(provider="test", model="test-model", max_tokens=1000)

    async def user_generation(_user_id):
        return provider, config

    monkeypatch.setattr("app.ai.generation_context.get_user_generation", user_generation)
    state = tool_state(
        user_id=user_id,
        calls=[
            {
                "id": "npc",
                "name": "invoke_npc",
                "args": {"name": "Mira", "context": "Where is the key?"},
            },
            {
                "id": "quest",
                "name": "update_quest",
                "args": {"quest_id": "find_key", "status": "active", "name": "Find the key"},
            },
            {
                "id": "quest-complete",
                "name": "update_quest",
                "args": {"quest_id": "find_key", "status": "completed"},
            },
            {
                "id": "quest-reopen",
                "name": "update_quest",
                "args": {"quest_id": "find_key", "status": "active"},
            },
            {"id": "bad-move", "name": "move_to", "args": {"location": "Nowhere"}},
        ],
    )
    with generation_context((provider, config)):
        generated = await tools_node(state)
    state.update(generated)
    state.update(post_process_node(state))
    ops = state["operations"]
    npc_id = next(op.payload.result.npc_id for op in ops if op.payload.name == "invoke_npc")
    assert any(op.payload.name == "update_quest" for op in ops)
    quest_ops = [op for op in ops if op.payload.name == "update_quest"]
    assert len(quest_ops) == 3
    assert [op.payload.outcome for op in quest_ops] == ["succeeded"] * 3
    assert quest_ops[0].payload.deltas and quest_ops[1].payload.deltas
    assert generated["quests"].active[0].id == "find_key"
    assert generated["quests"].completed == []
    assert any(op.payload.name == "move_to" and op.payload.outcome == "rejected" for op in ops)
    first = await recorded_turn(
        f,
        parent=None,
        number=1,
        action="Ask Mira about the key",
        narration=state["narration"],
        operations=ops,
    )
    second = await recorded_turn(
        f,
        parent=first,
        number=2,
        action="Return to the altar",
        narration="The party finds the altar.",
    )
    item = await batch(f, [first, second])
    source = await load_batch_input(f.session, f.campaign.id, item.id)
    request = prepare_request("batch", source, language="en", facts_policy=f.policy.payload.facts)
    await f.session.close()
    return item, source, request, npc_id


@pytest.mark.parametrize("empty_facts", [False, True])
async def test_handlers_recorded_history_generates_resolved_memory_without_db_during_provider(
    history_fixture: HistoryFixture,
    assert_no_db_held,
    monkeypatch: pytest.MonkeyPatch,
    empty_facts: bool,
) -> None:
    f = history_fixture
    provider = AsyncMock()
    calls = 0

    async def generate(**_kwargs):
        nonlocal calls
        calls += 1
        assert_no_db_held()
        if calls == 1:
            return '{"status":"speaking","lines":["I hid the key beneath the altar."]}'
        return memory_output("Mira", facts=[] if empty_facts else None)

    provider.generate.side_effect = generate
    _, source, request, npc_id = await recorded_batch(f, provider, monkeypatch)

    with generation_context((provider, ModelConfig("test", "test-model", 1000))):
        result = await generate_memory(request)
        assert_no_db_held()

    assert [turn.reference for turn in source.turns] == ["t1", "t2"]
    speech = "I hid the key beneath the altar."
    assert source.turns[0].narration.count(speech) == 1
    assert request.user_prompt.count(speech) == 1
    assert source.turns[0].operations is not None
    assert {op.payload.name for op in source.turns[0].operations} >= {"invoke_npc", "update_quest"}
    npc_operations = [op for op in source.turns[0].operations if op.payload.name == "invoke_npc"]
    assert npc_operations[0].payload.outcome == "succeeded", npc_operations
    assert npc_operations[0].payload.result.status == "speaking"
    assert any(
        op.payload.name == "move_to" and op.payload.outcome == "rejected"
        for op in source.turns[0].operations
    )
    if empty_facts:
        assert result.facts == ()
        assert result.payload.facts == ()
    else:
        assert result.facts[0].source_turn_ids == (source.turns[0].turn_id,)
        assert result.facts[0].metadata.entities[0].canonical_ref.id == npc_id
    assert provider.generate.await_count == 2


@pytest.mark.parametrize(
    "bad_facts",
    [
        [{"content": "missing fields"}],
        [
            {
                "content": "one",
                "category": "event",
                "assertion_type": "occurrence",
                "entities": [],
                "attribution": [],
                "source_turns": ["t1"],
                "temporal_references": [],
                "importance": {"level": "ordinary", "reason": "Reason"},
            }
        ]
        * 5,
    ],
)
async def test_invalid_or_over_cap_generation_writes_no_memory_documents(
    history_fixture: HistoryFixture,
    bad_facts: list[dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    f = history_fixture
    provider = AsyncMock()
    calls = 0

    async def generate(**_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return '{"status":"speaking","lines":["I hid it."]}'
        return memory_output("Mira", facts=bad_facts)

    provider.generate.side_effect = generate
    _, _, request, _ = await recorded_batch(f, provider, monkeypatch)
    with (
        generation_context((provider, ModelConfig("test", "test-model", 1000))),
        pytest.raises(MemoryOutputError),
    ):
        await generate_memory(request)

    assert (
        await f.session.scalar(
            select(func.count())
            .select_from(MemorySummary)
            .where(MemorySummary.campaign_id == f.campaign.id)
        )
        == 0
    )
    assert (
        await f.session.scalar(
            select(func.count())
            .select_from(MemoryFact)
            .where(MemoryFact.campaign_id == f.campaign.id)
        )
        == 0
    )
    assert (
        await f.session.scalar(
            select(func.count())
            .select_from(MemoryGlobalCheckpoint)
            .where(MemoryGlobalCheckpoint.campaign_id == f.campaign.id)
        )
        == 0
    )
