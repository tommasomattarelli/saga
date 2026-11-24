from __future__ import annotations

import base64
import json
from typing import cast

from pydantic import JsonValue

from app.ai.generation_contracts import (
    GenerationToolReceipt,
    RawGenerationReceipt,
    RawToolArguments,
)
from app.ai.providers.usage import UsageMetadata
from app.ai.response_contracts import parse_json_document


def _string(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"Google response {field} must be text.")
    return value


def _integer(value: object, field: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"Google response {field} must be an integer.")
    return value


def _signature(value: object) -> bytes | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("Google response thought signature must be base64 text.")
    return base64.b64decode(value, validate=True)


def receipt_from_body(raw_body: str, model: str) -> RawGenerationReceipt:
    response_value = parse_json_document(raw_body)
    if not isinstance(response_value, dict):
        raise ValueError("Google response must be a JSON object.")
    response = cast(dict[str, JsonValue], response_value)
    raw_candidates = response.get("candidates")
    if raw_candidates is not None and not isinstance(raw_candidates, list):
        raise TypeError("Google response candidates must be a list.")
    candidates = cast(list[JsonValue], raw_candidates or [])
    candidate_value = candidates[0] if candidates else None
    if candidate_value is not None and not isinstance(candidate_value, dict):
        raise TypeError("Google response candidate must be an object.")
    candidate = (
        cast(dict[str, JsonValue], candidate_value) if candidate_value is not None else None
    )
    text_parts: list[str] = []
    tool_calls: list[GenerationToolReceipt] = []
    text_signature: bytes | None = None
    content = candidate.get("content") if candidate is not None else None
    if content is not None and not isinstance(content, dict):
        raise TypeError("Google response candidate content must be an object.")
    parts_value = content.get("parts") if isinstance(content, dict) else None
    if parts_value is not None and not isinstance(parts_value, list):
        raise TypeError("Google response candidate parts must be a list.")
    for part_value in cast(list[JsonValue], parts_value or []):
        if not isinstance(part_value, dict):
            raise TypeError("Google response candidate part must be an object.")
        part = cast(dict[str, JsonValue], part_value)
        thought = part.get("thought")
        if thought is not None and not isinstance(thought, bool):
            raise TypeError("Google response thought marker must be boolean.")
        text = part.get("text")
        if text is not None:
            if not isinstance(text, str):
                raise TypeError("Google response text part must be text.")
            if thought is not True:
                text_parts.append(text)
                signature = _signature(part.get("thoughtSignature"))
                if text_signature is None and signature is not None:
                    text_signature = signature
        function_call_value = part.get("functionCall")
        if function_call_value is not None:
            if not isinstance(function_call_value, dict):
                raise TypeError("Google response function call must be an object.")
            function_call = cast(dict[str, JsonValue], function_call_value)
            tool_calls.append(
                GenerationToolReceipt(
                    call_id=_string(function_call.get("id"), "function call id"),
                    name=_string(function_call.get("name"), "function call name"),
                    arguments=RawToolArguments.structured(function_call.get("args")),
                    signature=_signature(part.get("thoughtSignature")),
                )
            )
    prompt_feedback_value = response.get("promptFeedback")
    if prompt_feedback_value is not None and not isinstance(prompt_feedback_value, dict):
        raise TypeError("Google response prompt feedback must be an object.")
    prompt_feedback = cast(dict[str, JsonValue], prompt_feedback_value or {})
    blocked_reason = _string(prompt_feedback.get("blockReason"), "block reason")
    finish_reason = _string(candidate.get("finishReason"), "finish reason") if candidate else None
    if blocked_reason is None and finish_reason in {
        "SAFETY",
        "RECITATION",
        "BLOCKLIST",
        "PROHIBITED_CONTENT",
        "SPII",
    }:
        blocked_reason = finish_reason
    usage_value = response.get("usageMetadata")
    if usage_value is not None and not isinstance(usage_value, dict):
        raise TypeError("Google response usage metadata must be an object.")
    usage = cast(dict[str, JsonValue], usage_value or {})
    response_id = _string(response.get("responseId"), "response id")
    response_model = _string(response.get("modelVersion"), "model version")
    model_id = model if response_model is None else response_model
    usage_metadata = (
        UsageMetadata(
            response_id=response_id,
            model=model_id,
            input_tokens=_integer(usage.get("promptTokenCount"), "prompt token count"),
            output_tokens=_integer(usage.get("candidatesTokenCount"), "candidate token count"),
            total_tokens=_integer(usage.get("totalTokenCount"), "total token count"),
            cached_input_tokens=_integer(
                usage.get("cachedContentTokenCount"), "cached token count"
            ),
            reasoning_output_tokens=_integer(
                usage.get("thoughtsTokenCount"), "thought token count"
            ),
        )
        if usage_value is not None
        else None
    )
    raw_candidate = (
        json.dumps(
            {"encoding_version": 1, "candidate": candidate},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if candidate is not None
        else None
    )
    return RawGenerationReceipt(
        text="".join(text_parts) if text_parts else None,
        tool_calls=tuple(tool_calls),
        finish_reason=finish_reason,
        refusal=_string(candidate.get("refusal"), "refusal") if candidate else None,
        blocked_reason=blocked_reason,
        response_id=response_id,
        model_id=model_id,
        usage=usage_metadata,
        text_signature=text_signature,
        raw_candidate=raw_candidate,
    )
