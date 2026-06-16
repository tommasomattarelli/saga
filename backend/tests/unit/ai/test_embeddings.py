"""Unit tests for app/ai/embeddings.py."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestGenerateEmbedding:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_api_key(self):
        from app.ai.embeddings import generate_embedding

        with patch("app.ai.embeddings.settings") as mock_settings:
            mock_settings.openai_api_key = None
            result = await generate_embedding("test text")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_empty_api_key(self):
        from app.ai.embeddings import generate_embedding

        with patch("app.ai.embeddings.settings") as mock_settings:
            mock_settings.openai_api_key = ""
            result = await generate_embedding("test text")

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_embedding_on_success(self):
        from app.ai.embeddings import generate_embedding

        mock_embedding = [0.1, 0.2, 0.3]
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": [{"embedding": mock_embedding}]}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.ai.embeddings.settings") as mock_settings:
            mock_settings.openai_api_key = "sk-test"
            with patch("app.ai.embeddings.httpx.AsyncClient", return_value=mock_client):
                result = await generate_embedding("hello world")

        assert result == mock_embedding

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self):
        from app.ai.embeddings import generate_embedding

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("network error"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("app.ai.embeddings.settings") as mock_settings:
            mock_settings.openai_api_key = "sk-test"
            with patch("app.ai.embeddings.httpx.AsyncClient", return_value=mock_client):
                result = await generate_embedding("text that fails")

        assert result is None

    @pytest.mark.asyncio
    async def test_truncates_long_text_at_8000_chars(self):
        from app.ai.embeddings import generate_embedding

        mock_embedding = [0.5] * 384
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": [{"embedding": mock_embedding}]}
        mock_response.raise_for_status = MagicMock()

        captured_payload = {}

        async def mock_post(url, headers, json, timeout):
            captured_payload["input"] = json["input"]
            return mock_response

        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        long_text = "x" * 10000
        with patch("app.ai.embeddings.settings") as mock_settings:
            mock_settings.openai_api_key = "sk-test"
            with patch("app.ai.embeddings.httpx.AsyncClient", return_value=mock_client):
                await generate_embedding(long_text)

        assert len(captured_payload["input"]) == 8000
