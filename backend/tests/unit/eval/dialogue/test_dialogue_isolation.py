import asyncio
import json
import uuid
from unittest.mock import AsyncMock

from eval.dialogue.cases import scenario_for
from eval.dialogue.pipeline import run_pipeline
from eval.dialogue.requests import SuiteProvider
from eval.dialogue.runtime import evaluation_dispatch
from eval.support.ledger import RequestLedger

from app.ai.providers.schemas import AgentResponse, ToolCall
from app.ai.providers.usage import capture_usage
from app.ai.router import ModelConfig


async def test_overlapping_pipelines_keep_generation_actor_observation_and_metrics_local(
    monkeypatch,
    tmp_path,
):
    forbidden = AsyncMock(side_effect=AssertionError("Unexpected profile/database access"))
    monkeypatch.setattr("app.core.dm.dm_nodes.get_user_generation", forbidden)
    monkeypatch.setattr("app.ai.generation_context.get_user_generation", forbidden)
    ledger = RequestLedger(tmp_path / "ledger.jsonl", budget=6)
    both_started = asyncio.Event()
    starts = []
    traces = []

    def pipeline(model):
        provider = AsyncMock()
        steps = 0

        async def dm(**kwargs):
            nonlocal steps
            assert kwargs["model"] == model
            steps += 1
            capture_usage(
                {"id": f"{model}:dm:{steps}", "usage": {"prompt_tokens": 11}}, model=model
            )
            if steps == 1:
                starts.append(model)
                if len(starts) == 2:
                    both_started.set()
                await both_started.wait()
                return AgentResponse("", [ToolCall("a", "invoke_npc", {"name": "Aldric"})])
            await asyncio.sleep(0)
            return AgentResponse("[[npc:Aldric:1]]")

        async def actor(**kwargs):
            assert kwargs["model"] == model
            await asyncio.sleep(0)
            capture_usage({"id": f"{model}:actor", "usage": {"prompt_tokens": 7}}, model=model)
            return json.dumps({"status": "speaking", "lines": [f"I speak for {model}."]})

        provider.generate_with_tools.side_effect = dm
        provider.generate.side_effect = actor
        trace = SuiteProvider(
            provider,
            ledger,
            key=model,
            case="two_npc_natural",
            model=model,
            run=0,
            commit="commit",
            ceiling=3,
        )
        traces.append(trace)
        return run_pipeline(
            scenario_for("two_npc_natural"),
            trace,
            ModelConfig("openrouter", model, 60000),
            uuid.uuid4(),
        )

    with evaluation_dispatch():
        results = await asyncio.wait_for(
            asyncio.gather(pipeline("vendor/a"), pipeline("vendor/b")), 5
        )
    for trace, (data, failures) in zip(traces, results, strict=True):
        assert not failures
        assert trace.count == 3
        assert data["narration"] == f'Aldric: "I speak for {trace.model}."'
        assert data["metrics"]["invocations"]["selected"] == 1
        assert data["metrics"]["invocations"]["executed"] == 1
        assert len(data["metrics"]["actor_calls"]) == 1
    assert ledger.spent == 6 and not ledger.interrupted()
    for attempt in ledger.results():
        assert len(attempt.usage) == 1
        usage = attempt.usage[0]
        assert usage["model"] == attempt.model
        assert usage["response_id"].startswith(attempt.model)
        assert usage["role"] == attempt.correlation["role"]
        assert usage["step"] == attempt.correlation["step"]
        assert usage["npc_name"] == ("Aldric" if attempt.probe.endswith(":actor") else None)
    forbidden.assert_not_called()
