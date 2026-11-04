import asyncio
import json
from unittest.mock import AsyncMock, Mock

import dialogue_execution
import dialogue_suite
import pytest
from dialogue_plan import manifest
from ledger import RequestLedger

from app.ai.providers.schemas import AgentResponse
from app.ai.router import ModelConfig


def prepare_run(monkeypatch, tmp_path, models, cases, budget, runs=1):
    plan = manifest(models=models, case_names=cases, runs=runs, paid_allowlist=set(models))
    monkeypatch.setattr(dialogue_suite, "manifest", lambda *_: plan)
    monkeypatch.setattr(
        dialogue_suite.subprocess,
        "check_output",
        lambda args, **kwargs: "" if "status" in args else "commit",
    )
    monkeypatch.setattr(dialogue_suite, "validate_eval_models", AsyncMock())

    async def generation(owner, model, **kwargs):
        provider = AsyncMock()
        provider.generate_with_tools.return_value = AgentResponse(model)
        provider.generate.return_value = '{"status":"silent","lines":[]}'
        return provider, ModelConfig("openrouter", model, 60000)

    monkeypatch.setattr(dialogue_suite, "resolve_eval_generation", generation)
    monkeypatch.setattr(
        "sys.argv",
        [
            "suite",
            "--user",
            "00000000-0000-0000-0000-000000000001",
            "--budget",
            str(budget),
            "--ledger",
            str(tmp_path / "ledger.jsonl"),
            "--results",
            str(tmp_path / "trials.jsonl"),
        ],
    )
    return plan


@pytest.mark.parametrize("model_count", [4, 6])
async def test_model_workers_advance_independently_without_a_task_barrier(
    monkeypatch,
    tmp_path,
    model_count,
):
    models = [f"vendor/model-{index}" for index in range(model_count)]
    prepare_run(monkeypatch, tmp_path, models, ["npc_speaks", "npc_followup"], model_count * 2)
    all_started = asyncio.Event()
    fast_second = asyncio.Event()
    first_starts = []
    finished = []

    async def run(case, scenario, trace, config, owner):
        if case == "npc_speaks":
            first_starts.append(config.model)
            if len(first_starts) == model_count:
                all_started.set()
            await all_started.wait()
            if config.model != models[0]:
                await fast_second.wait()
        elif config.model == models[0]:
            assert finished == [(models[0], "npc_speaks")]
            fast_second.set()
        await trace.generate_with_tools("system", [], [], config.model)
        finished.append((config.model, case))
        return {"model": config.model}, []

    monkeypatch.setattr(dialogue_suite, "run_case", run)
    await asyncio.wait_for(dialogue_suite.main(), 5)
    assert set(first_starts) == set(models)
    assert len(finished) == model_count * 2
    assert RequestLedger(tmp_path / "ledger.jsonl").spent == model_count * 2
    summary = json.loads((tmp_path / "trials.summary.json").read_text())
    assert summary["all_trials_recorded"]
    assert set(summary["timing"]["model_wall_seconds"]) == set(models)
    rows, interrupted = dialogue_suite.read_evidence(tmp_path / "trials.jsonl")
    assert not interrupted
    assert all(row["seconds"] >= 0 for row in rows.values())


@pytest.mark.parametrize(("budget", "expected_trials"), [(7, 1), (8, 2)])
async def test_parallel_trials_hold_request_ceilings_and_release_unused_capacity(
    monkeypatch,
    tmp_path,
    budget,
    expected_trials,
):
    prepare_run(monkeypatch, tmp_path, ["vendor/a", "vendor/b"], ["two_npc_two_beat"], budget)
    active = 0
    executed = []

    async def run(case, scenario, trace, config, owner):
        nonlocal active
        active += 1
        await asyncio.sleep(0)
        assert active == 1
        await trace.generate_with_tools("system", [], [], config.model)
        executed.append(config.model)
        active -= 1
        return {}, []

    monkeypatch.setattr(dialogue_suite, "run_case", run)
    await asyncio.wait_for(dialogue_suite.main(), 5)
    assert len(executed) == expected_trials
    ledger = RequestLedger(tmp_path / "ledger.jsonl")
    assert ledger.spent == expected_trials
    assert not ledger.interrupted()


async def test_parallel_dry_run_remains_offline_and_declares_free_request_limit(
    monkeypatch,
    capsys,
):
    def forbidden(*args, **kwargs):
        raise AssertionError("No provider or database access during preparation")

    monkeypatch.setattr("socket.socket.connect", forbidden)
    monkeypatch.setattr("sys.argv", ["suite", "--dry-run"])
    await dialogue_suite.main()
    plan = json.loads(capsys.readouterr().out)
    assert plan["execution"] == {
        "workers": "one-per-selected-model",
        "free_requests_per_minute": 20,
        "free_model_suffix": ":free",
        "session_affinity": "implicit",
    }


async def test_cli_automatically_shares_one_free_limiter_for_dm_and_actor_calls(
    monkeypatch,
    tmp_path,
):
    from dialogue_limits import FreeRequestLimiter

    models = ["vendor/a:free", "vendor/b:free", "vendor/c", "vendor/d"]
    prepare_run(monkeypatch, tmp_path, models, ["npc_speaks", "actor_en"], 48, runs=6)
    now = 0.0

    async def sleep(seconds):
        nonlocal now
        now += seconds
        await asyncio.sleep(0)

    limiter = FreeRequestLimiter(clock=lambda: now, sleep=sleep)
    factory = Mock(return_value=limiter)
    monkeypatch.setattr(dialogue_execution, "FreeRequestLimiter", factory)

    async def run(case, scenario, trace, config, owner):
        if case == "actor_en":
            await trace.generate("system", [], config.model)
        else:
            await trace.generate_with_tools("system", [], [], config.model)
        return {}, []

    monkeypatch.setattr(dialogue_suite, "run_case", run)
    await asyncio.wait_for(dialogue_suite.main(), 5)
    factory.assert_called_once_with()
    attempts = RequestLedger(tmp_path / "ledger.jsonl").results()
    assert len(attempts) == 48
    assert sum(row.rate_limit_wait_seconds for row in attempts) >= 60
    assert {row.probe for row in attempts if row.model.endswith(":free")} == {
        "npc_speaks:dm",
        "actor_en:actor",
    }
    assert all(
        row.rate_limit_wait_seconds == 0 for row in attempts if not row.model.endswith(":free")
    )


async def test_provider_429_finishes_inflight_requests_but_starts_no_followups(
    monkeypatch,
    tmp_path,
):
    prepare_run(monkeypatch, tmp_path, ["vendor/a", "vendor/b"], ["two_npc_two_beat"], 14)
    both_started = asyncio.Event()
    a_failed = asyncio.Event()
    starts = []

    class RateLimitError(Exception):
        status_code = 429

    async def generation(owner, model, **kwargs):
        provider = AsyncMock()

        async def dm(**request):
            starts.append(model)
            if len(starts) == 2:
                both_started.set()
            await both_started.wait()
            if model == "vendor/a":
                a_failed.set()
                raise RateLimitError()
            await a_failed.wait()
            return AgentResponse("The scene waits.")

        provider.generate_with_tools.side_effect = dm
        return provider, ModelConfig("openrouter", model, 60000)

    async def run(case, scenario, trace, config, owner):
        await trace.generate_with_tools("system", [], [], config.model)
        await trace.generate("actor", [], config.model)
        return {}, []

    monkeypatch.setattr(dialogue_suite, "resolve_eval_generation", generation)
    monkeypatch.setattr(dialogue_suite, "run_case", run)
    await asyncio.wait_for(dialogue_suite.main(), 5)
    ledger = RequestLedger(tmp_path / "ledger.jsonl")
    assert sorted(starts) == ["vendor/a", "vendor/b"]
    assert ledger.spent == 2 and not ledger.interrupted()
    assert all(row.probe.endswith(":dm") for row in ledger.results())
    rows, interrupted = dialogue_suite.read_evidence(tmp_path / "trials.jsonl")
    assert not interrupted
    assert all(row["trial_status"] == "provider_paused" for row in rows.values())
