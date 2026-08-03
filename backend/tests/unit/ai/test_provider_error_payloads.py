"""OpenAI-compatible gateways report upstream failures as HTTP 200 with an in-band
`error` object and no `choices` — the SDK deserializes it happily, so the guard has
to live in the provider (#50)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.ai.providers.local import LocalProvider
from app.ai.providers.openai import OpenAIProvider
from app.exceptions import AIProviderError

PROVIDERS = [LocalProvider, OpenAIProvider]
UPSTREAM_ERROR = {"code": 429, "message": "Rate limit exceeded: free-models-per-day"}
MESSAGES = [{"role": "user", "content": "hi"}]


def _make(cls, response):
    provider = cls.__new__(cls)
    provider.client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(return_value=response)))
    )
    return provider


async def _chunks(*items):
    for item in items:
        yield item


@pytest.mark.parametrize("cls", PROVIDERS)
@pytest.mark.asyncio
async def test_generate_surfaces_upstream_error(cls):
    provider = _make(cls, SimpleNamespace(choices=None, error=UPSTREAM_ERROR))

    with pytest.raises(AIProviderError, match="Rate limit exceeded"):
        await provider.generate("sys", MESSAGES)


@pytest.mark.parametrize("cls", PROVIDERS)
@pytest.mark.asyncio
async def test_generate_with_tools_surfaces_upstream_error(cls):
    provider = _make(cls, SimpleNamespace(choices=None, error=UPSTREAM_ERROR))

    with pytest.raises(AIProviderError, match="429"):
        await provider.generate_with_tools("sys", MESSAGES, tools=[])


@pytest.mark.parametrize("cls", PROVIDERS)
@pytest.mark.asyncio
async def test_empty_choices_without_error_payload_still_raises(cls):
    provider = _make(cls, SimpleNamespace(choices=[]))

    with pytest.raises(AIProviderError):
        await provider.generate("sys", MESSAGES)


@pytest.mark.parametrize("cls", PROVIDERS)
@pytest.mark.asyncio
async def test_generate_rejects_a_truncated_response(cls):
    """A cut-off answer must not be stored as a result: on a reasoning model what
    survives the budget is deliberation, and the summarisers validate nothing (#77)."""
    cut = SimpleNamespace(
        finish_reason="length",
        message=SimpleNamespace(content="Let me analyse the turns. Turn 16: Tavern"),
    )
    provider = _make(cls, SimpleNamespace(choices=[cut]))

    with pytest.raises(AIProviderError, match="truncated"):
        await provider.generate("sys", MESSAGES)


@pytest.mark.parametrize("cls", PROVIDERS)
@pytest.mark.asyncio
async def test_generate_with_tools_rejects_a_truncated_response(cls):
    cut = SimpleNamespace(
        finish_reason="length", message=SimpleNamespace(content="", tool_calls=[])
    )
    provider = _make(cls, SimpleNamespace(choices=[cut]))

    with pytest.raises(AIProviderError, match="truncated"):
        await provider.generate_with_tools("sys", MESSAGES, tools=[])


@pytest.mark.parametrize("cls", PROVIDERS)
@pytest.mark.asyncio
async def test_stream_surfaces_upstream_error(cls):
    provider = _make(cls, _chunks(SimpleNamespace(choices=[], error=UPSTREAM_ERROR)))

    with pytest.raises(AIProviderError, match="Rate limit exceeded"):
        [delta async for delta in provider.stream("sys", MESSAGES)]


@pytest.mark.parametrize("cls", PROVIDERS)
@pytest.mark.asyncio
async def test_stream_skips_chunk_without_choices(cls):
    text = SimpleNamespace(
        choices=[SimpleNamespace(delta=SimpleNamespace(content="ok"), finish_reason=None)]
    )
    provider = _make(cls, _chunks(SimpleNamespace(choices=[]), text))

    assert [delta async for delta in provider.stream("sys", MESSAGES)] == ["ok"]
