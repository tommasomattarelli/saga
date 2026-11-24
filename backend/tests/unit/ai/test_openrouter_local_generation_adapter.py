from __future__ import annotations

import json
from typing import Literal, cast
from uuid import UUID

import httpx
import openai
import pytest
from pydantic import BaseModel, ConfigDict, JsonValue

from app.ai.generation_contracts import (
    FormatMode,
    GenerationRequest,
    OutputLimit,
    RawGenerationReceipt,
)
from app.ai.providers import base as provider_base
from app.ai.providers.local import LocalProvider, OpenAICompatibleResponseError
from app.ai.providers.usage import UsageMetadata, usage_scope
from app.ai.response_contracts import ResponseContract

WIRE_SCHEMA: dict[str, JsonValue] = {
    "type": "object",
    "properties": {"result": {"type": "string", "minLength": 4}},
    "required": ["result"],
    "additionalProperties": False,
}
TOOL: dict[str, object] = {
    "type": "function",
    "function": {
        "name": "apply",
        "parameters": {
            "type": "object",
            "properties": {"value": {"type": "string", "minLength": 2}},
            "required": ["value"],
            "additionalProperties": False,
        },
    },
}


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    result: str


CONTRACT = ResponseContract("adapter-payload", "v1", Payload)


def _request(
    *,
    provider: Literal["local", "openrouter"] = "openrouter",
    mode: FormatMode = FormatMode.STRICT_NATIVE,
    tools: list[dict[str, object]] | None = None,
    messages: list[dict[str, object]] | None = None,
    output_limit: OutputLimit | None = None,
    wire_schema: dict[str, JsonValue] | None = WIRE_SCHEMA,
    effective_schema: dict[str, JsonValue] | None = None,
) -> GenerationRequest:
    return GenerationRequest.create(
        "Use the requested generation contract.",
        [{"role": "user", "content": "Return the result."}] if messages is None else messages,
        contract=CONTRACT,
        provider=provider,
        model="fixture-model",
        destination_fingerprint="fixture-destination",
        role="adapter-test",
        logical_result_id="adapter-result",
        output_limit=output_limit or OutputLimit(60000, 37, "verified endpoint metadata"),
        tool_declarations=tools,
        wire_schema=wire_schema,
        effective_schema=effective_schema,
        format_mode=mode,
        session_affinity="campaign-1",
    )


def _completion(
    *,
    content: str | None = '{"result":"ok"}',
    finish: str = "stop",
    calls: list[dict[str, object]] | None = None,
    refusal: str | None = None,
) -> dict[str, object]:
    return {
        "id": "response-1",
        "object": "chat.completion",
        "created": 1,
        "model": "fixture-returned-model",
        "choices": [
            {
                "index": 0,
                "finish_reason": finish,
                "message": {
                    "role": "assistant",
                    "content": content,
                    "tool_calls": calls,
                    "refusal": refusal,
                },
            }
        ],
        "usage": {
            "prompt_tokens": 3,
            "completion_tokens": 2,
            "total_tokens": 5,
            "cost": 0.125,
            "currency": "USD",
        },
        "future_field": {"parts": [2, 1]},
    }


async def _send(
    provider: LocalProvider,
    generation: GenerationRequest,
    response: dict[str, object],
    requests: list[httpx.Request] | None = None,
) -> tuple[RawGenerationReceipt, dict[str, object], list[httpx.Request]]:
    seen = [] if requests is None else requests

    async def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=response)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        provider.client = openai.AsyncOpenAI(
            api_key="fixture-key",
            base_url="https://openrouter.ai/api/v1",
            http_client=http,
        )
        receipt = await provider.send(generation)
    return receipt, json.loads(seen[0].content), seen


@pytest.mark.asyncio
async def test_native_schema_usage_and_raw_candidate_are_lossless() -> None:
    effective = CONTRACT.schema
    effective["properties"] = {"result": {"type": "string", "minLength": 4}}
    generation = _request(effective_schema=effective)
    with usage_scope(role="memory_summary") as collector:
        receipt, body, _ = await _send(
            LocalProvider(provider_kind="openrouter"), generation, _completion()
        )

    assert body["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": generation.contract.name,
            "strict": True,
            "schema": WIRE_SCHEMA,
        },
    }
    assert body["provider"] == {"require_parameters": True}
    assert body["max_tokens"] == 37
    assert "max_completion_tokens" not in body
    assert receipt.usage == UsageMetadata(
        response_id="response-1",
        model="fixture-returned-model",
        input_tokens=3,
        output_tokens=2,
        total_tokens=5,
        cost=0.125,
        currency="USD",
        role="memory_summary",
    )
    assert collector.items == [receipt.usage]
    raw = receipt.raw_candidate or ""
    assert raw.index('"choices"') < raw.index('"usage"') < raw.index('"future_field"')
    assert json.loads(raw)["future_field"] == {"parts": [2, 1]}


@pytest.mark.asyncio
async def test_json_mode_and_prompt_only_have_distinct_wire_bodies() -> None:
    json_request = _request(mode=FormatMode.JSON_MODE)
    _, json_body, _ = await _send(
        LocalProvider(provider_kind="openrouter"), json_request, _completion()
    )
    prompt_request = _request(
        mode=FormatMode.PROMPT_ONLY,
        output_limit=OutputLimit(configured_ceiling=60000),
        effective_schema={
            "type": "object",
            "properties": {"result": {"type": "string", "minLength": 2}},
            "required": ["result"],
            "additionalProperties": False,
        },
    )
    _, prompt_body, _ = await _send(
        LocalProvider(provider_kind="openrouter"), prompt_request, _completion()
    )

    assert json_body["response_format"] == {"type": "json_object"}
    assert json_body["provider"] == {"require_parameters": True}
    assert json_body["max_tokens"] == 37
    assert "response_format" not in prompt_body and "provider" not in prompt_body
    assert prompt_body["max_tokens"] == 60000
    prompt_messages = cast(list[dict[str, object]], prompt_body["messages"])
    system = cast(str, prompt_messages[0]["content"])
    canonical = json.dumps(prompt_request.canonical_schema, sort_keys=True, separators=(",", ":"))
    wire = json.dumps(prompt_request.wire_schema, sort_keys=True, separators=(",", ":"))
    assert prompt_request.canonical_schema != prompt_request.wire_schema
    assert canonical in system
    assert wire not in system


@pytest.mark.parametrize(
    ("content", "finish", "calls", "arguments"),
    [
        ("Text only.", "stop", None, None),
        (
            None,
            "tool_calls",
            [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "apply", "arguments": "{bad json"},
                }
            ],
            "{bad json",
        ),
        (
            "Mixed text.",
            "tool_calls",
            [
                {
                    "id": "c2",
                    "type": "function",
                    "function": {"name": "apply", "arguments": '{"value":"x"}'},
                }
            ],
            '{"value":"x"}',
        ),
    ],
)
@pytest.mark.parametrize("mode", [FormatMode.STRICT_NATIVE, FormatMode.PROMPT_ONLY])
@pytest.mark.asyncio
async def test_native_tools_preserve_text_tool_only_and_mixed_receipts(
    content: str | None,
    finish: str,
    calls: list[dict[str, object]] | None,
    arguments: str | None,
    mode: FormatMode,
) -> None:
    messages: list[dict[str, object]] = [
        {
            "role": "assistant",
            "content": None,
            "text_thought_signature": b"signature",
            "tool_call_signatures": {"c1": b"call-signature"},
            "custom_extension": {"order": [2, 1]},
        }
    ]
    generation = _request(mode=mode, tools=[TOOL], messages=messages)
    receipt, body, _ = await _send(
        LocalProvider(provider_kind="openrouter"),
        generation,
        _completion(content=content, finish=finish, calls=calls),
    )

    assert body["tools"] == [TOOL] and body["tool_choice"] == "auto"
    assert body["provider"] == {"require_parameters": True}
    if mode is FormatMode.STRICT_NATIVE:
        response_format = cast(dict[str, object], body["response_format"])
        json_schema = cast(dict[str, object], response_format["json_schema"])
        assert json_schema["schema"] == WIRE_SCHEMA
    else:
        assert "response_format" not in body
    assert body["max_tokens"] == 37
    wire_messages = cast(list[dict[str, object]], body["messages"])
    assert wire_messages[1] == {
        "role": "assistant",
        "content": None,
        "custom_extension": {"order": [2, 1]},
    }
    assert receipt.text == content
    assert len(receipt.tool_calls) == len(calls or [])
    if arguments is not None:
        assert receipt.tool_calls[0].arguments.raw_text_value == arguments


@pytest.mark.asyncio
async def test_empty_absent_refusal_and_truncated_text_are_preserved() -> None:
    empty, _, _ = await _send(
        LocalProvider(provider_kind="openrouter"),
        _request(),
        _completion(content="", finish="content_filter", refusal="blocked"),
    )
    absent_response = _completion(content=None)
    message = cast(
        dict[str, object],
        cast(list[dict[str, object]], absent_response["choices"])[0]["message"],
    )
    del message["content"]
    absent, _, _ = await _send(
        LocalProvider(provider_kind="openrouter"), _request(), absent_response
    )
    truncated, _, requests = await _send(
        LocalProvider(provider_kind="openrouter"),
        _request(),
        _completion(content='{"partial":', finish="length"),
    )

    assert (empty.text, empty.refusal, empty.finish_reason, empty.blocked_reason) == (
        "",
        "blocked",
        "content_filter",
        "content_filter",
    )
    assert absent.text is None
    assert "content" not in json.loads(absent.raw_candidate or "null")["choices"][0]["message"]
    assert (truncated.text, truncated.finish_reason, len(requests)) == (
        '{"partial":',
        "length",
        1,
    )


@pytest.mark.asyncio
async def test_session_affinity_survives_send_on_resolved_copy() -> None:
    from app.ai.session_affinity import campaign_provider, campaign_session

    original = LocalProvider(provider_kind="openrouter")
    requests: list[httpx.Request] = []

    async def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=_completion())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        original.client = openai.AsyncOpenAI(
            api_key="fixture-key", base_url="https://openrouter.ai/api/v1", http_client=http
        )
        with campaign_session(UUID("12345678-1234-5678-1234-567812345678")):
            resolved = cast(LocalProvider, campaign_provider(original))
        await resolved.send(_request())

    assert requests[0].headers["x-session-id"] == "12345678-1234-5678-1234-567812345678"
    assert "x-session-id" not in original.client.default_headers


@pytest.mark.asyncio
async def test_status_errors_propagate_after_one_http_attempt() -> None:
    requests: list[httpx.Request] = []

    async def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(503, json={"error": {"message": "temporary"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        provider = LocalProvider(provider_kind="openrouter")
        provider.client = openai.AsyncOpenAI(
            api_key="fixture-key", base_url="https://openrouter.ai/api/v1", http_client=http
        )
        with pytest.raises(openai.APIStatusError) as error:
            await provider.send(_request())
    assert len(requests) == 1 and error.value.status_code == 503


@pytest.mark.asyncio
async def test_in_band_error_exposes_code_and_captures_usage_once() -> None:
    response: dict[str, object] = {
        "id": "response-1",
        "object": "chat.completion",
        "created": 1,
        "model": "fixture-returned-model",
        "choices": [],
        "usage": {"prompt_tokens": 3},
        "error": {"code": 429, "message": "Rate limit exceeded: free-models-per-day"},
    }
    with (
        usage_scope(role="memory_summary") as collector,
        pytest.raises(OpenAICompatibleResponseError) as error,
    ):
        await _send(LocalProvider(provider_kind="openrouter"), _request(), response)
    assert error.value.code == 429
    assert len(collector.items) == 1 and collector.items[0].input_tokens == 3


@pytest.mark.asyncio
async def test_factory_selects_provider_kind_by_name_not_endpoint_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(provider_base, "_providers", {})
    router = provider_base.get_provider("openrouter", api_key="fixture-key")
    local = provider_base.get_provider(
        "local", api_key="fixture-key", base_url="https://openrouter.ai/api/v1"
    )
    assert isinstance(router, LocalProvider) and router.provider_kind == "openrouter"
    assert isinstance(local, LocalProvider) and local.provider_kind == "local"
    _, body, _ = await _send(local, _request(provider="local"), _completion())
    assert "provider" not in body
