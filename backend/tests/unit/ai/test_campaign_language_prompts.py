import uuid
from unittest.mock import AsyncMock

import pytest

from app.ai.npc_director import invoke_npcs_parallel
from app.ai.prompts.dm import build_dm_system_prompt
from app.ai.router import ModelConfig
from app.models.campaign import Campaign, Difficulty


@pytest.mark.parametrize("code,name", [("it", "Italian"), ("en", "English"), ("ja", "Japanese")])
async def test_campaign_target_is_explicit_in_dm_and_real_actor_call(
    monkeypatch: pytest.MonkeyPatch, code: str, name: str
) -> None:
    campaign = Campaign(
        user_id=uuid.uuid4(),
        name="Language",
        world_slug="test",
        language=code,
        difficulty=Difficulty.MEDIUM,
        quests={},
        character_data={},
        world_baseline={},
        world_state={
            "meta": {"current_location": "shrine"},
            "npcs": {
                "npc-1": {
                    "name": "Lyra",
                    "location": "shrine",
                    "traits": {"role": "English authored ranger"},
                },
            },
        },
    )
    prompt = build_dm_system_prompt(campaign)
    assert f"{name} ({code})" in prompt
    assert "same language the player uses" not in prompt
    provider = AsyncMock()
    provider.generate.return_value = '{"dialogue": "Test.", "axis_changes": {}}'
    monkeypatch.setattr(
        "app.ai.npc_director.get_generation",
        AsyncMock(return_value=(provider, ModelConfig("local", "test", 60000))),
    )
    await invoke_npcs_parallel(["Lyra"], campaign, "Ciao / hello", "You see an old shrine.")
    actor_prompt = provider.generate.call_args.kwargs["messages"][0]["content"]
    assert f"{name} ({code})" in actor_prompt
    assert "English authored ranger" in actor_prompt
