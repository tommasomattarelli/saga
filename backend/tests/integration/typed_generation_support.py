from __future__ import annotations

import json
from collections.abc import Callable
from typing import cast

from pydantic import BaseModel, ValidationError

from app.ai.generation_contracts import (
    FormatMode,
    GenerationRequest,
    GenerationToolReceipt,
    RawGenerationReceipt,
    RawToolArguments,
)
from app.ai.npc_outcomes import NPC_RESPONSE_CONTRACT
from app.ai.providers.base import AIProvider
from app.ai.providers.schemas import AgentResponse
from app.ai.response_contracts import parse_json_document
from app.ai.tools.dm_tools import get_tool
from app.ai.tools.tools_npc import UpdateNpc
from app.ai.tools.tools_world import ChangeNpcPsychology
from app.ai.wire_contracts import encode_wire


def _npc_wire_text(raw: str) -> str:
    try:
        payload = parse_json_document(raw)
        response = NPC_RESPONSE_CONTRACT.model_type.model_validate(payload, strict=True)
    except (TypeError, ValueError, ValidationError):
        return raw

    data = cast(dict[str, object], response.model_dump(mode="python"))
    axis_changes = cast(dict[str, int], data["axis_changes"])
    data["axis_changes"] = [{"key": key, "value": value} for key, value in axis_changes.items()]
    return json.dumps(data, ensure_ascii=False, allow_nan=False)


def _tool_arguments(name: str, arguments: dict[str, object]) -> dict[str, object]:
    tool = get_tool(name)
    if tool not in (UpdateNpc, ChangeNpcPsychology):
        return arguments

    try:
        canonical = tool.model_validate(arguments, strict=True)
        wire = cast(
            dict[str, object], encode_wire(cast(BaseModel, canonical)).model_dump(mode="python")
        )
    except (TypeError, ValueError, ValidationError):
        return arguments

    return {key: wire[key] for key in arguments}


def _dm_receipt(response: AgentResponse) -> RawGenerationReceipt:
    text = json.dumps({"text": response.text}, ensure_ascii=False, allow_nan=False)
    tools = tuple(
        GenerationToolReceipt(
            call_id=call.id,
            name=call.name,
            arguments=RawToolArguments.structured(
                _tool_arguments(call.name, cast(dict[str, object], call.arguments))
                if call.name is not None
                else cast(dict[str, object], call.arguments)
            ),
            signature=call.signature,
        )
        for call in response.tool_calls
    )
    candidate = json.dumps(
        {
            "text": text,
            "tool_calls": [
                {
                    "id": call.call_id,
                    "name": call.name,
                    "arguments": call.arguments.structured_value,
                    "signature": call.signature.hex() if call.signature is not None else None,
                }
                for call in tools
            ],
        },
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    return RawGenerationReceipt(
        text=text,
        tool_calls=tools,
        text_signature=response.text_signature,
        raw_candidate=candidate,
    )


def _actor_receipt(request: GenerationRequest, raw: str) -> RawGenerationReceipt:
    if (
        request.contract.name == NPC_RESPONSE_CONTRACT.name
        and request.format_mode is FormatMode.STRICT_NATIVE
    ):
        raw = _npc_wire_text(raw)
    return RawGenerationReceipt(text=raw, raw_candidate=raw)


async def send_from_legacy(
    provider: AIProvider,
    request: GenerationRequest,
    assert_no_db_held: Callable[[], None],
) -> RawGenerationReceipt:
    assert_no_db_held()
    if request.tool_declarations:
        response = await provider.generate_with_tools(
            system_prompt=request.system_prompt,
            messages=request.messages,
            tools=request.tool_declarations,
            model=request.model,
            max_tokens=request.output_limit.effective,
        )
        if isinstance(response, AgentResponse) and request.contract.name == "dm-narrative":
            return _dm_receipt(response)
        if isinstance(response, AgentResponse):
            return RawGenerationReceipt(
                text=response.text,
                text_signature=response.text_signature,
            )
        raise TypeError("Typed test scripts must return AgentResponse for tool requests.")

    raw = await provider.generate(
        system_prompt=request.system_prompt,
        messages=request.messages,
        model=request.model,
        max_tokens=request.output_limit.effective,
        json_mode=request.format_mode is FormatMode.JSON_MODE,
    )
    if not isinstance(raw, str):
        raise TypeError("Typed test scripts must return text for non-tool requests.")
    return _actor_receipt(request, raw)
