import json
import uuid
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.ai.generation_context import generation_context
from app.ai.providers.schemas import ToolCall
from app.dependencies import get_db_context
from app.memory.compressor import compress_turns_batch_llm
from app.memory.fact_extractor import extract_facts
from app.memory.global_summary import update_global_summary
from app.models.turn import Turn
from app.schemas.campaign import TurnResponse
from tests.integration.test_quest_persistence import (
    _create_campaign,
    _openai_provider,
    _owner,
    _reply,
    _script,
    _take_turn,
)


async def test_complete_transcript_is_the_single_persisted_and_memory_source(
    auth_client,
    generation_clients,
):
    created = await _create_campaign(auth_client)
    provider = await _openai_provider(auth_client, generation_clients)
    provider.generate.side_effect = None
    provider.generate.return_value = (
        '{"status":"speaking","lines":["A sealed promise.","Do not forget."]}'
    )
    requests = _script(
        provider,
        [
            _reply(
                "Wind over the stones. " * 25,
                ToolCall(
                    id="npc",
                    name="invoke_npc",
                    arguments={"name": "Lyra"},
                ),
            ),
            _reply(
                'A pause. [[npc:Lyra:1]] "A sealed promise."\n\n'
                "Then silence. [[npc:Lyra:1]] [[npc:Unknown:9]]"
            ),
            _reply("Morning comes."),
        ],
    )
    actual = await _take_turn(auth_client, created["id"])
    validated = TurnResponse.model_validate(actual).model_dump(mode="json")
    assert validated["narration_segments"] == actual["narration_segments"]
    assert "npc_dialogues" not in actual
    for line in ("A sealed promise.", "Do not forget."):
        assert actual["narration"].count(line) == 1
    assert "[[npc" not in json.dumps(actual)
    assert all("text" not in s and "npc_dialogues" not in s for s in actual["narration_segments"])

    async with get_db_context() as db:
        turn = await db.scalar(select(Turn).where(Turn.campaign_id == uuid.UUID(created["id"])))
    assert turn.narration == actual["narration"]
    assert turn.narration_segments == actual["narration_segments"]
    for path in (f"/api/journal/{created['id']}", f"/api/export/{created['id']}"):
        response = await auth_client.get(path)
        assert response.status_code == 200
        row = response.json()[0] if "journal" in path else response.json()["turns"][0]
        assert row["narration"] == actual["narration"]
        assert row["narration_segments"] == actual["narration_segments"]

    prompts = []

    async def generate(**kwargs):
        prompts.append(kwargs["messages"][0]["content"])
        return '{"summary":"A promise was made.","facts":[]}'

    provider.generate.side_effect = generate
    with generation_context(await _owner(auth_client)):
        await extract_facts("I listen.", turn.narration)
        await compress_turns_batch_llm([turn])
        async with get_db_context() as db:
            await update_global_summary(created["id"], 1, db)
            await db.commit()
    assert len(prompts) == 3
    for prompt in prompts:
        assert prompt.count("A sealed promise.") == prompt.count("Do not forget.") == 1
        assert "[[npc" not in prompt and "NPC dialogues:" not in prompt

    with patch("app.ai.context._recall_memories", new=AsyncMock(return_value=[])):
        await _take_turn(auth_client, created["id"], "I wait.")
    history = [m["content"] for m in requests[-1]["messages"] if m["role"] == "assistant"]
    assert history == [actual["narration"]]
