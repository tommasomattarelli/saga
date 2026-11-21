from collections.abc import AsyncIterator
from typing import cast

import pytest

from app.ai.generation_contracts import GenerationRequest
from app.ai.providers.base import AIProvider
from app.ai.providers.schemas import AgentResponse


class LegacyOnlyProvider(AIProvider):
    def __init__(self) -> None:
        self.legacy_called = False

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str,
        max_tokens: int = 2000,
        json_mode: bool = False,
    ) -> str:
        self.legacy_called = True
        return "legacy"

    def stream(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str,
        max_tokens: int = 2000,
    ) -> AsyncIterator[str]:
        raise NotImplementedError

    async def generate_with_tools(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[dict],
        model: str,
        max_tokens: int = 2000,
    ) -> AgentResponse:
        self.legacy_called = True
        return AgentResponse(text="legacy")


@pytest.mark.asyncio
async def test_unsupported_typed_send_does_not_fall_back_to_legacy_generation() -> None:
    provider = LegacyOnlyProvider()

    with pytest.raises(NotImplementedError, match="typed generation"):
        await provider.send(cast(GenerationRequest, object()))

    assert not provider.legacy_called
