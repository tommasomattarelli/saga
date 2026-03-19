"""Abstract AI provider interface."""

from abc import ABC, abstractmethod


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
    ):
        """Stream a response from the AI model, yielding chunks."""
        ...


# Provider registry
_providers: dict[str, AIProvider] = {}


def register_provider(name: str, provider: AIProvider) -> None:
    """Register an AI provider."""
    _providers[name] = provider


def get_provider(name: str) -> AIProvider:
    """Get a registered AI provider by name."""
    if name not in _providers:
        # Lazy initialization
        if name == "openai":
            from app.ai.providers.openai import OpenAIProvider
            _providers[name] = OpenAIProvider()
        elif name == "anthropic":
            from app.ai.providers.anthropic import AnthropicProvider
            _providers[name] = AnthropicProvider()
        elif name == "google":
            from app.ai.providers.google import GoogleProvider
            _providers[name] = GoogleProvider()
        else:
            raise ValueError(f"Unknown AI provider: {name}")
    return _providers[name]
