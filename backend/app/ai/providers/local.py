"""Local / OpenRouter provider — OpenAI-compatible API."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Mapping
from typing import Literal

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
from app.exceptions import AIProviderError

logger = structlog.get_logger()


class OpenAICompatibleResponseError(AIProviderError):
    def __init__(
        self,
        provider: str,
        *,
        code: str | int | None,
        status: str | None,
        error_type: str | None,
    ) -> None:
        self.code = code
        self.status = status
        self.error_type = error_type
        super().__init__(provider, "the provider returned an error without a completion")


def _error_field(error: object, name: str) -> object | None:
    if isinstance(error, Mapping):
        return error.get(name)
    return getattr(error, name, None)


class LocalProvider(AIProvider):
    """Any OpenAI-compatible endpoint: local models (Ollama, LM Studio) or OpenRouter."""

    def __init__(
        self,
        base_url: str = "http://localhost:8080/v1",
        api_key: str | None = None,
        *,
        provider_kind: Literal["local", "openrouter"] = "local",
    ) -> None:
        self.provider_kind = provider_kind
        self.client = openai.AsyncOpenAI(
            base_url=base_url,
            api_key=api_key or "local",  # Many local servers accept any non-empty key
        )

    async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
        if request.provider != self.provider_kind:
            raise ValueError("The generation request provider does not match this adapter.")

        system_prompt = request.system_prompt
        if request.format_mode is FormatMode.PROMPT_ONLY:
            canonical_schema = json.dumps(
                request.canonical_schema,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            system_prompt += f"\n\nReturn a JSON value matching this schema:\n{canonical_schema}"

        kwargs: dict[str, object] = {
            "model": request.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                *strip_provider_metadata(request.messages),
            ],
            "max_tokens": request.output_limit.effective,
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

        tools = request.tool_declarations
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        provider_enforced = request.format_mode is not FormatMode.PROMPT_ONLY or bool(tools)
        if self.provider_kind == "openrouter" and provider_enforced:
            kwargs["extra_body"] = {"provider": {"require_parameters": True}}

        raw_response = await (
            self.client.with_options(max_retries=0).chat.completions.with_raw_response.create(
                **kwargs
            )  # type: ignore[call-overload]
        )
        response = raw_response.parse()
        capture_usage(response, model=request.model)
        usage = extract_usage_metadata(response, model=request.model)
        if not response.choices:
            error = getattr(response, "error", None)
            if error is not None:
                code = _error_field(error, "code")
                status = _error_field(error, "status")
                error_type = _error_field(error, "type")
                raise OpenAICompatibleResponseError(
                    self.provider_kind,
                    code=code
                    if isinstance(code, (str, int)) and not isinstance(code, bool)
                    else None,
                    status=status if isinstance(status, str) else None,
                    error_type=error_type if isinstance(error_type, str) else None,
                )
            # OpenRouter reports an upstream failure as HTTP 200 with no choices (#50);
            # that is a provider failure, never an empty candidate to validate.
            first_choice(response, self.provider_kind)
        choice = response.choices[0]
        message = choice.message
        calls = tuple(
            GenerationToolReceipt(
                call_id=call.id,
                name=call.function.name,
                arguments=RawToolArguments.raw_text(call.function.arguments),
            )
            for call in (message.tool_calls or [])
        )

        return RawGenerationReceipt(
            text=message.content,
            tool_calls=calls,
            finish_reason=choice.finish_reason,
            refusal=message.refusal,
            blocked_reason="content_filter" if choice.finish_reason == "content_filter" else None,
            response_id=response.id,
            model_id=response.model,
            usage=usage,
            raw_candidate=raw_response.http_response.text,
        )

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str = "local",
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
        capture_usage(response, model=model)
        choice = first_choice(response, "local")
        if choice.finish_reason == "content_filter":
            raise ContentPolicyError("local", "Response blocked by content filter")
        return choice.message.content or ""

    async def stream(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str = "local",
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
        capture_usage(response, model=model)
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
