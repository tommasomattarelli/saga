from __future__ import annotations

import json
from typing import cast

import httpx
import pytest
from google.genai.errors import APIError

from app.ai.generation_contracts import (
    FormatMode,
    GenerationRequest,
    OutputLimit,
    RawGenerationReceipt,
)
from app.ai.response_contracts import ResponseContract
from tests.unit.ai._google_generation_test_support import (
    Reply,
    body_with_parts,
    make_provider,
    make_request,
    make_tool_request,
    response_body,
)


@pytest.mark.parametrize(
    ("mode", "expected_mime", "expects_schema"),
    [
        (FormatMode.STRICT_NATIVE, "application/json", True),
        (FormatMode.JSON_MODE, "application/json", False),
        (FormatMode.PROMPT_ONLY, None, False),
    ],
)
async def test_send_serializes_mode_and_preserves_google_receipt(
    mode: FormatMode, expected_mime: str | None, expects_schema: bool
) -> None:
    requests: list[httpx.Request] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=response_body())

    provider, client = make_provider(httpx.MockTransport(respond))
    try:
        receipt = await provider.send(make_request(mode))
    finally:
        await client.aclose()

    assert isinstance(receipt, RawGenerationReceipt)
    assert receipt.text == '{"answer":"4"}'
    assert receipt.finish_reason == "STOP"
    assert receipt.response_id == "response-1"
    assert receipt.model_id == "gemini-test-v2"
    assert receipt.usage is not None
    assert receipt.usage.input_tokens == 7
    assert receipt.usage.output_tokens == 3
    assert receipt.usage.reasoning_output_tokens == 2
    assert len(requests) == 1
    body = json.loads(requests[0].content)
    config = body["generationConfig"]
    assert config["maxOutputTokens"] == 1200
    assert config.get("responseMimeType") == expected_mime
    assert ("responseJsonSchema" in config) is expects_schema
    assert "responseSchema" not in config
    if expects_schema:
        assert config["responseJsonSchema"] == make_request(mode).wire_schema
    if mode is FormatMode.PROMPT_ONLY:
        expected_schema = json.dumps(make_request(mode).canonical_schema, separators=(",", ":"))
        assert expected_schema in body["systemInstruction"]["parts"][0]["text"]


async def test_send_is_one_attempt_and_does_not_use_preview_api() -> None:
    requests: list[httpx.Request] = []

    async def fail(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(503, json={"error": {"status": "UNAVAILABLE"}})

    provider, client = make_provider(httpx.MockTransport(fail))
    try:
        with pytest.raises(APIError):
            await provider.send(make_request(FormatMode.STRICT_NATIVE))
    finally:
        await client.aclose()

    assert len(requests) == 1
    assert requests[0].url.path.endswith(":generateContent")
    assert "interactions" not in requests[0].url.path


async def test_send_uses_configured_ceiling_when_model_limit_is_unknown() -> None:
    requests: list[httpx.Request] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=response_body())

    provider, client = make_provider(httpx.MockTransport(respond))
    request = GenerationRequest.create(
        "Answer.",
        [{"role": "user", "content": "Question"}],
        contract=ResponseContract("reply", "v1", Reply),
        provider="google",
        model="gemini-test",
        destination_fingerprint="google:test",
        role="test",
        logical_result_id="result-1",
        output_limit=OutputLimit(60000),
        format_mode=FormatMode.JSON_MODE,
    )
    try:
        await provider.send(request)
    finally:
        await client.aclose()

    assert json.loads(requests[0].content)["generationConfig"]["maxOutputTokens"] == 60000


async def test_send_encodes_native_tools_and_retains_ordered_tool_receipts() -> None:
    calls: list[httpx.Request] = []
    signature = "AQI="

    async def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        body = body_with_parts(
            [
                {"text": "before"},
                {"executableCode": {"language": "PYTHON", "code": "print(1)"}},
                {"futurePart": {"payload": [1, None, False]}},
                {
                    "functionCall": {
                        "id": "google-call-7",
                        "name": "roll",
                        "args": {"count": 2, "extra": [None, True]},
                    },
                    "thoughtSignature": signature,
                },
                {"text": "after"},
            ]
        )
        candidate = cast(dict[str, object], cast(list[object], body["candidates"])[0])
        candidate["futureCandidateField"] = {"preserved": True}
        return httpx.Response(200, json=body)

    provider, client = make_provider(httpx.MockTransport(respond))
    try:
        receipt = await provider.send(make_tool_request())
    finally:
        await client.aclose()

    assert len(calls) == 1
    sent = json.loads(calls[0].content)
    declaration = sent["tools"][0]["functionDeclarations"][0]
    assert declaration["parameters_json_schema"]["additionalProperties"] is False
    assert sent["generationConfig"]["maxOutputTokens"] == 1200
    assert receipt.text == "beforeafter"
    assert len(receipt.tool_calls) == 1
    call = receipt.tool_calls[0]
    assert call.call_id == "google-call-7"
    assert call.name == "roll"
    assert call.arguments.structured_value == {"count": 2, "extra": [None, True]}
    assert call.signature == b"\x01\x02"
    candidate = json.loads(receipt.raw_candidate or "null")["candidate"]
    assert [
        next(
            key
            for key in ("text", "executableCode", "functionCall", "futurePart")
            if part.get(key) is not None
        )
        for part in candidate["content"]["parts"]
    ] == ["text", "executableCode", "futurePart", "functionCall", "text"]
    assert candidate["content"]["parts"][1]["executableCode"]["code"] == "print(1)"
    assert candidate["content"]["parts"][2]["futurePart"]["payload"] == [1, None, False]
    assert candidate["content"]["parts"][3]["thoughtSignature"] == signature
    assert candidate["futureCandidateField"] == {"preserved": True}


@pytest.mark.asyncio
async def test_send_serializes_native_schema_and_tools_together() -> None:
    requests: list[httpx.Request] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=response_body())

    provider, client = make_provider(httpx.MockTransport(respond))
    generation = make_tool_request()
    try:
        await provider.send(generation)
    finally:
        await client.aclose()

    assert len(requests) == 1
    body = json.loads(requests[0].content)
    config = body["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert config["responseJsonSchema"] == generation.wire_schema
    assert body["tools"][0]["functionDeclarations"][0]["name"] == "roll"
