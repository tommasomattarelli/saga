"""Anthropic provider (Claude Sonnet, Opus)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import anthropic
import structlog

from app.ai.exceptions import ContentPolicyError
from app.ai.providers.base import AIProvider
from app.ai.providers.schemas import AgentChunk, AgentResponse, TextChunk, ToolCall, ToolCallChunk
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

    async def stream_with_tools(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[dict],
        model: str = "claude-sonnet-4-20250514",
        temperature: float = 0.8,
        max_tokens: int = 2000,
    ) -> AsyncIterator[AgentChunk]:
        anthropic_tools = [
            {
                "name": t["function"]["name"],
                "description": t["function"]["description"],
                "input_schema": t["function"]["parameters"],
            }
            for t in tools
        ]
        # Anthropic streaming with tools: text blocks stream, tool_use blocks come complete
        async with self.client.messages.stream(
            model=model,
            system=system_prompt,
            messages=messages,
            tools=anthropic_tools,
            temperature=temperature,
            max_tokens=max_tokens,
        ) as stream:
            async for event in stream:
                if event.type == "content_block_delta":
                    if hasattr(event.delta, "text"):
                        yield TextChunk(text=event.delta.text)
                elif event.type == "message_stop":
                    # Emit completed tool_use blocks
                    final = await stream.get_final_message()
                    for block in final.content:
                        if block.type == "tool_use":
                            yield ToolCallChunk(
                                tool_call=ToolCall(
                                    id=block.id, name=block.name, arguments=block.input
                                )
                            )

    def format_tool_result(self, tool_call_id: str, tool_name: str, result: str) -> dict:
        return {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": tool_call_id, "content": result}],
        }
