"""Unit tests for app/memory/fact_extractor.py."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _patched_extractor(raw: str):
    """Patch the provider round-trip so only the parsing half is exercised."""
    return (
        patch("app.memory.fact_extractor.route_ai_call", new_callable=AsyncMock),
        patch("app.memory.fact_extractor.get_provider", return_value=MagicMock()),
        patch(
            "app.memory.fact_extractor.logged_generate", new_callable=AsyncMock, return_value=raw
        ),
    )


class TestExtractFacts:
    """The derive pass reuses this without a database, so it must return facts, not store them."""

    async def _extract(self, raw: str) -> list[dict]:
        from app.memory.fact_extractor import extract_facts

        route, provider, generate = _patched_extractor(raw)
        with route as mock_route, provider, generate:
            mock_route.return_value = MagicMock(provider="openai", model="gpt-4o-mini")
            return await extract_facts("look around", "The hall is empty.")

    @pytest.mark.asyncio
    async def test_returns_parsed_facts(self):
        facts = await self._extract(
            '{"facts": [{"entity_name": "Lyra", "entity_type": "npc", "content": "Lyra is wary."}]}'
        )
        assert facts == [{"entity_name": "Lyra", "entity_type": "npc", "content": "Lyra is wary."}]

    @pytest.mark.asyncio
    async def test_accepts_a_bare_list(self):
        facts = await self._extract('[{"entity_name": "Hall", "content": "The hall is empty."}]')
        assert len(facts) == 1

    @pytest.mark.asyncio
    async def test_caps_at_five(self):
        entries = ", ".join(f'{{"entity_name": "N{i}", "content": "c"}}' for i in range(8))
        assert len(await self._extract(f'{{"facts": [{entries}]}}')) == 5

    @pytest.mark.asyncio
    async def test_drops_non_objects(self):
        facts = await self._extract('{"facts": ["junk", {"entity_name": "N", "content": "c"}]}')
        assert facts == [{"entity_name": "N", "content": "c"}]

    @pytest.mark.asyncio
    async def test_unusable_entries_do_not_consume_a_slot(self):
        entries = ", ".join(f'{{"entity_name": "N{i}", "content": "c"}}' for i in range(6))
        facts = await self._extract(f'{{"facts": ["junk", {entries}]}}')
        assert len(facts) == 5

    @pytest.mark.asyncio
    async def test_drops_entries_without_a_name_or_a_body(self):
        facts = await self._extract(
            '{"facts": [{"entity_name": "", "content": "c"},'
            ' {"entity_name": "N", "content": "   "},'
            ' {"entity_name": 7, "content": "c"}]}'
        )
        assert facts == [{"entity_name": 7, "content": "c"}]

    @pytest.mark.asyncio
    async def test_returns_empty_on_unparseable_output(self):
        assert await self._extract("not json at all {{{") == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_oversized_output(self):
        assert await self._extract("x" * 5000) == []


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
            with (
                patch(
                    "app.memory.fact_extractor.route_ai_call", new_callable=AsyncMock
                ) as mock_route,
                patch("app.memory.fact_extractor.get_provider", return_value=MagicMock()),
                patch(
                    "app.memory.fact_extractor.logged_generate", new_callable=AsyncMock
                ) as mock_gen,
            ):
                mock_route.return_value = MagicMock(provider="openai", model="gpt-4o-mini")
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
            with (
                patch(
                    "app.memory.fact_extractor.route_ai_call", new_callable=AsyncMock
                ) as mock_route,
                patch("app.memory.fact_extractor.get_provider", return_value=MagicMock()),
                patch(
                    "app.memory.fact_extractor.logged_generate", new_callable=AsyncMock
                ) as mock_gen,
            ):
                mock_route.return_value = MagicMock(provider="openai", model="gpt-4o-mini")
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
            with (
                patch(
                    "app.memory.fact_extractor.route_ai_call", new_callable=AsyncMock
                ) as mock_route,
                patch("app.memory.fact_extractor.get_provider", return_value=MagicMock()),
                patch(
                    "app.memory.fact_extractor.logged_generate", new_callable=AsyncMock
                ) as mock_gen,
                patch(
                    "app.memory.fact_extractor.generate_embedding", new_callable=AsyncMock
                ) as mock_embed,
                patch("app.dependencies.async_session", return_value=mock_session_instance),
            ):
                mock_route.return_value = MagicMock(provider="openai", model="gpt-4o-mini")
                mock_gen.return_value = facts_json
                mock_embed.return_value = [0.1] * 1536
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
            with patch(
                "app.memory.fact_extractor.route_ai_call", side_effect=RuntimeError("API error")
            ):
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
            with (
                patch(
                    "app.memory.fact_extractor.route_ai_call", new_callable=AsyncMock
                ) as mock_route,
                patch("app.memory.fact_extractor.get_provider", return_value=MagicMock()),
                patch(
                    "app.memory.fact_extractor.logged_generate", new_callable=AsyncMock
                ) as mock_gen,
            ):
                mock_route.return_value = MagicMock(provider="openai", model="gpt-4o-mini")
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
            with (
                patch(
                    "app.memory.fact_extractor.route_ai_call", new_callable=AsyncMock
                ) as mock_route,
                patch("app.memory.fact_extractor.get_provider", return_value=MagicMock()),
                patch(
                    "app.memory.fact_extractor.logged_generate", new_callable=AsyncMock
                ) as mock_gen,
                patch("app.memory.fact_extractor.generate_embedding", new_callable=AsyncMock),
                patch("app.dependencies.async_session", return_value=mock_session_instance),
            ):
                mock_route.return_value = MagicMock(provider="openai", model="gpt-4o-mini")
                mock_gen.return_value = facts_json
                await extract_and_store_facts(
                    campaign_id=uuid.uuid4(),
                    turn_number=1,
                    player_action="test",
                    narration="test",
                )
                mock_db.add.assert_not_called()
