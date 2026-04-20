"""Local / OpenRouter provider — OpenAI-compatible API."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import openai
import structlog

from app.ai.exceptions import ContentPolicyError
from app.ai.providers.base import AIProvider
from app.ai.providers.schemas import AgentChunk, AgentResponse, TextChunk, ToolCall, ToolCallChunk

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
    ) -> str:
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        response = await self.client.chat.completions.create(
            model=model,
            messages=full_messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        choice = response.choices[0]
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
            delta = chunk.choices[0].delta.content
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
        response = await self.client.chat.completions.create(
            model=model,
            messages=full_messages,
            tools=tools,
            tool_choice="auto",
            temperature=temperature,
            max_tokens=max_tokens,
        )
        msg = response.choices[0].message
        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
        return AgentResponse(text=msg.content or "", tool_calls=tool_calls)

    async def stream_with_tools(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[dict],
        model: str = "local",
        temperature: float = 0.8,
        max_tokens: int = 2000,
    ) -> AsyncIterator[AgentChunk]:
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        pending_tools: dict[int, dict] = {}

        stream = await self.client.chat.completions.create(
            model=model,
            messages=full_messages,
            tools=tools,
            tool_choice="auto",
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        try:
            async for chunk in stream:
                choice = chunk.choices[0]
                delta = choice.delta

                if delta.content:
                    yield TextChunk(text=delta.content)

                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in pending_tools:
                            pending_tools[idx] = {"id": "", "name": "", "args_str": ""}
                        if tc_delta.id:
                            pending_tools[idx]["id"] = tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                pending_tools[idx]["name"] = tc_delta.function.name
                            if tc_delta.function.arguments:
                                pending_tools[idx]["args_str"] += tc_delta.function.arguments

                if choice.finish_reason in ("tool_calls", "stop") and pending_tools:
                    for entry in pending_tools.values():
                        try:
                            args = json.loads(entry["args_str"])
                        except json.JSONDecodeError:
                            args = {}
                        yield ToolCallChunk(
                            tool_call=ToolCall(id=entry["id"], name=entry["name"], arguments=args)
                        )
                    pending_tools.clear()
        except openai.APIError as e:
            if "failed_generation" in str(e).lower():
                # Model failed to generate valid tool call JSON (common with llama on Groq).
                logger.warning("stream_tool_call_failed_generation", model=model, error=str(e)[:200])
                return
            raise

    def format_tool_result(self, tool_call_id: str, tool_name: str, result: str) -> dict:
        return {"role": "tool", "tool_call_id": tool_call_id, "content": result}
