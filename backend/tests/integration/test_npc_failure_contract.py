import json
import uuid

import pytest

from app.ai.providers.schemas import ToolCall
from app.dependencies import get_db_context
from app.models.campaign import Campaign
from tests.integration.test_quest_persistence import (
    _create_campaign,
    _openai_provider,
    _reply,
    _script,
    _take_turn,
)


@pytest.mark.parametrize(
    "raw",
    [
        {"action": "Looks away.", "axis_changes": {"trust": 10}},
        {"status": "speaking", "lines": ["..."], "axis_changes": {"trust": 10}},
        {"status": "speaking", "lines": ["[[npc:Lyra:1]]"], "axis_changes": {"trust": 10}},
    ],
)
async def test_actor_failure_does_not_persist_a_completed_conversation(
    auth_client,
    generation_clients,
    raw,
):
    created = await _create_campaign(auth_client)
    npc_id, before = next(
        (i, n) for i, n in created["world_state"]["npcs"].items() if n["name"] == "Lyra"
    )
    provider = await _openai_provider(auth_client, generation_clients)
    provider.generate.side_effect = None
    provider.generate.return_value = json.dumps(raw)
    requests = _script(
        provider,
        [
            _reply("", ToolCall(id="actor", name="invoke_npc", arguments={"name": "Lyra"})),
            _reply("The clearing is quiet."),
        ],
    )
    result = await _take_turn(auth_client, created["id"], "I ask Lyra who she is.")
    assert result["world_state"]["npcs"][npc_id] == before
    assert "..." not in result["narration"]
    assert result["narration"] == "The clearing is quiet."
    assert "did not answer" in requests[1]["messages"][-1]["content"]
    async with get_db_context() as db:
        campaign = await db.get(Campaign, uuid.UUID(created["id"]))
        assert campaign.world_state["npcs"][npc_id] == before
