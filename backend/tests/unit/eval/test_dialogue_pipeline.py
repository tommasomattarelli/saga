import json
import uuid
from unittest.mock import AsyncMock

from dialogue_cases import scenario_for
from dialogue_pipeline import run_pipeline
from dialogue_requests import SuiteProvider
from ledger import RequestLedger

from app.ai.providers.schemas import AgentResponse, ToolCall
from app.ai.router import ModelConfig


async def test_real_two_beat_path_counts_dm_and_actors_without_db_or_background(tmp_path):
    provider = AsyncMock()
    provider.generate_with_tools.side_effect = [
        AgentResponse(
            "",
            [
                ToolCall(
                    "a", "invoke_npc", {"name": "Aldric", "context": "Your independent answer."}
                ),
                ToolCall(
                    "m", "invoke_npc", {"name": "Mira", "context": "Your independent answer."}
                ),
            ],
        ),
        AgentResponse(
            "", [ToolCall("a2", "invoke_npc", {"name": "Aldric", "context": "React to Mira."})]
        ),
        AgentResponse("[[npc:Aldric:1]] [[npc:Mira:1]] [[npc:Aldric:2]]"),
    ]
    actor_inputs = []

    async def actor(**kwargs):
        content = kwargs["messages"][0]["content"]
        actor_inputs.append(content)
        line = "Una seconda risposta." if "React to Mira." in content else "Una prima risposta."
        return json.dumps({"status": "speaking", "lines": [line]})

    provider.generate.side_effect = actor
    ledger = RequestLedger(tmp_path / "calls", budget=7)
    trace = SuiteProvider(
        provider,
        ledger,
        key="trial",
        case="two_npc_two_beat",
        model="m:free",
        run=0,
        commit="commit",
        ceiling=7,
    )
    data, failed = await run_pipeline(
        scenario_for("two_npc_two_beat"),
        trace,
        ModelConfig("openrouter", "m:free", 60000),
        uuid.uuid4(),
    )
    assert trace.count == 6 and ledger.spent == 6
    assert data["dm_steps"] == 3 and len(data["beats"]) == 2
    assert "Una prima risposta." not in actor_inputs[0]
    assert "Una prima risposta." not in actor_inputs[1]
    assert "Una prima risposta." in actor_inputs[2]
    assert "[[npc:" not in data["narration"]
    assert data["narration"].count("Una prima risposta.") == 2
    assert data["narration"].count("Una seconda risposta.") == 1
    assert "not-batched" not in failed and "missing-dependent-beat" not in failed
