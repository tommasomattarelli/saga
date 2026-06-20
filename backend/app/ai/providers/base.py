"""Abstract AI provider interface."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.ai.providers.schemas import AgentResponse

_llm_io = logging.getLogger("llm_io")


class AIProvider(ABC):
    """Base class for AI providers."""

    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str,
        temperature: float = 0.8,
        max_tokens: int = 2000,
        json_mode: bool = False,
    ) -> str:
        """Generate a response from the AI model."""
        ...

    @abstractmethod
    def stream(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str,
        temperature: float = 0.8,
        max_tokens: int = 2000,
    ) -> AsyncIterator[str]:
        """Stream a response from the AI model, yielding text chunks."""
        ...

    async def generate_with_tools(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[dict],
        model: str,
        temperature: float = 0.8,
        max_tokens: int = 2000,
    ) -> AgentResponse:
        """Generate a response with tool-calling support."""
        raise NotImplementedError(f"{self.__class__.__name__} does not support tool calling")


async def logged_generate(
    provider: AIProvider,
    *,
    caller: str,
    system_prompt: str,
    messages: list[dict],
    model: str,
    temperature: float = 0.8,
    max_tokens: int = 2000,
    json_mode: bool = False,
) -> str:
    """Wrap provider.generate() with full I/O logging to llm_io.log."""
    _llm_io.info(
        json.dumps(
            {
                "direction": "input",
                "caller": caller,
                "model": model,
                "system_prompt": system_prompt,
                "messages": messages,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
        + ("─" * 80)
    )

    result = await provider.generate(
        system_prompt=system_prompt,
        messages=messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=json_mode,
    )

    _llm_io.info(
        json.dumps(
            {
                "direction": "output",
                "caller": caller,
                "text": result,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
        + ("═" * 80)
    )

    return result


# Provider registry
_providers: dict[str, AIProvider] = {}


def get_provider(name: str) -> AIProvider:
    """Get a registered AI provider by name (lazy initialization)."""
    if name not in _providers:
        if name == "openai":
            from app.ai.providers.openai import OpenAIProvider

            _providers[name] = OpenAIProvider()
        elif name == "anthropic":
            from app.ai.providers.anthropic import AnthropicProvider

            _providers[name] = AnthropicProvider()
        elif name == "google":
            from app.ai.providers.google import GoogleProvider

            _providers[name] = GoogleProvider()
        elif name == "local":
            from app.ai.providers.local import LocalProvider
            from app.config import settings

            _providers[name] = LocalProvider(base_url=settings.local_model_url)
        elif name == "openrouter":
            from app.ai.providers.local import LocalProvider
            from app.config import settings

            _providers[name] = LocalProvider(
                base_url="https://openrouter.ai/api/v1",
                api_key=settings.openrouter_api_key,
            )
        elif name == "cohere":
            from app.ai.providers.local import LocalProvider
            from app.config import settings

            _providers[name] = LocalProvider(
                base_url="https://api.cohere.ai/compatibility/v1",
                api_key=settings.cohere_api_key,
            )
        elif name == "groq":
            from app.ai.providers.local import LocalProvider
            from app.config import settings

            _providers[name] = LocalProvider(
                base_url="https://api.groq.com/openai/v1",
                api_key=settings.groq_api_key,
            )
        else:
            raise ValueError(f"Unknown AI provider: {name}")
    return _providers[name]
