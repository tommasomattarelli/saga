"""Tests for the NPC Actor-Director system."""

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.ai.generation_contracts import GenerationRequest, RawGenerationReceipt
from app.ai.generation_execution import GenerationProvider
from app.ai.npc_director import (
    NPCInput,
    invoke_npcs_parallel,
    invoke_single_npc,
)
from app.ai.npc_outcomes import NPCSpeaking
from app.ai.router import ModelConfig
from tests.unit.eval.dialogue.typed_provider_test_support import TypedResponseProvider


def configured_provider(provider: GenerationProvider) -> tuple[GenerationProvider, ModelConfig]:
    return provider, ModelConfig(
        provider="openai",
        model="gpt-4o-mini",
        max_tokens=300,
        destination_fingerprint="offline-test-destination",
    )


class TestInvokeSingleNPC:
    @pytest.mark.asyncio
    async def test_invoke_returns_dialogue(self):
        mock_provider = TypedResponseProvider(
            [
                RawGenerationReceipt(
                    text=json.dumps(
                        {
                            "status": "speaking",
                            "lines": ["Well met!"],
                            "action": None,
                            "axis_changes": [
                                {"key": "trust", "value": 5},
                                {"key": "fear", "value": -2},
                            ],
                            "reveals_secret": False,
                        }
                    )
                )
            ]
        )

        with (
            patch(
                "app.ai.npc_director.get_generation",
                new_callable=AsyncMock,
                return_value=configured_provider(mock_provider),
            ),
        ):
            result = await invoke_single_npc(
                npc_name="Grenda",
                npc_profile={"name": "Grenda", "role": "Blacksmith"},
                player_action="I approach the forge",
                dm_narration="You see a sturdy dwarf hammering at the anvil.",
            )

            assert result.npc_name == "Grenda"
            assert result.lines == ("Well met!",)
            assert result.axis_changes == {"trust": 5, "fear": -2}

    @pytest.mark.asyncio
    async def test_malformed_axis_changes_fail_the_response(self):
        mock_provider = TypedResponseProvider(
            [
                RawGenerationReceipt(
                    text='{"status":"speaking","lines":["Hm."],"action":null,'
                    '"axis_changes":[{"key":"trust","value":"lots"}],'
                    '"reveals_secret":false}'
                )
            ]
        )

        with (
            patch(
                "app.ai.npc_director.get_generation",
                new_callable=AsyncMock,
                return_value=configured_provider(mock_provider),
            ),
        ):
            result = await invoke_single_npc(
                npc_name="Grenda",
                npc_profile={"name": "Grenda"},
                player_action="hello",
                dm_narration="You approach.",
            )

            assert result.status == "failure"

    @pytest.mark.asyncio
    async def test_invoke_fallback_on_error(self):
        class FailingProvider:
            async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
                raise RuntimeError("provider failure")

        with (
            patch(
                "app.ai.npc_director.get_generation",
                new_callable=AsyncMock,
                return_value=configured_provider(FailingProvider()),
            ),
        ):
            result = await invoke_single_npc(
                npc_name="Grenda",
                npc_profile={"name": "Grenda"},
                player_action="hello",
                dm_narration="You approach.",
            )

            assert result.npc_name == "Grenda"
            assert result.status == "failure"


class TestInvokeNPCsParallel:
    @pytest.mark.asyncio
    async def test_invokes_actors_concurrently_and_isolates_failure(self):
        entered = 0
        both_entered = asyncio.Event()

        async def mock_invoke(npc_name: str, **kwargs: object) -> NPCSpeaking:
            nonlocal entered
            entered += 1
            if entered == 2:
                both_entered.set()
            await asyncio.wait_for(both_entered.wait(), timeout=1)
            if npc_name == "B":
                raise RuntimeError("isolated actor error")
            return NPCSpeaking(npc_name, ("Hello.",))

        actors = [NPCInput(name, {"name": name}, "hello") for name in ("A", "B")]
        with patch("app.ai.npc_director.invoke_single_npc", side_effect=mock_invoke):
            results = await invoke_npcs_parallel(actors, uuid.uuid4())
        assert entered == 2
        assert results[0] == NPCSpeaking("A", ("Hello.",))
        assert results[1].status == "failure"

    @pytest.mark.asyncio
    async def test_empty_actor_list_returns_empty(self):
        assert await invoke_npcs_parallel([], uuid.uuid4()) == []
