import json
import uuid
from unittest.mock import AsyncMock

import pytest
from dialogue_cases import scenario_for
from dialogue_pipeline import run_pipeline
from dialogue_requests import SuiteProvider
from dialogue_runtime import evaluation_dispatch
from ledger import RequestLedger

from app.ai.providers.schemas import AgentResponse, ToolCall
from app.ai.router import ModelConfig


@pytest.mark.parametrize(
    ("case_name", "semantic_review"),
    [("two_npc_two_beat", False), ("two_npc_natural", True)],
)
async def test_real_two_beat_path_counts_dm_and_actors_without_db_or_background(
    tmp_path, case_name, semantic_review
):
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
        case=case_name,
        model="m:free",
        run=0,
        commit="commit",
        ceiling=7,
    )
    with evaluation_dispatch():
        data, failed = await run_pipeline(
            scenario_for(case_name),
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
    assert data["metrics"]["invocations"] == {
        "requested": 3,
        "selected": 3,
        "executed": 3,
        "succeeded": 3,
        "speaking": 3,
        "silent": 0,
        "failed": 0,
    }
    assert data["metrics"]["second_beat"]["successful"] is True
    assert data["metrics"]["second_beat"]["requested"] is True
    assert data["metrics"]["language_status"] == (
        "likely-it" if not semantic_review else "needs-review"
    )
    assert data["metrics"]["language_review_required"] is True
    assert data["metrics"]["semantic_review_required"] is semantic_review
    assert data["metrics"]["raw_marker_count"] == 3
    assert data["metrics"]["accepted_marker_count"] == 3
    assert data["metrics"]["fallback_speech_parts"] == 0
    assert data["metrics"]["final_marker_count"] == 0
    requests = [call.kwargs for call in provider.generate_with_tools.await_args_list]
    for request in requests:
        assert request["system_prompt"].count("DIALOGUE COMPOSITION:") == 1
        assert "GOOD DM:" in request["system_prompt"]
        assert "BAD DM:" in request["system_prompt"]
    closing_request = requests[-1]
    assert "CLOSING STEP:" in closing_request["system_prompt"]
    assert 'tool="invoke_npc"' not in closing_request["system_prompt"]
    assert "invoke_npc" not in {tool["function"]["name"] for tool in closing_request["tools"]}
