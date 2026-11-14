from __future__ import annotations

import httpx
from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict

from app.ai.generation_contracts import FormatMode, GenerationRequest, OutputLimit
from app.ai.providers.google import GoogleProvider
from app.ai.response_contracts import ResponseContract


class Reply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str


def make_request(mode: FormatMode) -> GenerationRequest:
    return GenerationRequest.create(
        "Answer the question.",
        [{"role": "user", "content": "What is 2+2?"}],
        contract=ResponseContract("reply", "v1", Reply),
        provider="google",
        model="gemini-test",
        destination_fingerprint="google:test",
        role="test",
        logical_result_id="result-1",
        output_limit=OutputLimit(60000, 1200, "model registry"),
        format_mode=mode,
    )


def make_tool_request(mode: FormatMode = FormatMode.STRICT_NATIVE) -> GenerationRequest:
    request = make_request(mode)
    return GenerationRequest.create(
        request.system_prompt,
        request.messages,
        contract=request.contract,
        provider=request.provider,
        model=request.model,
        destination_fingerprint=request.destination_fingerprint,
        role=request.role,
        logical_result_id=request.logical_result_id,
        output_limit=request.output_limit,
        format_mode=mode,
        tool_declarations=[
            {
                "type": "function",
                "function": {
                    "name": "roll",
                    "description": "Roll dice.",
                    "parameters": {
                        "type": "object",
                        "properties": {"count": {"type": "integer"}},
                        "required": ["count"],
                        "additionalProperties": False,
                    },
                },
            }
        ],
    )


def make_provider(
    transport: httpx.MockTransport,
) -> tuple[GoogleProvider, httpx.AsyncClient]:
    http_client = httpx.AsyncClient(
        transport=transport,
        base_url="https://generativelanguage.googleapis.com",
    )
    provider = GoogleProvider.__new__(GoogleProvider)
    provider.client = genai.Client(
        api_key="fake-test-key",
        http_options=types.HttpOptions(httpx_async_client=http_client),
    )
    return provider, http_client


def response_body(*, text: str | None = '{"answer":"4"}') -> dict[str, object]:
    parts = [] if text is None else [{"text": text}]
    return {
        "candidates": [
            {
                "content": {"role": "model", "parts": parts},
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": 7,
            "candidatesTokenCount": 3,
            "totalTokenCount": 10,
            "thoughtsTokenCount": 2,
        },
        "responseId": "response-1",
        "modelVersion": "gemini-test-v2",
    }


def body_with_parts(parts: list[dict[str, object]]) -> dict[str, object]:
    return {
        "candidates": [
            {
                "content": {"role": "model", "parts": parts},
                "finishReason": "STOP",
            }
        ],
        "responseId": "response-2",
        "modelVersion": "gemini-test-v2",
    }
