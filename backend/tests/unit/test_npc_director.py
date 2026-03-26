"""Tests for the NPC Actor-Director system."""

from unittest.mock import AsyncMock, patch

import pytest

from app.ai.npc_director import (
    NPCDialogue,
    format_npc_dialogues_for_turn,
    invoke_npcs_parallel,
    invoke_single_npc,
)


class TestNPCDialogue:
    def test_format_single_dialogue(self):
        dialogues = [NPCDialogue(npc_name="Grenda", dialogue="Welcome, traveler.")]
        result = format_npc_dialogues_for_turn(dialogues)
        assert '**Grenda:** "Welcome, traveler."' in result

    def test_format_with_action(self):
        dialogues = [NPCDialogue(npc_name="Grenda", dialogue="Stop!", action="draws sword")]
        result = format_npc_dialogues_for_turn(dialogues)
        assert "*(draws sword)*" in result

    def test_format_multiple_dialogues(self):
        dialogues = [
            NPCDialogue(npc_name="Grenda", dialogue="Hello."),
            NPCDialogue(npc_name="Aldric", dialogue="Greetings."),
        ]
        result = format_npc_dialogues_for_turn(dialogues)
        assert "Grenda" in result
        assert "Aldric" in result
        assert "---" in result

    def test_format_empty(self):
        assert format_npc_dialogues_for_turn([]) == ""


class TestInvokeSingleNPC:
    @pytest.mark.asyncio
    async def test_invoke_returns_dialogue(self):
        mock_provider = AsyncMock()
        mock_provider.generate.return_value = '{"dialogue": "Well met!", "action": null, "disposition_change": 5, "reveals_secret": false}'

        with (
            patch("app.ai.npc_director.get_provider", return_value=mock_provider),
            patch("app.ai.npc_director.route_ai_call", new_callable=AsyncMock) as mock_route,
        ):
            from app.ai.router import ModelConfig

            mock_route.return_value = ModelConfig(provider="openai", model="gpt-4o-mini", temperature=0.7, max_tokens=300)

            result = await invoke_single_npc(
                npc_name="Grenda",
                npc_profile={"name": "Grenda", "role": "Blacksmith"},
                player_action="I approach the forge",
                dm_narration="You see a sturdy dwarf hammering at the anvil.",
            )

            assert result.npc_name == "Grenda"
            assert result.dialogue == "Well met!"
            assert result.disposition_change == 5

    @pytest.mark.asyncio
    async def test_invoke_fallback_on_error(self):
        mock_provider = AsyncMock()
        mock_provider.generate.side_effect = Exception("API error")

        with (
            patch("app.ai.npc_director.get_provider", return_value=mock_provider),
            patch("app.ai.npc_director.route_ai_call", new_callable=AsyncMock) as mock_route,
        ):
            from app.ai.router import ModelConfig

            mock_route.return_value = ModelConfig(provider="openai", model="gpt-4o-mini", temperature=0.7, max_tokens=300)

            result = await invoke_single_npc(
                npc_name="Grenda",
                npc_profile={"name": "Grenda"},
                player_action="hello",
                dm_narration="You approach.",
            )

            assert result.npc_name == "Grenda"
            assert result.dialogue == "..."


class TestInvokeNPCsParallel:
    @pytest.mark.asyncio
    async def test_respects_npc_cap(self):
        call_count = 0

        async def mock_invoke(npc_name, npc_profile, player_action, dm_narration):
            nonlocal call_count
            call_count += 1
            return NPCDialogue(npc_name=npc_name, dialogue="Hello.")

        with (
            patch("app.ai.npc_director.invoke_single_npc", side_effect=mock_invoke),
            patch("app.ai.npc_director.get_gameplay_config") as mock_config,
        ):
            from app.ai.router import GameplayConfig

            mock_config.return_value = GameplayConfig(npc_verbosity="low")  # max 2

            campaign = AsyncMock()
            campaign.world_state = {"npcs": {}}

            results = await invoke_npcs_parallel(
                npc_names=["A", "B", "C", "D", "E"],
                campaign=campaign,
                player_action="hello",
                dm_narration="You enter the tavern.",
            )

            assert call_count == 2
            assert len(results) == 2

    @pytest.mark.asyncio
    async def test_null_verbosity_returns_empty(self):
        with patch("app.ai.npc_director.get_gameplay_config") as mock_config:
            from app.ai.router import GameplayConfig

            mock_config.return_value = GameplayConfig(npc_verbosity="null")  # max 0

            campaign = AsyncMock()
            campaign.world_state = {"npcs": {}}

            results = await invoke_npcs_parallel(
                npc_names=["A", "B"],
                campaign=campaign,
                player_action="hello",
                dm_narration="You enter.",
            )

            assert results == []
