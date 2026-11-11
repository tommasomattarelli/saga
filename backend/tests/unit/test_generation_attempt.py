import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.ai.generation_attempt import (
    generation_attempt_is_single,
    single_generation_attempt,
)
from app.ai.providers.google import GoogleProvider
from app.ai.providers.local import LocalProvider
from app.ai.providers.openai import OpenAIProvider


def test_generation_attempt_resets_after_exception() -> None:
    assert not generation_attempt_is_single()
    with pytest.raises(RuntimeError), single_generation_attempt():
        assert generation_attempt_is_single()
        raise RuntimeError("failure")
    assert not generation_attempt_is_single()


@pytest.mark.asyncio
async def test_generation_attempt_context_isolated_between_tasks() -> None:
    entered = asyncio.Event()

    async def opted_in() -> bool:
        with single_generation_attempt():
            entered.set()
            await asyncio.sleep(0)
            return generation_attempt_is_single()

    async def ordinary() -> bool:
        await entered.wait()
        return generation_attempt_is_single()

    assert await asyncio.gather(opted_in(), ordinary()) == [True, False]
    assert not generation_attempt_is_single()


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_type", [OpenAIProvider, LocalProvider])
async def test_openai_compatible_uses_nonretrying_client_only_when_opted_in(
    provider_type: type[OpenAIProvider] | type[LocalProvider],
) -> None:
    provider = provider_type(api_key="test-key")
    response = SimpleNamespace(
        choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content="ok"))]
    )
    cached_create = AsyncMock(return_value=response)
    retryless_create = AsyncMock(return_value=response)
    provider.client.chat.completions.create = cached_create
    retryless = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=retryless_create))
    )
    provider.client.with_options = Mock(return_value=retryless)

    await provider.generate("system", [], model="m")
    cached_create.assert_awaited_once()
    provider.client.with_options.assert_not_called()

    with single_generation_attempt():
        await provider.generate("system", [], model="m")
    provider.client.with_options.assert_called_once_with(max_retries=0)
    retryless_create.assert_awaited_once()
    cached_create.assert_awaited_once()


@pytest.mark.asyncio
async def test_google_503_is_not_retried_when_opted_in() -> None:
    provider = GoogleProvider(api_key="test-key")
    generate_content = AsyncMock(side_effect=RuntimeError("503 unavailable"))
    provider.client.aio.models.generate_content = generate_content

    with single_generation_attempt(), pytest.raises(RuntimeError, match="503"):
        await provider.generate("system", [], model="m")
    generate_content.assert_awaited_once()
    config = generate_content.await_args.kwargs["config"]
    assert config.http_options.retry_options.attempts == 1


@pytest.mark.asyncio
async def test_google_default_generation_keeps_503_retry_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = GoogleProvider(api_key="test-key")
    generate_content = AsyncMock(
        side_effect=[RuntimeError("503 unavailable"), SimpleNamespace(text="ok")]
    )
    provider.client.aio.models.generate_content = generate_content
    monkeypatch.setattr("app.ai.providers.google._RETRY_DELAYS", [0])

    assert await provider.generate("system", [], model="m") == "ok"
    assert generate_content.await_count == 2
    assert generate_content.await_args.kwargs["config"].http_options is None
