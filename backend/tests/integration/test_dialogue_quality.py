from app.ai.providers.schemas import AgentResponse, ToolCall
from tests.integration.test_npc_beats import actor, speaking
from tests.integration.test_quest_persistence import (
    _create_campaign,
    _openai_provider,
    _reply,
    _script,
    _take_turn,
)


async def test_public_observation_is_clean_before_next_beat_but_provider_message_stays_raw(
    auth_client,
    generation_clients,
):
    created = await _create_campaign(auth_client)
    provider = await _openai_provider(auth_client, generation_clients)
    actor_inputs = []

    async def generate(**kwargs):
        actor_inputs.append(kwargs["messages"][0]["content"])
        return speaking("Forse" if len(actor_inputs) == 1 else "Adesso so.")

    provider.generate.side_effect = generate
    raw = "[[npc:Lyra:1]] «Forse»\n\nIl vento tace."
    dm = _script(
        provider,
        [
            _reply("", actor("Lyra")),
            AgentResponse(raw, [ToolCall("next", "invoke_npc", {"name": "Lyra"})], b"signed"),
            _reply("[[npc:Lyra:2]]"),
        ],
    )
    result = await _take_turn(auth_client, created["id"])
    assert len(actor_inputs) == 2
    assert "«Forse»" not in actor_inputs[1]
    assert "Forse" in actor_inputs[1]
    assert "«Forse»" not in result["narration"]
    assert result["narration"].count("Forse") == 1
    original = next(
        m for m in dm[2]["messages"] if m["role"] == "assistant" and m["content"] == raw
    )
    assert original["text_thought_signature"] == b"signed"
    assert "<dialogue_state>" in dm[1]["system_prompt"]
    assert "[[npc:Lyra:1]]" in dm[1]["system_prompt"]


async def test_closing_reminder_places_remaining_handles_without_inviting_another_beat(
    auth_client,
    generation_clients,
    monkeypatch,
):
    monkeypatch.setenv("SAGA_GAMEPLAY_MAX_AGENT_STEPS", "2")
    created = await _create_campaign(auth_client)
    provider = await _openai_provider(auth_client, generation_clients)
    provider.generate.side_effect = None
    provider.generate.return_value = speaking("Wait.")
    dm = _script(provider, [_reply("", actor("Lyra")), _reply("[[npc:Lyra:1]]")])
    await _take_turn(auth_client, created["id"])
    assert "No further actor calls" in dm[-1]["system_prompt"]
    assert "Reactions to new words may use a subsequent beat" not in dm[-1]["system_prompt"]
