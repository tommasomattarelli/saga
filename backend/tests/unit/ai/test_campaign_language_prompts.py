import json
import uuid
from unittest.mock import AsyncMock

import pytest

from app.ai.generation_contracts import RawGenerationReceipt
from app.ai.npc_director import NPCInput, invoke_npcs_parallel
from app.ai.prompts.dm import build_dm_system_prompt
from app.ai.router import ModelConfig
from app.models.campaign import Campaign, Difficulty
from tests.unit.eval.dialogue.typed_provider_test_support import TypedResponseProvider


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
    provider = TypedResponseProvider(
        [
            RawGenerationReceipt(
                text=json.dumps(
                    {
                        "status": "speaking",
                        "lines": ["Test."],
                        "action": None,
                        "axis_changes": [],
                        "reveals_secret": False,
                    }
                )
            )
        ]
    )
    monkeypatch.setattr(
        "app.ai.npc_director.get_generation",
        AsyncMock(
            return_value=(
                provider,
                ModelConfig(
                    "local",
                    "test",
                    60000,
                    destination_fingerprint="offline-test-destination",
                ),
            )
        ),
    )
    actor = NPCInput(
        npc_name="Lyra",
        npc_profile=dict(campaign.world_state["npcs"]["npc-1"]),
        player_action="Ciao / hello",
        dm_narration="You see an old shrine.",
        language=code,
    )
    await invoke_npcs_parallel([actor], campaign.user_id)
    actor_prompt = provider.requests[0].messages[0]["content"]
    assert isinstance(actor_prompt, str)
    assert f"{name} ({code})" in actor_prompt
    assert "English authored ranger" in actor_prompt
