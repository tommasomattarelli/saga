from __future__ import annotations

import json

import httpx
import pytest

from app.ai.generation_contracts import GenerationRequest, OutputLimit
from app.ai.providers.schemas import TEXT_SIGNATURE_KEY, TOOL_CALL_SIGNATURES_KEY
from app.ai.response_contracts import ResponseContract
from tests.unit.ai._google_generation_test_support import Reply, make_provider, response_body


async def test_send_restores_signature_sidechannels_without_leaking_synthetic_ids() -> None:
    requests: list[httpx.Request] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=response_body())

    provider, client = make_provider(httpx.MockTransport(respond))
    request = GenerationRequest.create(
        "Continue.",
        [
            {
                "role": "assistant",
                "content": "Thinking",
                TEXT_SIGNATURE_KEY: b"\x03\x04",
                "tool_calls": [
                    {
                        "id": "saga-call-0123456789abcdef0123456789abcdef",
                        "function": {"name": "roll", "arguments": {"count": 1}},
                    }
                ],
                TOOL_CALL_SIGNATURES_KEY: {
                    "saga-call-0123456789abcdef0123456789abcdef": b"\x01\x02"
                },
            }
        ],
        contract=ResponseContract("reply", "v1", Reply),
        provider="google",
        model="gemini-test",
        destination_fingerprint="google:test",
        role="test",
        logical_result_id="result-1",
        output_limit=OutputLimit(2000),
    )
    try:
        await provider.send(request)
    finally:
        await client.aclose()

    parts = json.loads(requests[0].content)["contents"][0]["parts"]
    assert parts[0]["thoughtSignature"] == "AwQ="
    assert "id" not in parts[1]["functionCall"]
    assert parts[1]["thoughtSignature"] == "AQI="


async def test_send_rejects_malformed_native_arguments_before_io() -> None:
    requests: list[httpx.Request] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=response_body())

    provider, client = make_provider(httpx.MockTransport(respond))
    request = GenerationRequest.create(
        "Continue.",
        [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "function": {"name": "roll", "arguments": '{"count":'},
                    }
                ],
            }
        ],
        contract=ResponseContract("reply", "v1", Reply),
        provider="google",
        model="gemini-test",
        destination_fingerprint="google:test",
        role="test",
        logical_result_id="result-1",
        output_limit=OutputLimit(2000),
    )
    try:
        with pytest.raises(ValueError):
            await provider.send(request)
    finally:
        await client.aclose()

    assert requests == []


async def test_send_rejects_valid_non_object_tool_arguments_before_io() -> None:
    requests: list[httpx.Request] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=response_body())

    provider, client = make_provider(httpx.MockTransport(respond))
    request = GenerationRequest.create(
        "Continue.",
        [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "function": {"name": "roll", "arguments": "[1,2]"},
                    }
                ],
            }
        ],
        contract=ResponseContract("reply", "v1", Reply),
        provider="google",
        model="gemini-test",
        destination_fingerprint="google:test",
        role="test",
        logical_result_id="result-1",
        output_limit=OutputLimit(2000),
    )
    try:
        with pytest.raises(ValueError, match="JSON object"):
            await provider.send(request)
    finally:
        await client.aclose()

    assert requests == []


@pytest.mark.parametrize(
    ("messages", "tools", "error"),
    [
        ([{"role": "system", "content": "not a system instruction"}], [], "role"),
        ([{"role": "tool", "content": "result"}], [], "tool result name"),
        ([{"role": "tool", "name": 12, "content": "result"}], [], "tool result name"),
        ([{"role": "tool", "name": "roll", "tool_call_id": 12}], [], "ID"),
        (
            [
                {
                    "role": "assistant",
                    "tool_calls": [{"id": "call-1", "function": {"name": "roll"}}],
                }
            ],
            [],
            "arguments",
        ),
        (
            [
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": 12,
                            "function": {"name": "roll", "arguments": {}},
                        }
                    ],
                }
            ],
            [],
            "ID",
        ),
        (
            [{"role": "user", "content": "Question"}],
            [{"type": "function", "function": {"name": "roll", "description": 12}}],
            "description",
        ),
        (
            [{"role": "user", "content": "Question"}],
            [{"type": "function", "function": {"name": ""}}],
            "function declaration name",
        ),
        (
            [{"role": "user", "content": "Question"}],
            [{"type": "function", "function": {"name": "1roll"}}],
            "function declaration name",
        ),
        (
            [{"role": "user", "content": "Question"}],
            [{"type": "function", "function": {"name": "roll/name"}}],
            "function declaration name",
        ),
        (
            [{"role": "user", "content": "Question"}],
            [{"type": "function", "function": {"name": f"r{'x' * 64}"}}],
            "function declaration name",
        ),
    ],
)
async def test_send_rejects_malformed_inputs_before_io(
    messages: list[dict[str, object]], tools: list[dict[str, object]], error: str
) -> None:
    requests: list[httpx.Request] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=response_body())

    provider, client = make_provider(httpx.MockTransport(respond))
    request = GenerationRequest.create(
        "Continue.",
        messages,
        contract=ResponseContract("reply", "v1", Reply),
        provider="google",
        model="gemini-test",
        destination_fingerprint="google:test",
        role="test",
        logical_result_id="result-1",
        output_limit=OutputLimit(2000),
        tool_declarations=tools,
    )
    try:
        with pytest.raises(ValueError, match=error):
            await provider.send(request)
    finally:
        await client.aclose()

    assert requests == []


async def test_send_accepts_maximum_length_google_function_name() -> None:
    requests: list[httpx.Request] = []
    function_name = f"r{'x' * 63}"

    async def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=response_body())

    provider, client = make_provider(httpx.MockTransport(respond))
    request = GenerationRequest.create(
        "Question",
        [{"role": "user", "content": "Question"}],
        contract=ResponseContract("reply", "v1", Reply),
        provider="google",
        model="gemini-test",
        destination_fingerprint="google:test",
        role="test",
        logical_result_id="result-1",
        output_limit=OutputLimit(2000),
        tool_declarations=[{"type": "function", "function": {"name": function_name}}],
    )
    try:
        await provider.send(request)
    finally:
        await client.aclose()

    declaration = json.loads(requests[0].content)["tools"][0]["functionDeclarations"][0]
    assert declaration["name"] == function_name


async def test_send_preserves_real_provider_ids_and_present_empty_arguments() -> None:
    requests: list[httpx.Request] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=response_body())

    provider, client = make_provider(httpx.MockTransport(respond))
    request = GenerationRequest.create(
        "Continue.",
        [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "saga-call-provider-issued",
                        "function": {"name": "roll", "arguments": {}},
                    }
                ],
            }
        ],
        contract=ResponseContract("reply", "v1", Reply),
        provider="google",
        model="gemini-test",
        destination_fingerprint="google:test",
        role="test",
        logical_result_id="result-1",
        output_limit=OutputLimit(2000),
        tool_declarations=[{"type": "function", "function": {"name": "roll"}}],
    )
    try:
        await provider.send(request)
    finally:
        await client.aclose()

    body = json.loads(requests[0].content)
    function_call = body["contents"][0]["parts"][0]["functionCall"]
    assert function_call["id"] == "saga-call-provider-issued"
    assert function_call["args"] == {}
    assert "description" not in body["tools"][0]["functionDeclarations"][0]
