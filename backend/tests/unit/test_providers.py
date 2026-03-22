import pytest
from unittest.mock import AsyncMock, MagicMock

from app.ai.providers.openai import OpenAIProvider
from app.ai.providers.anthropic import AnthropicProvider
from app.ai.providers.google import GoogleProvider
from app.ai.providers.local import LocalProvider


@pytest.mark.asyncio
async def test_openai_generate(mocker):
    mocker.patch("app.ai.providers.openai.openai.AsyncOpenAI")
    provider = OpenAIProvider(api_key="sk-test")

    mock_choice = MagicMock()
    mock_choice.message.content = "openai_response"
    mock_comp = MagicMock()
    mock_comp.choices = [mock_choice]

    provider.client.chat.completions.create = AsyncMock(return_value=mock_comp)

    res = await provider.generate("sys", [{"role": "user", "content": "hi"}])
    assert res == "openai_response"
