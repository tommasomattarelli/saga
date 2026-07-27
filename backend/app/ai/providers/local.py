"""Local / OpenRouter provider — OpenAI-compatible API."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import openai
import structlog

from app.ai.exceptions import ContentPolicyError
from app.ai.providers.base import AIProvider
from app.ai.providers.openai_compat import first_choice, stream_choice
from app.ai.providers.schemas import AgentResponse, ToolCall

logger = structlog.get_logger()


class LocalProvider(AIProvider):
    """Any OpenAI-compatible endpoint: local models (Ollama, LM Studio) or OpenRouter."""

    def __init__(
        self, base_url: str = "http://localhost:8080/v1", api_key: str | None = None
    ) -> None:
        self.client = openai.AsyncOpenAI(
            base_url=base_url,
            api_key=api_key or "local",  # Many local servers accept any non-empty key
        )

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str = "local",
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
        choice = first_choice(response, "local")
        if choice.finish_reason == "content_filter":
            raise ContentPolicyError("local", "Response blocked by content filter")
        return choice.message.content or ""

    async def stream(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str = "local",
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
            choice = stream_choice(chunk, "local")
            if choice is None:
                continue
            delta = choice.delta.content
            if delta:
                yield delta

    async def generate_with_tools(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[dict],
        model: str = "local",
        temperature: float = 0.8,
        max_tokens: int = 2000,
    ) -> AgentResponse:
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        response = await self.client.chat.completions.create(  # type: ignore[call-overload]
            model=model,
            messages=full_messages,
            tools=tools,
            tool_choice="auto",
            temperature=temperature,
            max_tokens=max_tokens,
        )
        msg = first_choice(response, "local").message
        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        return AgentResponse(text=msg.content or "", tool_calls=tool_calls)
