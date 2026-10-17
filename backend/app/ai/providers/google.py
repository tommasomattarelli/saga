"""Google Gemini provider."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator

import structlog
from google import genai
from google.genai import types as genai_types

from app.ai.exceptions import ContentPolicyError
from app.ai.providers.base import AIProvider
from app.ai.providers.schemas import (
    TEXT_SIGNATURE_KEY,
    TOOL_CALL_SIGNATURES_KEY,
    AgentResponse,
    ToolCall,
)
from app.config import settings

logger = structlog.get_logger()

_RETRY_DELAYS = [5, 15, 30]  # seconds between retries on 503


async def _with_retry(coro_fn, *args, **kwargs):
    """Retry a coroutine up to 3 times on 503 errors."""
    last_exc: Exception | None = None
    for attempt, delay in enumerate([0] + _RETRY_DELAYS):
        if delay:
            await asyncio.sleep(delay)
        try:
            return await coro_fn(*args, **kwargs)
        except Exception as e:
            if "503" in str(e) or "UNAVAILABLE" in str(e):
                logger.warning("google_503_retry", attempt=attempt + 1, error=str(e)[:100])
                last_exc = e
            else:
                raise
    raise last_exc


def _to_contents(messages: list[dict]) -> list[dict]:
    import json as _json

    contents = []
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"

        # Already in Google native format (function_response tool results from format_tool_result)
        if msg.get("parts"):
            contents.append({"role": role, "parts": msg["parts"]})

        # OpenAI-format tool result: role=tool
        elif msg["role"] == "tool":
            tool_name = msg.get("name") or msg.get("tool_call_id") or "tool"
            contents.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "function_response": {
                                "name": tool_name,
                                "response": {"result": msg["content"]},
                            }
                        }
                    ],
                }
            )

        # Assistant message with tool calls → model parts with function_call
        elif msg["role"] == "assistant" and msg.get("tool_calls"):
            parts = []
            if msg.get("content"):
                text_part: dict = {"text": msg["content"]}
                text_signature = msg.get(TEXT_SIGNATURE_KEY)
                if text_signature is not None:
                    text_part["thought_signature"] = text_signature
                parts.append(text_part)
            signatures = msg.get(TOOL_CALL_SIGNATURES_KEY) or {}
            for tc in msg["tool_calls"]:
                fn = tc.get("function", {})
                args = fn.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = _json.loads(args)
                    except (ValueError, TypeError):
                        args = {}
                part: dict = {"function_call": {"name": fn.get("name", ""), "args": args}}
                signature = signatures.get(tc.get("id"))
                if signature is not None:
                    part["thought_signature"] = signature
                parts.append(part)
            contents.append({"role": "model", "parts": parts})

        else:
            content = msg.get("content", "")
            if isinstance(content, str) and content:
                contents.append({"role": role, "parts": [{"text": content}]})
            elif isinstance(content, list):
                parts = []
                for block in content:
                    if block.get("type") == "tool_result":
                        parts.append(
                            {
                                "function_response": {
                                    "name": block.get("name", "tool"),
                                    "response": {"result": block.get("content", "")},
                                }
                            }
                        )
                    elif isinstance(block, dict) and "text" in block:
                        parts.append({"text": block["text"]})
                if parts:
                    contents.append({"role": role, "parts": parts})
    return contents


def _call_id(fc: genai_types.FunctionCall) -> str:
    # Google may omit the id; falling back to the name collides across parallel calls
    # and smears one signature onto every same-named one, so mint a unique internal id.
    if getattr(fc, "id", None):
        return str(fc.id)
    return f"{fc.name or 'call'}_{uuid.uuid4().hex}"


def _openai_tool_to_google(tool: dict) -> dict:
    """Convert OpenAI-format function schema to Google function declaration."""
    fn = tool["function"]
    return {
        "name": fn["name"],
        "description": fn["description"],
        "parameters": fn["parameters"],
    }


def _check_safety(response: object) -> None:
    if hasattr(response, "candidates") and response.candidates:
        finish_reason = getattr(response.candidates[0], "finish_reason", None)
        if finish_reason and str(finish_reason) == "SAFETY":
            raise ContentPolicyError("google", "Response blocked by safety filter")


class GoogleProvider(AIProvider):
    """Google Gemini API provider."""

    def __init__(self, api_key: str | None = None) -> None:
        self.client = genai.Client(api_key=api_key or settings.google_ai_api_key)

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str = "gemini-2.5-pro",
        max_tokens: int = 2000,
        json_mode: bool = False,
    ) -> str:
        config: dict = {
            "system_instruction": system_prompt,
            "max_output_tokens": max_tokens,
        }
        if json_mode:
            config["response_mime_type"] = "application/json"
        response = await _with_retry(
            self.client.aio.models.generate_content,
            model=model,
            contents=_to_contents(messages),
            config=config,
        )
        _check_safety(response)
        return response.text or ""

    async def stream(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str = "gemini-2.5-pro",
        max_tokens: int = 2000,
    ) -> AsyncIterator[str]:
        response = await self.client.aio.models.generate_content_stream(
            model=model,
            contents=_to_contents(messages),
            config={
                "system_instruction": system_prompt,
                "max_output_tokens": max_tokens,
            },
        )
        async for chunk in response:
            if chunk.text:
                yield chunk.text

    async def generate_with_tools(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[dict],
        model: str = "gemini-2.5-pro",
        max_tokens: int = 2000,
    ) -> AgentResponse:
        google_tools = [
            genai_types.Tool(function_declarations=[_openai_tool_to_google(t) for t in tools])
        ]
        response = await _with_retry(
            self.client.aio.models.generate_content,
            model=model,
            contents=_to_contents(messages),
            config=genai_types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=max_tokens,
                tools=google_tools,
                automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(
                    disable=True, maximum_remote_calls=None
                ),
            ),
        )
        _check_safety(response)

        text = ""
        text_signature: bytes | None = None
        tool_calls = []
        if response.candidates:
            for part in response.candidates[0].content.parts:
                if hasattr(part, "text") and part.text:
                    text += part.text
                    if text_signature is None:
                        text_signature = getattr(part, "thought_signature", None)
                elif hasattr(part, "function_call") and part.function_call:
                    fc = part.function_call
                    tool_calls.append(
                        ToolCall(
                            id=_call_id(fc),
                            name=fc.name,
                            arguments=dict(fc.args) if fc.args else {},
                            signature=getattr(part, "thought_signature", None),
                        )
                    )
        return AgentResponse(text=text, tool_calls=tool_calls, text_signature=text_signature)
