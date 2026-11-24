"""OpenAI provider (GPT-4o, GPT-4o-mini)."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import openai
import structlog

from app.ai.exceptions import ContentPolicyError
from app.ai.generation_attempt import generation_attempt_is_single
from app.ai.generation_contracts import (
    FormatMode,
    GenerationRequest,
    GenerationToolReceipt,
    RawGenerationReceipt,
    RawToolArguments,
)
from app.ai.providers.base import AIProvider
from app.ai.providers.openai_compat import first_choice, stream_choice, strip_provider_metadata
from app.ai.providers.schemas import AgentResponse, ToolCall
from app.ai.providers.usage import capture_usage, extract_usage_metadata
from app.config import settings

logger = structlog.get_logger()


class OpenAIProvider(AIProvider):
    """OpenAI API provider (also used for OpenRouter and Local via base_url override)."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self.client = openai.AsyncOpenAI(
            api_key=api_key or settings.openai_api_key,
            base_url=base_url,
        )

    async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
        system_prompt = request.system_prompt
        if request.format_mode is FormatMode.PROMPT_ONLY:
            schema = json.dumps(
                request.canonical_schema,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            system_prompt = f"{system_prompt}\n\nReturn JSON matching this schema:\n{schema}"

        messages = [{"role": "system", "content": system_prompt}] + strip_provider_metadata(
            request.messages
        )
        kwargs: dict[str, object] = {
            "model": request.model,
            "messages": messages,
            "max_completion_tokens": request.output_limit.effective,
        }
        if request.format_mode is FormatMode.STRICT_NATIVE:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": request.contract.name,
                    "strict": True,
                    "schema": request.wire_schema,
                },
            }
        elif request.format_mode is FormatMode.JSON_MODE:
            kwargs["response_format"] = {"type": "json_object"}
        elif request.format_mode is not FormatMode.PROMPT_ONLY:
            raise ValueError("Unsupported generation format mode.")

        if request.tool_declarations:
            kwargs["tools"] = request.tool_declarations
            kwargs["tool_choice"] = "auto"

        client = self.client.with_options(max_retries=0)
        raw_response = await client.chat.completions.with_raw_response.create(**kwargs)  # type: ignore[call-overload]
        response = raw_response.parse()
        if not response.choices:
            first_choice(response, "openai")
        choice = response.choices[0]
        message = choice.message
        capture_usage(response, model=request.model)
        tool_calls = tuple(
            GenerationToolReceipt(
                call_id=tool_call.id,
                name=tool_call.function.name,
                arguments=RawToolArguments.raw_text(tool_call.function.arguments),
            )
            for tool_call in message.tool_calls or ()
        )

        return RawGenerationReceipt(
            text=message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason,
            refusal=message.refusal,
            blocked_reason="content_filter" if choice.finish_reason == "content_filter" else None,
            response_id=response.id,
            model_id=response.model,
            usage=extract_usage_metadata(response, model=request.model),
            raw_candidate=raw_response.http_response.text,
        )

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str = "gpt-4o",
        max_tokens: int = 2000,
        json_mode: bool = False,
    ) -> str:
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        kwargs: dict = {
            "model": model,
            "messages": full_messages,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        client = (
            self.client.with_options(max_retries=0)
            if generation_attempt_is_single()
            else self.client
        )
        response = await client.chat.completions.create(**kwargs)
        choice = first_choice(response, "openai")
        if choice.finish_reason == "content_filter":
            raise ContentPolicyError("openai", "Response blocked by content filter")
        return choice.message.content or ""

    async def stream(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str = "gpt-4o",
        max_tokens: int = 2000,
    ) -> AsyncIterator[str]:
        full_messages = [{"role": "system", "content": system_prompt}] + messages
        stream = await self.client.chat.completions.create(
            model=model,
            messages=full_messages,
            max_tokens=max_tokens,
            stream=True,
        )
        async for chunk in stream:
            choice = stream_choice(chunk, "openai")
            if choice is None:
                continue
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
        max_tokens: int = 2000,
    ) -> AgentResponse:
        full_messages = [{"role": "system", "content": system_prompt}] + strip_provider_metadata(
            messages
        )
        response = await self.client.chat.completions.create(  # type: ignore[call-overload]
            model=model,
            messages=full_messages,
            tools=tools,
            tool_choice="auto",
            max_tokens=max_tokens,
        )
        choice = first_choice(response, "openai")
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
