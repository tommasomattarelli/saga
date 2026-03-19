"""Google Gemini provider."""

from collections.abc import AsyncIterator

import structlog
from google import genai

from app.ai.providers.base import AIProvider
from app.config import settings

logger = structlog.get_logger()


class GoogleProvider(AIProvider):
    """Google Gemini API provider."""

    def __init__(self, api_key: str | None = None) -> None:
        self.client = genai.Client(api_key=api_key or settings.google_ai_api_key)

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str = "gemini-2.5-pro",
        temperature: float = 0.8,
        max_tokens: int = 2000,
    ) -> str:
        """Generate a response via Gemini API."""
        # Convert message format
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})

        response = await self.client.aio.models.generate_content(
            model=model,
            contents=contents,
            config={
                "system_instruction": system_prompt,
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            },
        )
        return response.text or ""

    async def stream(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str = "gemini-2.5-pro",
        temperature: float = 0.8,
        max_tokens: int = 2000,
    ) -> AsyncIterator[str]:
        """Stream a response via Gemini API."""
        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            contents.append({"role": role, "parts": [{"text": msg["content"]}]})

        response = await self.client.aio.models.generate_content_stream(
            model=model,
            contents=contents,
            config={
                "system_instruction": system_prompt,
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            },
        )
        async for chunk in response:
            if chunk.text:
                yield chunk.text
