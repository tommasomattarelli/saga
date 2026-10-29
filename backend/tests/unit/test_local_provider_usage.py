from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.ai.exceptions import ContentPolicyError
from app.ai.providers.local import LocalProvider
from app.ai.providers.usage import usage_scope


def completion(reason: str, content: str = "{}") -> SimpleNamespace:
    return SimpleNamespace(
        id="id1",
        model="model",
        usage={"prompt_tokens": 3},
        choices=[
            SimpleNamespace(
                finish_reason=reason, message=SimpleNamespace(content=content, tool_calls=None)
            )
        ],
    )


def provider_with(response: object) -> LocalProvider:
    provider = LocalProvider()
    provider.client.chat.completions.create = AsyncMock(return_value=response)
    return provider


@pytest.mark.asyncio
async def test_generate_captures_usage_before_content_filter_error() -> None:
    provider = provider_with(completion("content_filter"))
    with usage_scope() as collector, pytest.raises(ContentPolicyError):
        await provider.generate("system", [], model="m")
    assert collector.items[0].input_tokens == 3
    provider.client.chat.completions.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_captures_usage_before_length_error() -> None:
    provider = provider_with(completion("length"))
    with usage_scope() as collector, pytest.raises(Exception, match="truncated"):
        await provider.generate("system", [], model="m")
    assert collector.items[0].input_tokens == 3


@pytest.mark.asyncio
async def test_generate_with_tools_captures_usage_before_length_error() -> None:
    provider = provider_with(completion("length"))
    with usage_scope() as collector, pytest.raises(Exception, match="truncated"):
        await provider.generate_with_tools("system", [], [], model="m")
    assert collector.items[0].input_tokens == 3
