"""OpenAI provider (GPT-4o, GPT-4o-mini)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import openai
import structlog

from app.ai.exceptions import ContentPolicyError
from app.ai.providers.base import AIProvider
from app.ai.providers.schemas import AgentResponse, ToolCall
from app.config import settings

logger = structlog.get_logger()


class OpenAIProvider(AIProvider):
    """OpenAI API provider (also used for OpenRouter and Local via base_url override)."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self.client = openai.AsyncOpenAI(
            api_key=api_key or settings.openai_api_key,
            base_url=base_url,
        )

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str = "gpt-4o",
        temperature: float = 0.8,
        max_tokens: int = 2000,
        json_mode: bool = False,
    ) -> str:
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        kwargs: dict = {
            "model": model,
            "messages": full_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = await self.client.chat.completions.create(**kwargs)
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

    async def generate_with_tools(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[dict],
        model: str = "gpt-4o",
        temperature: float = 0.8,
        max_tokens: int = 2000,
    ) -> AgentResponse:
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        response = await self.client.chat.completions.create(
            model=model,
            messages=full_messages,
            tools=tools,
            tool_choice="auto",
            temperature=temperature,
            max_tokens=max_tokens,
        )
        choice = response.choices[0]
        if choice.finish_reason == "content_filter":
            raise ContentPolicyError("openai", "Response blocked by content filter")

        msg = choice.message
        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))

        return AgentResponse(text=msg.content or "", tool_calls=tool_calls)
