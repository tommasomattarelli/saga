from __future__ import annotations

import base64
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, StrictBool, StrictFloat, StrictInt, StrictStr

from app.ai.generation_contracts import (
    GenerationToolReceipt,
    RawGenerationReceipt,
    RawToolArguments,
)
from app.ai.providers.usage import UsageMetadata

_ENCODING_VERSION = 1


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class _Usage(_StrictModel):
    response_id: StrictStr | None = None
    model: StrictStr | None = None
    input_tokens: StrictInt | None = None
    output_tokens: StrictInt | None = None
    total_tokens: StrictInt | None = None
    cached_input_tokens: StrictInt | None = None
    reasoning_output_tokens: StrictInt | None = None
    cost: StrictFloat | None = None
    currency: StrictStr | None = None
    role: StrictStr | None = None
    step: StrictInt | None = None
    beat: StrictInt | None = None
    npc_id: StrictStr | None = None
    npc_name: StrictStr | None = None


class _Tool(_StrictModel):
    call_id: StrictStr | None
    name: StrictStr | None
    argument_kind: Literal["raw_text", "structured"]
    raw_text: StrictStr | None
    structured_arguments: object | None
    signature: StrictStr | None


class _Receipt(_StrictModel):
    text: StrictStr | None
    tool_calls: tuple[_Tool, ...]
    finish_reason: StrictStr | None
    refusal: StrictStr | None
    blocked_reason: StrictStr | None
    response_id: StrictStr | None
    model_id: StrictStr | None
    usage: _Usage | None
    text_signature: StrictStr | None


class _Envelope(_StrictModel):
    encoding_version: Literal[1]
    receipt: _Receipt
    candidate_in_column: StrictBool


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def encode_receipt(receipt: RawGenerationReceipt) -> tuple[str, str | None]:
    tools = []
    for tool in receipt.tool_calls:
        args = tool.arguments
        tools.append(
            {
                "call_id": tool.call_id,
                "name": tool.name,
                "argument_kind": args.kind,
                "raw_text": args.raw_text_value,
                "structured_arguments": args.structured_value,
                "signature": (
                    base64.b64encode(tool.signature).decode("ascii")
                    if tool.signature is not None
                    else None
                ),
            }
        )
    usage = None
    if receipt.usage is not None:
        usage = _Usage.model_validate(receipt.usage.__dict__).model_dump(mode="json")
    envelope = _Envelope.model_validate(
        {
            "encoding_version": _ENCODING_VERSION,
            "candidate_in_column": receipt.raw_candidate is not None,
            "receipt": {
                "text": receipt.text,
                "tool_calls": tuple(tools),
                "finish_reason": receipt.finish_reason,
                "refusal": receipt.refusal,
                "blocked_reason": receipt.blocked_reason,
                "response_id": receipt.response_id,
                "model_id": receipt.model_id,
                "usage": usage,
                "text_signature": (
                    base64.b64encode(receipt.text_signature).decode("ascii")
                    if receipt.text_signature is not None
                    else None
                ),
            },
        }
    )
    return _canonical_json(envelope.model_dump(mode="json")), receipt.raw_candidate


def _decode_bytes(value: str | None) -> bytes | None:
    if value is None:
        return None
    return base64.b64decode(value, validate=True)


def _object_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Stored generation receipt contains duplicate keys.")
        result[key] = value
    return result


def _decode_arguments(tool: _Tool) -> RawToolArguments:
    if tool.argument_kind == "raw_text":
        if tool.raw_text is None or tool.structured_arguments is not None:
            raise ValueError("Stored tool arguments do not match their declared representation.")
        return RawToolArguments.raw_text(tool.raw_text)
    if tool.raw_text is not None:
        raise ValueError("Stored tool arguments do not match their declared representation.")
    return RawToolArguments.structured(tool.structured_arguments)


def decode_receipt(encoded: str, candidate: str | None) -> RawGenerationReceipt:
    try:
        json.loads(encoded, object_pairs_hook=_object_without_duplicates)
        envelope = _Envelope.model_validate_json(encoded)
        if envelope.candidate_in_column != (candidate is not None):
            raise ValueError("Receipt candidate reference does not match stored candidate.")
        tools = tuple(
            GenerationToolReceipt(
                call_id=tool.call_id,
                name=tool.name,
                arguments=_decode_arguments(tool),
                signature=_decode_bytes(tool.signature),
            )
            for tool in envelope.receipt.tool_calls
        )
        usage = (
            UsageMetadata(**envelope.receipt.usage.model_dump())
            if envelope.receipt.usage is not None
            else None
        )
        return RawGenerationReceipt(
            text=envelope.receipt.text,
            tool_calls=tools,
            finish_reason=envelope.receipt.finish_reason,
            refusal=envelope.receipt.refusal,
            blocked_reason=envelope.receipt.blocked_reason,
            response_id=envelope.receipt.response_id,
            model_id=envelope.receipt.model_id,
            usage=usage,
            text_signature=_decode_bytes(envelope.receipt.text_signature),
            raw_candidate=candidate,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Stored generation receipt is invalid.") from exc
