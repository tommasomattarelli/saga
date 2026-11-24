from __future__ import annotations

import json
import re
import string
from typing import cast

from google import genai
from google.genai import types
from pydantic import JsonValue

from app.ai.generation_contracts import FormatMode, GenerationRequest, RawGenerationReceipt
from app.ai.providers.google_generation_receipt import receipt_from_body
from app.ai.providers.schemas import TEXT_SIGNATURE_KEY, TOOL_CALL_SIGNATURES_KEY
from app.ai.response_contracts import parse_json_document

SYNTHETIC_CALL_ID_PREFIX = "saga-call-"


def _native_call_id(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Google tool call ID must be text.")
    # Internal IDs are prefix + UUID hex; preserve other provider IDs sharing the prefix.
    suffix = value.removeprefix(SYNTHETIC_CALL_ID_PREFIX)
    is_internal_id = (
        suffix != value
        and len(suffix) == 32
        and all(character in string.hexdigits.lower() for character in suffix)
    )
    if not is_internal_id:
        return value
    return None


def _contents(request: GenerationRequest) -> list[dict[str, object]]:
    contents: list[dict[str, object]] = []
    for message in request.messages:
        role = message.get("role")
        if role not in {"user", "assistant", "tool"}:
            raise ValueError("Google generation message has an unsupported role.")
        google_role = "user" if role in {"user", "tool"} else "model"
        existing_parts = message.get("parts")
        if existing_parts is not None:
            if not isinstance(existing_parts, list) or not all(
                isinstance(part, dict) for part in existing_parts
            ):
                raise ValueError("Google-native message parts must be objects.")
            contents.append({"role": google_role, "parts": existing_parts})
            continue

        if role == "tool":
            name = message.get("name")
            call_id = message.get("tool_call_id")
            if not isinstance(name, str) or not name:
                raise ValueError("Google tool result requires a tool result name.")
            response: dict[str, object] = {
                "name": name,
                "response": {"result": message.get("content")},
            }
            native_id = _native_call_id(call_id)
            if native_id is not None:
                response["id"] = native_id
            contents.append({"role": "user", "parts": [{"function_response": response}]})
            continue

        parts: list[dict[str, object]] = []
        text = message.get("content")
        if text is not None:
            if not isinstance(text, str):
                raise ValueError("Google generation message content must be text.")
            text_part: dict[str, object] = {"text": text}
            signature = message.get(TEXT_SIGNATURE_KEY)
            if signature is not None:
                text_part["thought_signature"] = signature
            parts.append(text_part)

        calls = message.get("tool_calls", [])
        if not isinstance(calls, list):
            raise ValueError("Google generation tool calls must be a list.")
        signatures = message.get(TOOL_CALL_SIGNATURES_KEY, {})
        if not isinstance(signatures, dict):
            raise ValueError("Google tool-call signatures must be an object.")
        for call in calls:
            if not isinstance(call, dict) or not isinstance(call.get("function"), dict):
                raise ValueError("Google generation tool call is malformed.")
            call_id = call.get("id")
            function = cast(dict[str, object], call["function"])
            name = function.get("name")
            if not isinstance(name, str) or not name:
                raise ValueError("Google generation tool call requires a name.")
            if "arguments" not in function:
                raise ValueError("Google function-call arguments are required.")
            arguments = function["arguments"]
            if isinstance(arguments, str):
                arguments = parse_json_document(arguments)
            if not isinstance(arguments, dict):
                raise ValueError("Google function-call arguments must be a JSON object.")
            arguments = cast(JsonValue, arguments)
            function_call: dict[str, object] = {
                "name": name,
                "args": arguments,
            }
            native_id = _native_call_id(call_id)
            if native_id is not None:
                function_call["id"] = native_id
            part: dict[str, object] = {"function_call": function_call}
            signature = signatures.get(call_id) if isinstance(call_id, str) else None
            if signature is not None:
                part["thought_signature"] = signature
            parts.append(part)

        if parts:
            contents.append({"role": google_role, "parts": parts})
    return contents


def _tool_declarations(request: GenerationRequest) -> list[types.Tool] | None:
    declarations: list[types.FunctionDeclaration] = []
    for tool in request.tool_declarations:
        function = tool.get("function")
        if not isinstance(function, dict):
            raise ValueError("Google tool declaration requires a function object.")
        name = function.get("name")
        if (
            not isinstance(name, str)
            or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.:-]{0,63}", name) is None
        ):
            raise ValueError("Google function declaration name is invalid.")
        kwargs: dict[str, object] = {"name": name}
        if "description" in function:
            description = function["description"]
            if not isinstance(description, str):
                raise ValueError("Google tool description must be text.")
            kwargs["description"] = description
        if "parameters" in function:
            parameters = function["parameters"]
            if not isinstance(parameters, dict):
                raise ValueError("Google tool parameters must be an object schema.")
            kwargs["parameters_json_schema"] = parameters
        declarations.append(types.FunctionDeclaration(**kwargs))
    if not declarations:
        return None
    return [types.Tool(function_declarations=declarations)]


def _config(
    request: GenerationRequest,
) -> types.GenerateContentConfig:
    mode = request.format_mode
    schema = request.canonical_schema
    system_instruction = request.system_prompt
    config: dict[str, object] = {
        "system_instruction": system_instruction,
        "max_output_tokens": request.output_limit.effective,
        "automatic_function_calling": types.AutomaticFunctionCallingConfig(
            disable=True, maximum_remote_calls=None
        ),
        "should_return_http_response": True,
        "http_options": types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=1)),
    }
    if mode is FormatMode.STRICT_NATIVE:
        config["response_mime_type"] = "application/json"
        config["response_json_schema"] = request.wire_schema
    elif mode is FormatMode.JSON_MODE:
        config["response_mime_type"] = "application/json"
    elif mode is FormatMode.PROMPT_ONLY:
        system_instruction = (
            f"{system_instruction}\n\n"
            "Return one JSON document conforming to this JSON Schema:\n"
            + json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
        )
        config["system_instruction"] = system_instruction
    else:
        raise ValueError("Google generation format mode is unsupported.")
    tools = _tool_declarations(request)
    if tools is not None:
        config["tools"] = tools
    return types.GenerateContentConfig(**config)


async def send_generation(
    client: genai.Client, request: GenerationRequest
) -> RawGenerationReceipt:
    response = await client.aio.models.generate_content(
        model=request.model,
        contents=_contents(request),
        config=_config(request),
    )
    raw_response = response.sdk_http_response
    if raw_response is None or raw_response.body is None:
        raise ValueError("Google SDK did not return its raw response body.")
    return receipt_from_body(raw_response.body, request.model)
