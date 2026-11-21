from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from app.ai.generation_contracts import (
    GenerationRequest,
    GenerationToolReceipt,
    RawGenerationReceipt,
    RawToolArguments,
)


class TypedResponseProvider:
    def __init__(
        self,
        receipts: list[RawGenerationReceipt | Exception],
        *,
        before_send: Callable[[GenerationRequest], Awaitable[None]] | None = None,
    ) -> None:
        self.receipts = receipts
        self.requests: list[GenerationRequest] = []
        self.before_send = before_send

    async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
        self.requests.append(request)
        if self.before_send is not None:
            await self.before_send(request)
        receipt = self.receipts.pop(0)
        if isinstance(receipt, Exception):
            raise receipt
        return receipt


def dm_receipt(
    narrative_json: str,
    calls: tuple[GenerationToolReceipt, ...] = (),
) -> RawGenerationReceipt:
    return RawGenerationReceipt(text=narrative_json, tool_calls=calls)


def npc_receipt(lines: list[str], *, status: str = "speaking") -> RawGenerationReceipt:
    return RawGenerationReceipt(
        text=json.dumps(
            {
                "status": status,
                "lines": lines,
                "action": None,
                "axis_changes": [],
                "reveals_secret": False,
            }
        )
    )


def dm_tool_call(
    name: str, arguments: dict[str, object], call_id: str = "call-1"
) -> GenerationToolReceipt:
    return GenerationToolReceipt(
        call_id=call_id,
        name=name,
        arguments=RawToolArguments.structured(arguments),
    )
