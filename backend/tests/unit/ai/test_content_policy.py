"""Tests for ContentPolicyError handling in providers."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ai.exceptions import ContentPolicyError


class TestContentPolicyError:
    def test_error_attributes(self):
        err = ContentPolicyError("openai", "blocked")
        assert err.provider == "openai"
        assert "openai" in str(err)
        assert err.status_code == 422

    def test_error_without_detail(self):
        err = ContentPolicyError("anthropic")
        assert "anthropic" in str(err)


class TestOpenAIContentPolicy:
    @pytest.mark.asyncio
    async def test_content_filter_raises(self):
        from app.ai.providers.openai import OpenAIProvider

        provider = OpenAIProvider.__new__(OpenAIProvider)

        mock_choice = MagicMock()
        mock_choice.finish_reason = "content_filter"
        mock_choice.message.content = ""

        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)
        provider.client = mock_client

        with pytest.raises(ContentPolicyError, match="openai"):
            await provider.generate(
                system_prompt="test",
                messages=[{"role": "user", "content": "test"}],
                model="gpt-4o",
            )


class TestAnthropicContentPolicy:
    @pytest.mark.asyncio
    async def test_empty_response_raises(self):
        from app.ai.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider.__new__(AnthropicProvider)

        mock_response = MagicMock()
        mock_response.stop_reason = "end_turn"
        mock_response.content = []

        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_response)
        provider.client = mock_client

        with pytest.raises(ContentPolicyError, match="anthropic"):
            await provider.generate(
                system_prompt="test",
                messages=[{"role": "user", "content": "test"}],
                model="claude-sonnet-4-20250514",
            )


class TestGoogleContentPolicy:
    @pytest.mark.asyncio
    async def test_safety_finish_reason_raises(self):
        from app.ai.providers.google import GoogleProvider

        provider = GoogleProvider.__new__(GoogleProvider)

        mock_candidate = MagicMock()
        mock_candidate.finish_reason = "SAFETY"

        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]
        mock_response.text = ""

        mock_client = MagicMock()
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
        provider.client = mock_client

        with pytest.raises(ContentPolicyError, match="google"):
            await provider.generate(
                system_prompt="test",
                messages=[{"role": "user", "content": "test"}],
                model="gemini-2.5-pro",
            )
