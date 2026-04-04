"""Abstract AI provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.ai.providers.schemas import AgentChunk, AgentResponse


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
    ) -> str:
        """Generate a response from the AI model."""
        ...

    @abstractmethod
    async def stream(
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

    async def stream_with_tools(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[dict],
        model: str,
        temperature: float = 0.8,
        max_tokens: int = 2000,
    ) -> AsyncIterator[AgentChunk]:
        """Stream a response, yielding text chunks and tool call chunks."""
        raise NotImplementedError(f"{self.__class__.__name__} does not support tool calling")
        yield  # make it a generator

    def format_tool_result(self, tool_call_id: str, tool_name: str, result: str) -> dict:
        """Format a tool result message to append to the conversation."""
        raise NotImplementedError(f"{self.__class__.__name__} does not support tool calling")


# Provider registry
_providers: dict[str, AIProvider] = {}


def register_provider(name: str, provider: AIProvider) -> None:
    _providers[name] = provider


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
        else:
            raise ValueError(f"Unknown AI provider: {name}")
    return _providers[name]
