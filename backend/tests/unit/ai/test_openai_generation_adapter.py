import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal, cast

import httpx
import pytest
from openai import APIStatusError, AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from app.ai.generation_contracts import (
    FormatMode,
    GenerationRequest,
    GenerationToolReceipt,
    OutputLimit,
    RawToolArguments,
)
from app.ai.providers.openai import OpenAIProvider
from app.ai.providers.usage import UsageMetadata, usage_scope
from app.ai.response_contracts import ResponseContract

_RAW_KEY = "sk-offline-test"
_BASE_URL = "https://api.openai.test/v1"
_TOOLS: list[dict[str, object]] = [
    {
        "type": "function",
        "function": {
            "name": "advance",
            "description": "Advance the scene.",
            "parameters": {
                "type": "object",
                "properties": {"steps": {"type": "integer"}},
                "required": ["steps"],
                "additionalProperties": False,
            },
            "strict": True,
        },
    }
]


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    levels: list[Literal["basic", "advanced"]] = Field(min_length=1, max_length=2)


def make_request(
    mode: FormatMode = FormatMode.STRICT_NATIVE,
    *,
    tools: list[dict[str, object]] | None = None,
) -> GenerationRequest:
    contract = ResponseContract("test_payload", "v1", Payload)
    effective = contract.schema
    properties = cast(dict[str, JsonValue], effective["properties"])
    levels = cast(dict[str, JsonValue], properties["levels"])
    levels["maxItems"] = 1
    items = cast(dict[str, JsonValue], levels["items"])
    items["enum"] = ["basic"]
    return GenerationRequest.create(
        "Return a complete payload.",
        [{"role": "user", "content": "Start."}],
        contract=contract,
        provider="openai",
        model="gpt-test",
        destination_fingerprint="openai-test",
        role="test",
        logical_result_id="result-test",
        output_limit=OutputLimit(
            configured_ceiling=60000,
            known_lower_limit=8192,
            limit_source="explicit test profile",
        ),
        format_mode=mode,
        tool_declarations=tools,
        effective_schema=effective,
    )


def completion(
    *,
    content: str | None = "{}",
    include_content: bool = True,
    finish_reason: str = "stop",
    refusal: str | None = None,
    tool_calls: list[dict[str, object]] | None = None,
    include_usage: bool = True,
) -> dict[str, object]:
    message: dict[str, object] = {"role": "assistant", "refusal": refusal}
    if include_content:
        message["content"] = content
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    choice = {
        "index": 0,
        "finish_reason": finish_reason,
        "logprobs": None,
        "message": message,
    }
    result: dict[str, object] = {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1760000000,
        "model": "gpt-test",
        "choices": [choice],
        "provider_extra": {"parts": ["first", "second"]},
    }
    if include_usage:
        result["usage"] = {
            "prompt_tokens": 11,
            "completion_tokens": 7,
            "total_tokens": 18,
            "prompt_tokens_details": {"cached_tokens": 3},
            "completion_tokens_details": {"reasoning_tokens": 2},
        }
    return result


@asynccontextmanager
async def provider_with_response(
    payload: dict[str, object], *, status_code: int = 200
) -> AsyncIterator[tuple[OpenAIProvider, list[httpx.Request], str]]:
    raw_body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    requests: list[httpx.Request] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            status_code,
            headers={"content-type": "application/json"},
            content=raw_body,
            request=request,
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    client = AsyncOpenAI(
        api_key=_RAW_KEY,
        base_url=_BASE_URL,
        http_client=http_client,
    )
    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider.client = client
    try:
        yield provider, requests, raw_body
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mode", "format_type"),
    [
        (FormatMode.STRICT_NATIVE, "json_schema"),
        (FormatMode.JSON_MODE, "json_object"),
        (FormatMode.PROMPT_ONLY, None),
    ],
)
async def test_send_serializes_each_explicit_format_without_fallback(
    mode: FormatMode, format_type: str | None
) -> None:
    request = make_request(mode, tools=_TOOLS if mode is FormatMode.STRICT_NATIVE else None)
    async with provider_with_response(completion()) as (provider, calls, _):
        await provider.send(request)

    body = json.loads(calls[0].content)
    assert body["model"] == "gpt-test"
    assert body["max_completion_tokens"] == 8192
    assert "max_tokens" not in body
    assert body["messages"][0]["role"] == "system"
    assert body["messages"][1]["content"] == "Start."
    if format_type == "json_schema":
        assert body["response_format"]["type"] == "json_schema"
        schema_format = body["response_format"]["json_schema"]
        assert schema_format == {
            "name": "test_payload",
            "strict": True,
            "schema": request.wire_schema,
        }
        properties = cast(dict[str, JsonValue], request.canonical_schema["properties"])
        effective_levels = cast(dict[str, JsonValue], properties["levels"])
        items = cast(dict[str, JsonValue], effective_levels["items"])
        assert effective_levels["maxItems"] == 1
        assert items["enum"] == ["basic"]
        assert body["tools"] == _TOOLS
        assert body["tool_choice"] == "auto"
        assert "response_format" in body
        assert "schema" not in body["messages"][0]["content"]
    elif format_type == "json_object":
        assert body["response_format"] == {"type": "json_object"}
        assert "tools" not in body
    else:
        assert "response_format" not in body
        canonical = json.dumps(
            request.canonical_schema,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        assert canonical in body["messages"][0]["content"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (completion(include_content=False, tool_calls=[]), None),
        (completion(content=None, tool_calls=[]), None),
        (completion(content="", tool_calls=[]), ""),
    ],
)
async def test_send_preserves_absent_nullable_and_empty_text(
    payload: dict[str, object], expected: str | None
) -> None:
    async with provider_with_response(payload) as (provider, _, raw_body):
        receipt = await provider.send(make_request(tools=_TOOLS))

    assert receipt.text == expected
    assert receipt.raw_candidate == raw_body


@pytest.mark.asyncio
async def test_send_preserves_order_and_raw_tool_arguments_without_json_repair() -> None:
    payload = completion(
        content=None,
        finish_reason="tool_calls",
        tool_calls=[
            {
                "id": "call-first",
                "type": "function",
                "function": {"name": "first", "arguments": "{bad json"},
            },
            {
                "id": "call-second",
                "type": "function",
                "function": {"name": "second", "arguments": '{"steps":2}'},
            },
        ],
    )
    async with provider_with_response(payload) as (provider, _, raw_body):
        receipt = await provider.send(make_request(tools=_TOOLS))

    assert receipt.text is None
    assert receipt.finish_reason == "tool_calls"
    assert receipt.tool_calls == (
        GenerationToolReceipt("call-first", "first", RawToolArguments.raw_text("{bad json")),
        GenerationToolReceipt("call-second", "second", RawToolArguments.raw_text('{"steps":2}')),
    )
    assert receipt.raw_candidate == raw_body
    assert "provider_extra" in receipt.raw_candidate


@pytest.mark.asyncio
async def test_send_preserves_mixed_narrative_and_native_tool_calls() -> None:
    payload = completion(
        content="The gate opens.",
        finish_reason="tool_calls",
        tool_calls=[
            {
                "id": "call-advance",
                "type": "function",
                "function": {"name": "advance", "arguments": '{"steps":1}'},
            }
        ],
    )
    async with provider_with_response(payload) as (provider, calls, _):
        receipt = await provider.send(make_request(tools=_TOOLS))

    body = json.loads(calls[0].content)
    assert receipt.text == "The gate opens."
    assert len(receipt.tool_calls) == 1
    assert receipt.tool_calls[0].call_id == "call-advance"
    assert body["response_format"]["type"] == "json_schema"
    assert body["tools"] == _TOOLS


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("finish_reason", "refusal", "blocked_reason"),
    [
        ("stop", "I cannot help with that request.", None),
        ("content_filter", None, "content_filter"),
        ("length", None, None),
    ],
)
async def test_send_preserves_refusal_finish_reason_usage_and_response_identity(
    finish_reason: str, refusal: str | None, blocked_reason: str | None
) -> None:
    payload = completion(
        content="partial candidate",
        finish_reason=finish_reason,
        refusal=refusal,
    )
    async with provider_with_response(payload) as (provider, _, raw_body):
        receipt = await provider.send(make_request())

    assert receipt.text == "partial candidate"
    assert receipt.finish_reason == finish_reason
    assert receipt.refusal == refusal
    assert receipt.blocked_reason == blocked_reason
    assert receipt.response_id == "chatcmpl-test"
    assert receipt.model_id == "gpt-test"
    assert receipt.raw_candidate == raw_body
    assert receipt.usage == UsageMetadata(
        response_id="chatcmpl-test",
        model="gpt-test",
        input_tokens=11,
        output_tokens=7,
        total_tokens=18,
        cached_input_tokens=3,
        reasoning_output_tokens=2,
    )


@pytest.mark.asyncio
async def test_send_usage_stays_correlated_inside_existing_usage_scope() -> None:
    async with provider_with_response(completion()) as (provider, _, _):
        with usage_scope(role="npc", step=4, npc_id="npc-1") as collector:
            receipt = await provider.send(make_request())

    assert receipt.usage is not None
    assert receipt.usage.role == "npc"
    assert collector.items == [receipt.usage]


@pytest.mark.asyncio
async def test_send_has_no_usage_metadata_when_sdk_omits_usage() -> None:
    async with provider_with_response(completion(include_usage=False)) as (provider, _, _):
        receipt = await provider.send(make_request())

    assert receipt.usage == UsageMetadata(
        response_id="chatcmpl-test",
        model="gpt-test",
    )


@pytest.mark.asyncio
async def test_send_keeps_one_http_attempt_for_sdk_server_errors() -> None:
    error: dict[str, object] = {"error": {"message": "temporary", "type": "server_error"}}
    async with provider_with_response(error, status_code=503) as (provider, calls, _):
        with pytest.raises(APIStatusError) as raised:
            await provider.send(make_request())

    assert raised.value.status_code == 503
    assert len(calls) == 1
