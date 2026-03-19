"""Anthropic provider (Claude Sonnet, Opus)."""

from collections.abc import AsyncIterator

import anthropic
import structlog

from app.ai.providers.base import AIProvider
from app.config import settings

logger = structlog.get_logger()


class AnthropicProvider(AIProvider):
    """Anthropic Claude API provider."""

    def __init__(self, api_key: str | None = None) -> None:
        self.client = anthropic.AsyncAnthropic(api_key=api_key or settings.anthropic_api_key)

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str = "claude-sonnet-4-20250514",
        temperature: float = 0.8,
        max_tokens: int = 2000,
    ) -> str:
        """Generate a response via Anthropic API."""
        response = await self.client.messages.create(
            model=model,
            system=system_prompt,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return response.content[0].text

    async def stream(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str = "claude-sonnet-4-20250514",
        temperature: float = 0.8,
        max_tokens: int = 2000,
    ) -> AsyncIterator[str]:
        """Stream a response via Anthropic API."""
        async with self.client.messages.stream(
            model=model,
            system=system_prompt,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        ) as stream:
            async for text in stream.text_stream:
                yield text
