"""Local model provider (future: vLLM / Ollama)."""

from collections.abc import AsyncIterator

import httpx
import structlog

from app.ai.providers.base import AIProvider

logger = structlog.get_logger()


class LocalProvider(AIProvider):
    """Local self-hosted model provider via OpenAI-compatible API."""

    def __init__(self, base_url: str = "http://localhost:8080/v1") -> None:
        self.base_url = base_url

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str = "local",
        temperature: float = 0.8,
        max_tokens: int = 2000,
    ) -> str:
        """Generate a response from a local model."""
        full_messages = [{"role": "system", "content": system_prompt}] + messages

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": model,
                    "messages": full_messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                timeout=120.0,
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

    async def stream(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str = "local",
        temperature: float = 0.8,
        max_tokens: int = 2000,
    ) -> AsyncIterator[str]:
        """Stream from a local model (not yet implemented)."""
        result = await self.generate(system_prompt, messages, model, temperature, max_tokens)
        yield result
