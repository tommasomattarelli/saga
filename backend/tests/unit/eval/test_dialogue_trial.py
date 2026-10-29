import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import dialogue_trial
import pytest
from dialogue_cases import scenario_for
from dialogue_trial import run_case

from app.ai.npc_outcomes import NPCSpeaking
from app.ai.providers.schemas import AgentResponse
from app.ai.router import ModelConfig


@pytest.mark.parametrize("case_name", ["npc_followup", "npc_followup_short"])
async def test_followup_uses_runtime_reminder_and_reports_raw_vs_clean_echo(
    monkeypatch, case_name
):
    sc = scenario_for(case_name)
    line = sc.stimuli["npc_followup"].npc_dialogue
    response = AgentResponse(f'[[npc:Aldric:1]] "{line}"\n\nThe elder nods.')
    trace = SimpleNamespace(
        generate_with_tools=AsyncMock(return_value=response), count=1, errors=False
    )
    monkeypatch.setattr(
        dialogue_trial,
        "dm_request",
        lambda *_: {
            "system_prompt": "legacy prompt",
            "messages": [{"role": "user", "content": "player"}],
            "tools": [{"function": {"name": "invoke_npc"}}],
        },
    )
    data, _ = await run_case(
        case_name, sc, trace, ModelConfig("openrouter", "m:free", 1000), uuid.uuid4()
    )
    sent = trace.generate_with_tools.await_args.kwargs
    assert "language reminder" in sent["system_prompt"].casefold()
    assert "[[npc:Aldric:1]]" in sent["system_prompt"]
    assert '"completed_beats": [{"step": 0, "actors": ["Aldric"]}]' in sent["system_prompt"]
    assert line in sent["messages"][-1]["content"]
    assert data["metrics"]["raw_echo_exact"] == 1
    assert data["metrics"]["final_echo_exact"] == 0
    assert data["metrics"]["echo_guard_removals"] == 1
    assert data["metrics"]["raw_marker_count"] == 1
    assert data["metrics"]["accepted_marker_count"] == 1
    assert data["metrics"]["final_marker_count"] == 0
    assert data["metrics"]["fallback_speech_parts"] == 0


async def test_actor_scene_case_supplies_production_scene_context(monkeypatch):
    sc = scenario_for("actor_scene")
    received = {}

    async def invoke(**kwargs):
        received.update(kwargs)
        return NPCSpeaking(npc_name="Aldric", lines=("I remember the road.",))

    monkeypatch.setattr(dialogue_trial, "invoke_single_npc", invoke)
    trace = SimpleNamespace(count=0, errors=False)
    await run_case(
        "actor_scene", sc, trace, ModelConfig("openrouter", "m:free", 1000), uuid.uuid4()
    )
    scene = json.loads(received["scene_context"])
    assert scene["location"] == "Thornhaven"
    assert "condition" in scene
    assert scene["player"]["name"] == sc.campaign.character_data["name"]
