"""Anthropic provider (Claude Sonnet, Opus)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import anthropic
import structlog

from app.ai.exceptions import ContentPolicyError
from app.ai.providers.base import AIProvider
from app.ai.providers.schemas import AgentResponse, ToolCall
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
        json_mode: bool = False,
    ) -> str:
        # Anthropic lacks native json_mode; the prompt already contains the JSON schema.
        response = await self.client.messages.create(
            model=model,
            system=system_prompt,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if response.stop_reason == "end_turn" and not response.content:
            raise ContentPolicyError("anthropic", "Empty response — possible policy block")
        return response.content[0].text

    async def stream(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str = "claude-sonnet-4-20250514",
        temperature: float = 0.8,
        max_tokens: int = 2000,
    ) -> AsyncIterator[str]:
        async with self.client.messages.stream(
            model=model,
            system=system_prompt,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def generate_with_tools(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[dict],
        model: str = "claude-sonnet-4-20250514",
        temperature: float = 0.8,
        max_tokens: int = 2000,
    ) -> AgentResponse:
        # Convert OpenAI-format tool schemas to Anthropic format
        anthropic_tools = [
            {
                "name": t["function"]["name"],
                "description": t["function"]["description"],
                "input_schema": t["function"]["parameters"],
            }
            for t in tools
        ]
        response = await self.client.messages.create(
            model=model,
            system=system_prompt,
            messages=messages,
            tools=anthropic_tools,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if response.stop_reason == "end_turn" and not response.content:
            raise ContentPolicyError("anthropic", "Empty response — possible policy block")

        text = ""
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                text += block.text
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(id=block.id, name=block.name, arguments=block.input))

        return AgentResponse(text=text, tool_calls=tool_calls)
