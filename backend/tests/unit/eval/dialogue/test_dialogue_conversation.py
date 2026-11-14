import uuid
from unittest.mock import AsyncMock

from eval.dialogue.cases import scenario_for
from eval.dialogue.requests import SuiteProvider
from eval.dialogue.runtime import evaluation_dispatch
from eval.dialogue.trial import run_case
from eval.support.ledger import RequestLedger

from app.ai.generation_contracts import GenerationRequest, RawGenerationReceipt
from app.ai.router import ModelConfig
from tests.unit.eval.dialogue.typed_provider_test_support import (
    dm_receipt,
    dm_tool_call,
    npc_receipt,
)


async def test_two_turn_case_reuses_the_actual_transcript_and_world_state(tmp_path):
    provider = AsyncMock()
    dm_receipts = [
        dm_receipt('{"text":""}', (dm_tool_call("invoke_npc", {"name": "Aldric"}),)),
        dm_receipt('{"text":"[[npc:Aldric:1]] The crowd waits."}'),
        dm_receipt('{"text":"The earlier warning still hangs over the square."}'),
    ]

    async def send(request: GenerationRequest) -> RawGenerationReceipt:
        if request.role == "actor":
            return npc_receipt(["The seal was broken yesterday."])
        return dm_receipts.pop(0)

    provider.send.side_effect = send
    trace = SuiteProvider(
        provider,
        RequestLedger(tmp_path / "requests", budget=14),
        key="trial",
        case="two_npc_conversation",
        model="m:free",
        run=0,
        commit="commit",
        ceiling=14,
    )
    with evaluation_dispatch():
        data, _ = await run_case(
            "two_npc_conversation",
            scenario_for("two_npc_conversation"),
            trace,
            ModelConfig("openrouter", "m:free", 60000, destination_fingerprint="test:destination"),
            uuid.uuid4(),
        )
    assert len(data["turns"]) == 2
    assert any(
        "The seal was broken yesterday." in str(message["content"])
        for message in provider.send.await_args_list[2].args[0].messages
    )
    assert data["turns"][1]["before"] == data["turns"][0]["after"]
    assert trace.count == 4
    assert data["turns"][0]["metrics"]["invocations"]["executed"] == 1
    assert data["turns"][1]["metrics"]["invocations"]["executed"] == 0
