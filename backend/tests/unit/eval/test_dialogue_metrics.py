import uuid
from unittest.mock import AsyncMock

from dialogue_cases import scenario_for
from dialogue_pipeline import run_pipeline
from dialogue_requests import SuiteProvider
from ledger import RequestLedger

from app.ai.providers.schemas import AgentResponse, ToolCall
from app.ai.router import ModelConfig


async def test_second_beat_metrics_match_the_required_actor_and_separate_languages(tmp_path):
    provider = AsyncMock()
    provider.generate_with_tools.side_effect = [
        AgentResponse(
            "",
            [
                ToolCall("a", "invoke_npc", {"name": "Aldric"}),
                ToolCall("m", "invoke_npc", {"name": "Mira"}),
            ],
        ),
        AgentResponse("", [ToolCall("m2", "invoke_npc", {"name": "Mira"})]),
        AgentResponse(
            "The bell rings and the crowd watches you. [[npc:Aldric:1]] [[npc:Mira:1]] [[npc:Mira:2]]"
        ),
    ]
    provider.generate.return_value = (
        '{"status":"speaking","lines":["Non ti conosco, non sono del villaggio."]}'
    )
    trace = SuiteProvider(
        provider,
        RequestLedger(tmp_path / "requests", budget=7),
        key="trial",
        case="two_npc_two_beat",
        model="m:free",
        run=0,
        commit="commit",
        ceiling=7,
    )
    data, _ = await run_pipeline(
        scenario_for("two_npc_two_beat"),
        trace,
        ModelConfig("openrouter", "m:free", 60000),
        uuid.uuid4(),
    )
    metrics = data["metrics"]
    assert metrics["second_beat"]["requested"] is False
    assert metrics["second_beat"]["executed"] is False
    assert metrics["second_beat"]["successful"] is False
    assert metrics["narrator_language"]["detected"] == "en"
    assert all(actor["detected"] == "it" for actor in metrics["actor_languages"])


async def test_requested_second_actor_failure_is_not_a_missing_invocation(tmp_path):
    provider = AsyncMock()
    provider.generate_with_tools.side_effect = [
        AgentResponse(
            "",
            [
                ToolCall("a", "invoke_npc", {"name": "Aldric"}),
                ToolCall("m", "invoke_npc", {"name": "Mira"}),
            ],
        ),
        AgentResponse("", [ToolCall("a2", "invoke_npc", {"name": "Aldric"})]),
        AgentResponse("La campana suona. [[npc:Aldric:1]] [[npc:Mira:1]]"),
    ]
    seen = 0

    async def generate(**kwargs):
        nonlocal seen
        seen += 1
        return (
            '{"status":{},"lines":[]}'
            if seen == 3
            else '{"status":"speaking","lines":["Non conosco la tua storia."]}'
        )

    provider.generate.side_effect = generate
    trace = SuiteProvider(
        provider,
        RequestLedger(tmp_path / "requests", budget=7),
        key="trial",
        case="two_npc_two_beat",
        model="m:free",
        run=0,
        commit="commit",
        ceiling=7,
    )
    data, _ = await run_pipeline(
        scenario_for("two_npc_two_beat"),
        trace,
        ModelConfig("openrouter", "m:free", 60000),
        uuid.uuid4(),
    )
    metrics = data["metrics"]
    assert metrics["second_beat"]["requested"] is True
    assert metrics["second_beat"]["executed"] is True
    assert metrics["second_beat"]["successful"] is False
    assert metrics["second_beat"]["received_prior_public_lines"] is True
    assert metrics["invocations"]["failed"] == 1
