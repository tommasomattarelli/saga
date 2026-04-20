"""Unit tests for app/memory/fact_extractor.py."""

from __future__ import annotations

import uuid
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestExtractAndStoreFacts:
    @pytest.mark.asyncio
    async def test_early_return_when_disabled(self):
        from app.memory.fact_extractor import extract_and_store_facts

        with patch("app.memory.fact_extractor.get_gameplay_config") as mock_cfg:
            mock_cfg.return_value.fact_extraction_enabled = False
            # Should return immediately without calling AI
            with patch("app.memory.fact_extractor.route_ai_call") as mock_route:
                await extract_and_store_facts(
                    campaign_id=uuid.uuid4(),
                    turn_number=1,
                    player_action="test",
                    narration="test",
                )
                mock_route.assert_not_called()

    @pytest.mark.asyncio
    async def test_includes_npc_dialogues_in_prompt(self):
        from app.memory.fact_extractor import extract_and_store_facts

        with patch("app.memory.fact_extractor.get_gameplay_config") as mock_cfg:
            mock_cfg.return_value.fact_extraction_enabled = True
            with patch("app.memory.fact_extractor.route_ai_call", new_callable=AsyncMock) as mock_route:
                mock_route.return_value = MagicMock(provider="openai", model="gpt-4o-mini")
                with patch("app.memory.fact_extractor.get_provider", return_value=MagicMock()):
                    with patch("app.memory.fact_extractor.logged_generate", new_callable=AsyncMock) as mock_gen:
                        mock_gen.return_value = '{"facts": []}'
                        await extract_and_store_facts(
                            campaign_id=uuid.uuid4(),
                            turn_number=1,
                            player_action="talk to innkeeper",
                            narration="The innkeeper greets you.",
                            npc_dialogues=["Innkeeper: Welcome!"],
                        )
                        call_kwargs = mock_gen.call_args
                        messages = call_kwargs[1]["messages"] if call_kwargs[1] else call_kwargs[0][3]
                        content = messages[0]["content"]
                        assert "NPC dialogues" in content

    @pytest.mark.asyncio
    async def test_returns_when_empty_facts(self):
        from app.memory.fact_extractor import extract_and_store_facts

        with patch("app.memory.fact_extractor.get_gameplay_config") as mock_cfg:
            mock_cfg.return_value.fact_extraction_enabled = True
            with patch("app.memory.fact_extractor.route_ai_call", new_callable=AsyncMock) as mock_route:
                mock_route.return_value = MagicMock(provider="openai", model="gpt-4o-mini")
                with patch("app.memory.fact_extractor.get_provider", return_value=MagicMock()):
                    with patch("app.memory.fact_extractor.logged_generate", new_callable=AsyncMock) as mock_gen:
                        mock_gen.return_value = '{"facts": []}'
                        # Should complete without error
                        await extract_and_store_facts(
                            campaign_id=uuid.uuid4(),
                            turn_number=1,
                            player_action="nothing",
                            narration="nothing happened",
                        )

    @pytest.mark.asyncio
    async def test_stores_facts_with_embeddings(self):
        from app.memory.fact_extractor import extract_and_store_facts

        facts_json = '{"facts": [{"entity_name": "Gandalf", "entity_type": "npc", "content": "Gandalf arrived in town"}]}'
        mock_db = AsyncMock()
        mock_session_instance = MagicMock()
        mock_session_instance.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("app.memory.fact_extractor.get_gameplay_config") as mock_cfg:
            mock_cfg.return_value.fact_extraction_enabled = True
            with patch("app.memory.fact_extractor.route_ai_call", new_callable=AsyncMock) as mock_route:
                mock_route.return_value = MagicMock(provider="openai", model="gpt-4o-mini")
                with patch("app.memory.fact_extractor.get_provider", return_value=MagicMock()):
                    with patch("app.memory.fact_extractor.logged_generate", new_callable=AsyncMock) as mock_gen:
                        mock_gen.return_value = facts_json
                        with patch("app.memory.fact_extractor.generate_embedding", new_callable=AsyncMock) as mock_embed:
                            mock_embed.return_value = [0.1] * 1536
                            with patch("app.dependencies.async_session", return_value=mock_session_instance):
                                await extract_and_store_facts(
                                    campaign_id=uuid.uuid4(),
                                    turn_number=5,
                                    player_action="meet Gandalf",
                                    narration="Gandalf arrived in town.",
                                )
                                mock_embed.assert_called_once()
                                mock_db.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_swallows_exceptions_silently(self):
        from app.memory.fact_extractor import extract_and_store_facts

        with patch("app.memory.fact_extractor.get_gameplay_config") as mock_cfg:
            mock_cfg.return_value.fact_extraction_enabled = True
            with patch("app.memory.fact_extractor.route_ai_call", side_effect=RuntimeError("API error")):
                # Should not raise
                await extract_and_store_facts(
                    campaign_id=uuid.uuid4(),
                    turn_number=1,
                    player_action="test",
                    narration="test",
                )

    @pytest.mark.asyncio
    async def test_handles_empty_llm_response(self):
        from app.memory.fact_extractor import extract_and_store_facts

        with patch("app.memory.fact_extractor.get_gameplay_config") as mock_cfg:
            mock_cfg.return_value.fact_extraction_enabled = True
            with patch("app.memory.fact_extractor.route_ai_call", new_callable=AsyncMock) as mock_route:
                mock_route.return_value = MagicMock(provider="openai", model="gpt-4o-mini")
                with patch("app.memory.fact_extractor.get_provider", return_value=MagicMock()):
                    with patch("app.memory.fact_extractor.logged_generate", new_callable=AsyncMock) as mock_gen:
                        mock_gen.return_value = "   "
                        # Should complete without error (empty response → early return)
                        await extract_and_store_facts(
                            campaign_id=uuid.uuid4(),
                            turn_number=1,
                            player_action="test",
                            narration="test",
                        )

    @pytest.mark.asyncio
    async def test_skips_facts_missing_entity_or_content(self):
        from app.memory.fact_extractor import extract_and_store_facts

        facts_json = '{"facts": [{"entity_name": "", "entity_type": "npc", "content": "some content"}, {"entity_name": "Valid", "entity_type": "npc", "content": ""}]}'
        mock_db = AsyncMock()
        mock_session_instance = MagicMock()
        mock_session_instance.__aenter__ = AsyncMock(return_value=mock_db)
        mock_session_instance.__aexit__ = AsyncMock(return_value=False)

        with patch("app.memory.fact_extractor.get_gameplay_config") as mock_cfg:
            mock_cfg.return_value.fact_extraction_enabled = True
            with patch("app.memory.fact_extractor.route_ai_call", new_callable=AsyncMock) as mock_route:
                mock_route.return_value = MagicMock(provider="openai", model="gpt-4o-mini")
                with patch("app.memory.fact_extractor.get_provider", return_value=MagicMock()):
                    with patch("app.memory.fact_extractor.logged_generate", new_callable=AsyncMock) as mock_gen:
                        mock_gen.return_value = facts_json
                        with patch("app.memory.fact_extractor.generate_embedding", new_callable=AsyncMock):
                            with patch("app.dependencies.async_session", return_value=mock_session_instance):
                                await extract_and_store_facts(
                                    campaign_id=uuid.uuid4(),
                                    turn_number=1,
                                    player_action="test",
                                    narration="test",
                                )
                                mock_db.add.assert_not_called()
