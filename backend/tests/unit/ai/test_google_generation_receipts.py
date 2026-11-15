from __future__ import annotations

import json
from typing import cast

import httpx
import pytest

from app.ai.generation_contracts import FormatMode
from tests.unit.ai._google_generation_test_support import (
    body_with_parts,
    make_provider,
    make_request,
    make_tool_request,
    response_body,
)


async def test_send_excludes_thought_text_but_retains_full_candidate() -> None:
    async def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=body_with_parts(
                [
                    {"text": "private thought", "thought": True, "thoughtSignature": "AQI="},
                    {"text": "visible", "thought": False, "thoughtSignature": "AwQ="},
                ]
            ),
        )

    provider, client = make_provider(httpx.MockTransport(respond))
    try:
        receipt = await provider.send(make_request(FormatMode.JSON_MODE))
    finally:
        await client.aclose()

    assert receipt.text == "visible"
    assert receipt.text_signature == b"\x03\x04"
    raw = json.loads(receipt.raw_candidate or "null")
    assert raw["candidate"]["content"]["parts"] == [
        {"text": "private thought", "thought": True, "thoughtSignature": "AQI="},
        {"text": "visible", "thought": False, "thoughtSignature": "AwQ="},
    ]


async def test_send_thought_only_has_no_visible_text() -> None:
    async def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=body_with_parts([{"text": "private thought", "thought": True}]),
        )

    provider, client = make_provider(httpx.MockTransport(respond))
    try:
        receipt = await provider.send(make_request(FormatMode.JSON_MODE))
    finally:
        await client.aclose()

    assert receipt.text is None
    assert receipt.text_signature is None


async def test_send_supports_tool_only_receipt_without_invented_call_id() -> None:
    async def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=body_with_parts([{"functionCall": {"name": "roll", "args": {"count": 1}}}]),
        )

    provider, client = make_provider(httpx.MockTransport(respond))
    try:
        receipt = await provider.send(make_tool_request(FormatMode.JSON_MODE))
    finally:
        await client.aclose()

    assert receipt.text is None
    assert receipt.tool_calls[0].call_id is None
    assert receipt.tool_calls[0].arguments.structured_value == {"count": 1}


@pytest.mark.parametrize(
    "raw_body",
    [
        '{"candidates":[{"content":{"parts":[{"text":"a","text":"b"}]}}]}',
        '{"candidates":[{"content":{"parts":[{"functionCall":{"args":{"value":NaN}}}]}}]}',
    ],
)
async def test_send_rejects_ambiguous_or_non_finite_raw_response(raw_body: str) -> None:
    async def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=raw_body)

    provider, client = make_provider(httpx.MockTransport(respond))
    try:
        with pytest.raises(ValueError):
            await provider.send(make_request(FormatMode.JSON_MODE))
    finally:
        await client.aclose()


async def test_send_distinguishes_empty_text_from_absent_text() -> None:
    async def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body_with_parts([{"text": ""}]))

    provider, client = make_provider(httpx.MockTransport(respond))
    try:
        receipt = await provider.send(make_request(FormatMode.JSON_MODE))
    finally:
        await client.aclose()

    assert receipt.text == ""


async def test_send_keeps_absent_text_and_reports_blocked_response_without_candidates() -> None:
    async def blocked(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "candidates": [],
                "promptFeedback": {"blockReason": "SAFETY"},
                "responseId": "blocked-response",
            },
        )

    provider, client = make_provider(httpx.MockTransport(blocked))
    try:
        receipt = await provider.send(make_request(FormatMode.JSON_MODE))
    finally:
        await client.aclose()

    assert receipt.text is None
    assert receipt.blocked_reason == "SAFETY"
    assert receipt.response_id == "blocked-response"
    assert receipt.raw_candidate is None


async def test_send_preserves_present_empty_candidate_distinct_from_absence() -> None:
    async def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"candidates": [{}]})

    provider, client = make_provider(httpx.MockTransport(respond))
    try:
        receipt = await provider.send(make_request(FormatMode.JSON_MODE))
    finally:
        await client.aclose()

    assert receipt.text is None
    assert receipt.tool_calls == ()
    assert receipt.raw_candidate == '{"encoding_version":1,"candidate":{}}'


async def test_send_preserves_falsey_native_receipt_fields() -> None:
    async def respond(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": ""},
                                {
                                    "functionCall": {"id": "", "name": "", "args": {}},
                                    "thoughtSignature": "",
                                },
                            ]
                        },
                        "finishReason": "",
                    }
                ],
                "promptFeedback": {"blockReason": ""},
                "usageMetadata": {
                    "promptTokenCount": 0,
                    "candidatesTokenCount": 0,
                    "totalTokenCount": 0,
                    "cachedContentTokenCount": 0,
                    "thoughtsTokenCount": 0,
                },
                "responseId": "",
                "modelVersion": "",
            },
        )

    provider, client = make_provider(httpx.MockTransport(respond))
    try:
        receipt = await provider.send(make_request(FormatMode.JSON_MODE))
    finally:
        await client.aclose()

    assert receipt.text == ""
    assert receipt.finish_reason == ""
    assert receipt.blocked_reason == ""
    assert receipt.response_id == ""
    assert receipt.model_id == ""
    assert receipt.usage is not None
    assert receipt.usage.input_tokens == 0
    assert receipt.usage.output_tokens == 0
    assert receipt.usage.total_tokens == 0
    assert receipt.usage.cached_input_tokens == 0
    assert receipt.usage.reasoning_output_tokens == 0
    assert receipt.tool_calls[0].call_id == ""
    assert receipt.tool_calls[0].name == ""
    assert receipt.tool_calls[0].arguments.structured_value == {}
    assert receipt.tool_calls[0].signature == b""


@pytest.mark.parametrize(
    ("finish", "blocked"),
    [("MAX_TOKENS", None), ("SAFETY", "SAFETY")],
)
async def test_send_preserves_finish_and_block_reason(finish: str, blocked: str | None) -> None:
    async def respond(_: httpx.Request) -> httpx.Response:
        body = response_body(text=None)
        candidate = cast(dict[str, object], cast(list[object], body["candidates"])[0])
        candidate["finishReason"] = finish
        return httpx.Response(200, json=body)

    provider, client = make_provider(httpx.MockTransport(respond))
    try:
        receipt = await provider.send(make_request(FormatMode.JSON_MODE))
    finally:
        await client.aclose()

    assert receipt.text is None
    assert receipt.finish_reason == finish
    assert receipt.blocked_reason == blocked
