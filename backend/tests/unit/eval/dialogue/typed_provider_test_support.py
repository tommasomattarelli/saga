from __future__ import annotations

from app.ai.generation_contracts import (
    GenerationToolReceipt,
    RawGenerationReceipt,
    RawToolArguments,
)


def dm_receipt(
    narrative_json: str,
    calls: tuple[GenerationToolReceipt, ...] = (),
) -> RawGenerationReceipt:
    return RawGenerationReceipt(text=narrative_json, tool_calls=calls)


def dm_tool_call(
    name: str, arguments: dict[str, object], call_id: str = "call-1"
) -> GenerationToolReceipt:
    return GenerationToolReceipt(
        call_id=call_id,
        name=name,
        arguments=RawToolArguments.structured(arguments),
    )
