"""OpenAI provider (GPT-4o, GPT-4o-mini)."""

from collections.abc import AsyncIterator

import openai
import structlog

from app.ai.exceptions import ContentPolicyError
from app.ai.providers.base import AIProvider
from app.config import settings

logger = structlog.get_logger()


class OpenAIProvider(AIProvider):
    """OpenAI API provider."""

    def __init__(self, api_key: str | None = None) -> None:
        self.client = openai.AsyncOpenAI(api_key=api_key or settings.openai_api_key)

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str = "gpt-4o",
        temperature: float = 0.8,
        max_tokens: int = 2000,
    ) -> str:
        """Generate a response via OpenAI API."""
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        response = await self.client.chat.completions.create(
            model=model,
            messages=full_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        choice = response.choices[0]
        if choice.finish_reason == "content_filter":
            raise ContentPolicyError("openai", "Response blocked by content filter")

        return choice.message.content or ""

    async def stream(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str = "gpt-4o",
        temperature: float = 0.8,
        max_tokens: int = 2000,
    ) -> AsyncIterator[str]:
        """Stream a response via OpenAI API."""
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        stream = await self.client.chat.completions.create(
            model=model,
            messages=full_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            choice = chunk.choices[0]
            if choice.finish_reason == "content_filter":
                raise ContentPolicyError("openai", "Stream blocked by content filter")
            delta = choice.delta.content
            if delta:
                yield delta
