import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from eval.memory.plan import prepare_plan, write_plan
from eval.memory.run_lock import evidence_run_lock
from eval.memory.runner import run_plan
from eval.support.ledger import Attempt, RequestLedger

from app.ai.router import ModelConfig
from app.memory.document_contracts import GlobalPayload
from app.memory.producer_contracts import MemoryOutputError


@pytest.fixture(autouse=True)
def stub_provider_affinity(monkeypatch: pytest.MonkeyPatch) -> None:
    import eval.memory.runner as runner

    def clone(provider, session_id):
        return SimpleNamespace(
            generate=getattr(provider, "generate", None),
            client=SimpleNamespace(default_headers={"x-session-id": session_id}),
        )

    monkeypatch.setattr(runner, "provider_with_session", clone)


def make_plan(*, source_count: int = 1, global_count: int = 1, language: str = "en"):
    turn_ids = [str(uuid4()) for _ in range(source_count * 2)]
    turns = [
        {
            "reference": "t1",
            "turn_id": turn_ids[0],
            "player_action": "Ask",
            "narration": "A door opens.",
            "operations": None,
        },
        {
            "reference": "t2",
            "turn_id": turn_ids[1],
            "player_action": "Wait",
            "narration": "The party rests.",
            "operations": None,
        },
    ]
    return prepare_plan(
        sources=[
            {
                "turns": [
                    {**turn, "turn_id": turn_ids[index * 2 + offset]}
                    for offset, turn in enumerate(turns)
                ]
            }
            for index in range(source_count)
        ],
        facts_policy={
            "max_per_batch": 2,
            "importance_levels": [{"name": "high", "criteria": "Major", "examples": "Secret"}],
        },
        global_policy={"target_words": 100},
        language=language,
        models=["provider/model"],
        repetitions=1,
        global_count=global_count,
        session_scope="test-memory-scope",
    )


@pytest.mark.asyncio
async def test_runner_reserves_failures_and_never_retries_completed_or_interrupted(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from eval.support import live_calls

    from app.memory import producers

    calls = AsyncMock(side_effect=MemoryOutputError("offline validation failure"))
    monkeypatch.setattr(producers, "generate_memory", calls)
    plan = make_plan()
    monkeypatch.setattr(
        live_calls,
        "resolve_eval_generation",
        AsyncMock(
            return_value=(object(), ModelConfig("openrouter", "provider/model", plan.output_cap))
        ),
    )
    write_plan(plan, tmp_path)
    await run_plan(plan, tmp_path, uuid4(), authorized=True)
    assert calls.await_count == plan.call_budget == 4
    ledger = RequestLedger(tmp_path / "requests.jsonl")
    assert ledger.spent == 4
    assert {attempt.status for attempt in ledger.results()} == {"error"}
    await run_plan(plan, tmp_path, uuid4(), authorized=True)
    assert calls.await_count == 4


@pytest.mark.asyncio
async def test_runner_requires_authorization_before_provider_resolution(tmp_path) -> None:
    plan = make_plan()
    with pytest.raises(ValueError, match="authorization"):
        await run_plan(plan, tmp_path, uuid4(), authorized=False)
    assert not (tmp_path / "requests.jsonl").exists()


@pytest.mark.asyncio
async def test_global_is_one_oldest_first_chain_shared_outside_the_split_arms(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from eval.support import live_calls

    from app.memory import producers

    plan = make_plan(source_count=2, global_count=2)
    requests = []

    async def generate(request):
        requests.append(request)
        if request.kind != "global":
            raise MemoryOutputError("offline validation failure")
        payload = GlobalPayload(
            story_so_far=f"checkpoint-{len([item for item in requests if item.kind == 'global'])}",
            open_threads=(),
            relationships=(),
            resolved_threads=(),
        )
        return SimpleNamespace(payload=payload, raw=payload.model_dump_json(), facts=())

    monkeypatch.setattr(producers, "generate_memory", generate)
    monkeypatch.setattr(
        live_calls,
        "resolve_eval_generation",
        AsyncMock(
            return_value=(object(), ModelConfig("openrouter", "provider/model", plan.output_cap))
        ),
    )
    await run_plan(plan, tmp_path, uuid4(), authorized=True)
    globals_ = [request for request in requests if request.kind == "global"]
    assert len(globals_) == plan.global_count == 2
    assert json.loads(globals_[0].user_prompt)["previous"] is None
    assert json.loads(globals_[1].user_prompt)["previous"]["story_so_far"] == "checkpoint-1"
    assert plan.call_budget == len(requests) == 8


@pytest.mark.asyncio
async def test_interrupted_ledger_stops_before_resolving_provider(tmp_path, monkeypatch) -> None:
    from eval.support import live_calls

    plan = make_plan()
    write_plan(plan, tmp_path)
    RequestLedger(tmp_path / "requests.jsonl").reserve(
        Attempt("interrupted", "batch-1", "unified", 1)
    )
    resolve = AsyncMock()
    monkeypatch.setattr(live_calls, "resolve_eval_generation", resolve)
    with pytest.raises(ValueError, match="manual review"):
        await run_plan(plan, tmp_path, uuid4(), authorized=True)
    resolve.assert_not_awaited()


@pytest.mark.asyncio
async def test_plan_must_match_directory_manifest_before_profile_resolution(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from eval.support import live_calls

    original = make_plan()
    edited = make_plan(language="it")
    write_plan(original, tmp_path)
    resolve = AsyncMock()
    monkeypatch.setattr(live_calls, "resolve_eval_generation", resolve)
    with pytest.raises(ValueError, match="manifest changed"):
        await run_plan(edited, tmp_path, uuid4(), authorized=True)
    resolve.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_lock_rejects_second_process_and_keeps_stale_marker(
    tmp_path, monkeypatch
) -> None:
    from eval.support import live_calls

    plan = make_plan()
    resolve = AsyncMock()
    monkeypatch.setattr(live_calls, "resolve_eval_generation", resolve)
    with evidence_run_lock(tmp_path), pytest.raises(RuntimeError, match="locked"):
        await run_plan(plan, tmp_path, uuid4(), authorized=True)
    stale = tmp_path / ".run.lock"
    stale.write_text("pid=crashed\n")
    with pytest.raises(RuntimeError, match="stale lock"):
        await run_plan(plan, tmp_path, uuid4(), authorized=True)
    assert stale.read_text() == "pid=crashed\n"
    resolve.assert_not_awaited()


@pytest.mark.asyncio
async def test_trace_retains_invalid_raw_and_reserves_full_request_before_provider_call(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from eval.support import live_calls

    plan = make_plan(global_count=0)
    raw = '{"unexpected":"provider output"}'
    provider = SimpleNamespace()

    async def generate(**kwargs):
        reservations = [
            json.loads(line)
            for line in (tmp_path / "requests.jsonl").read_text().splitlines()
            if '"event": "reserve"' in line
        ]
        request = reservations[-1]["request"]
        assert request == kwargs
        assert request["json_mode"] is True
        assert request["model"] == "provider/model"
        return raw

    provider.generate = AsyncMock(side_effect=generate)
    monkeypatch.setattr(
        live_calls,
        "resolve_eval_generation",
        AsyncMock(
            return_value=(provider, ModelConfig("openrouter", "provider/model", plan.output_cap))
        ),
    )
    await run_plan(plan, tmp_path, uuid4(), authorized=True)
    evidence = [json.loads(line) for line in (tmp_path / "outputs.jsonl").read_text().splitlines()]
    assert len(evidence) == 3
    assert all(row["status"] == "error" and row["raw"] == raw for row in evidence)
    assert all(
        row["error"] == "Generated output failed memory contract validation." for row in evidence
    )


@pytest.mark.asyncio
async def test_resolved_output_cap_mismatch_blocks_generation(tmp_path, monkeypatch) -> None:
    from eval.support import live_calls

    plan = make_plan(global_count=0)
    resolve = AsyncMock(
        return_value=(object(), ModelConfig("openrouter", "provider/model", plan.output_cap + 1))
    )
    monkeypatch.setattr(live_calls, "resolve_eval_generation", resolve)
    with pytest.raises(ValueError, match="output cap"):
        await run_plan(plan, tmp_path, uuid4(), authorized=True)
    assert not (tmp_path / "requests.jsonl").exists()


@pytest.mark.parametrize("status", [401, 402, 403, 429, None])
@pytest.mark.asyncio
async def test_auth_error_pauses_after_one_reserved_attempt_and_blocks_resume(
    tmp_path, monkeypatch: pytest.MonkeyPatch, status: int | None
) -> None:
    import httpx
    from eval.memory.runner import EvaluationPausedError
    from eval.support import live_calls

    from app.exceptions import AIProviderError

    plan = make_plan(global_count=0)
    if status is None:
        failure = AIProviderError("openrouter", "rate limited (code 429)")
    else:
        request = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
        response = httpx.Response(status, request=request, text="private credential detail")
        failure = httpx.HTTPStatusError(str(status), request=request, response=response)
    provider = SimpleNamespace(generate=AsyncMock(side_effect=failure))
    resolve = AsyncMock(
        return_value=(provider, ModelConfig("openrouter", "provider/model", plan.output_cap))
    )
    monkeypatch.setattr(live_calls, "resolve_eval_generation", resolve)
    with pytest.raises(EvaluationPausedError, match="check authorization"):
        await run_plan(plan, tmp_path, uuid4(), authorized=True)
    assert provider.generate.await_count == 1
    ledger = RequestLedger(tmp_path / "requests.jsonl")
    assert ledger.spent == 1
    assert ledger.results()[0].correlation["fatal_provider_error"] is True
    assert "private credential detail" not in (tmp_path / "outputs.jsonl").read_text()
    with pytest.raises(EvaluationPausedError, match="new evidence directory"):
        await run_plan(plan, tmp_path, uuid4(), authorized=True)
    resolve.assert_awaited_once()
