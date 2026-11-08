import uuid
from unittest.mock import AsyncMock

from eval.dialogue.cases import scenario_for
from eval.dialogue.requests import SuiteProvider
from eval.dialogue.runtime import evaluation_dispatch
from eval.dialogue.trial import run_case
from eval.support.ledger import RequestLedger

from app.ai.providers.schemas import AgentResponse, ToolCall
from app.ai.router import ModelConfig


async def test_two_turn_case_reuses_the_actual_transcript_and_world_state(tmp_path):
    provider = AsyncMock()
    calls = []
    replies = [
        AgentResponse("", [ToolCall("a", "invoke_npc", {"name": "Aldric"})]),
        AgentResponse("[[npc:Aldric:1]] The crowd waits."),
        AgentResponse("The earlier warning still hangs over the square."),
    ]

    async def generate(**kwargs):
        calls.append(kwargs)
        return replies.pop(0)

    provider.generate_with_tools.side_effect = generate
    provider.generate.return_value = (
        '{"status":"speaking","lines":["The seal was broken yesterday."]}'
    )
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
            ModelConfig("openrouter", "m:free", 60000),
            uuid.uuid4(),
        )
    assert len(data["turns"]) == 2
    assert any(
        "The seal was broken yesterday." in str(message["content"])
        for message in calls[2]["messages"]
    )
    assert data["turns"][1]["before"] == data["turns"][0]["after"]
    assert trace.count == 4
    assert data["turns"][0]["metrics"]["invocations"]["executed"] == 1
    assert data["turns"][1]["metrics"]["invocations"]["executed"] == 0
