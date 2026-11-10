from __future__ import annotations

import asyncio
from collections import Counter
from types import SimpleNamespace
from uuid import uuid4

import pytest
from eval.memory.runner import EvaluationPausedError, run_plan
from eval.support.ledger import Attempt, RequestLedger

from app.ai.router import ModelConfig
from app.memory.producer_contracts import MemoryOutputError
from tests.unit.eval._memory_runner_support import memory_plan


def _install_fake_affinity(monkeypatch: pytest.MonkeyPatch) -> None:
    import eval.memory.runner as runner

    def clone(provider, session_id):
        return SimpleNamespace(
            client=SimpleNamespace(default_headers={"x-session-id": session_id})
        )

    monkeypatch.setattr(runner, "provider_with_session", clone)


@pytest.mark.asyncio
async def test_model_workers_overlap_advance_independently_and_serialize_each_lane(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from eval.support import live_calls

    from app.ai import generation_context as context
    from app.memory import producers

    _install_fake_affinity(monkeypatch)
    models = ["vendor/slow", "vendor/fast", "vendor/third"]
    plan = memory_plan(models=models)
    slow_started = asyncio.Event()
    third_started = asyncio.Event()
    fast_advanced = asyncio.Event()
    release_slow = asyncio.Event()
    active: Counter[str] = Counter()
    maximum: Counter[str] = Counter()
    combined_maximum = 0

    async def resolve(_owner, model, *, allow_paid):
        return object(), ModelConfig("openrouter", model, plan.output_cap)

    async def generate(_request):
        nonlocal combined_maximum
        _provider, config = await context.resolve_generation_context()
        model = config.model
        active[model] += 1
        maximum[model] = max(maximum[model], active[model])
        combined_maximum = max(combined_maximum, sum(active.values()))
        try:
            if model == models[0]:
                slow_started.set()
                await release_slow.wait()
            elif model == models[1]:
                await slow_started.wait()
                if maximum[model] == 1 and not fast_advanced.is_set():
                    await third_started.wait()
                if not fast_advanced.is_set():
                    fast_advanced.set()
            else:
                await slow_started.wait()
                third_started.set()
            raise MemoryOutputError("intentional offline contract stop")
        finally:
            active[model] -= 1

    monkeypatch.setattr(live_calls, "resolve_eval_generation", resolve)
    monkeypatch.setattr(producers, "generate_memory", generate)
    running = asyncio.create_task(run_plan(plan, tmp_path, uuid4(), authorized=True))
    await fast_advanced.wait()
    assert not running.done()
    assert active[models[0]] == 1
    assert combined_maximum == 3
    assert maximum == Counter({model: 1 for model in models})
    release_slow.set()
    await running
    ledger = RequestLedger(tmp_path / "requests.jsonl")
    assert ledger.spent == plan.call_budget
    assert not ledger.interrupted()


@pytest.mark.asyncio
async def test_fatal_provider_error_drains_inflight_sibling_without_followups(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from eval.support import live_calls

    from app.ai import generation_context as context
    from app.memory import producers

    _install_fake_affinity(monkeypatch)
    models = ["vendor/fatal", "vendor/sibling"]
    plan = memory_plan(models=models)
    sibling_started = asyncio.Event()
    release_sibling = asyncio.Event()
    fatal_recorded = asyncio.Event()
    calls: Counter[str] = Counter()
    original_record = RequestLedger.record

    def record(ledger: RequestLedger, attempt) -> None:
        original_record(ledger, attempt)
        if attempt.correlation.get("fatal_provider_error"):
            fatal_recorded.set()

    async def resolve(_owner, model, *, allow_paid):
        return object(), ModelConfig("openrouter", model, plan.output_cap)

    async def generate(_request):
        _provider, config = await context.resolve_generation_context()
        model = config.model
        calls[model] += 1
        if model == models[0]:
            await sibling_started.wait()
            raise RuntimeError("private offline provider detail")
        sibling_started.set()
        await release_sibling.wait()
        raise MemoryOutputError("offline contract failure")

    monkeypatch.setattr(RequestLedger, "record", record)
    monkeypatch.setattr(live_calls, "resolve_eval_generation", resolve)
    monkeypatch.setattr(producers, "generate_memory", generate)
    running = asyncio.create_task(run_plan(plan, tmp_path, uuid4(), authorized=True))
    await fatal_recorded.wait()
    assert not running.done()
    assert calls == Counter({models[0]: 1, models[1]: 1})
    release_sibling.set()
    with pytest.raises(EvaluationPausedError, match="check authorization"):
        await running
    ledger = RequestLedger(tmp_path / "requests.jsonl")
    assert ledger.spent == 2
    assert len(ledger.results()) == 2
    assert not ledger.interrupted()
    assert calls == Counter({models[0]: 1, models[1]: 1})


@pytest.mark.asyncio
async def test_unexpected_worker_error_keeps_lock_until_inflight_sibling_finishes(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from eval.support import live_calls

    from app.ai import generation_context as context
    from app.memory import producers

    _install_fake_affinity(monkeypatch)
    models = ["vendor/failing", "vendor/sibling"]
    plan = memory_plan(models=models)
    sibling_started = asyncio.Event()
    release_sibling = asyncio.Event()
    recording_failed = asyncio.Event()
    sibling_finished = asyncio.Event()
    calls: Counter[str] = Counter()
    lock_held_at_sibling_finish = False
    original_record = RequestLedger.record

    def record(ledger: RequestLedger, attempt: Attempt) -> None:
        if attempt.model == models[0]:
            recording_failed.set()
            raise OSError("offline evidence write failed")
        original_record(ledger, attempt)

    async def resolve(_owner, model, *, allow_paid):
        return object(), ModelConfig("openrouter", model, plan.output_cap)

    async def generate(_request: object) -> None:
        nonlocal lock_held_at_sibling_finish
        _, config = await context.resolve_generation_context()
        calls[config.model] += 1
        if config.model == models[0]:
            await sibling_started.wait()
        else:
            sibling_started.set()
            await release_sibling.wait()
            lock_held_at_sibling_finish = (tmp_path / ".run.lock").exists()
            sibling_finished.set()
        raise MemoryOutputError("offline contract failure")

    monkeypatch.setattr(RequestLedger, "record", record)
    monkeypatch.setattr(live_calls, "resolve_eval_generation", resolve)
    monkeypatch.setattr(producers, "generate_memory", generate)
    running = asyncio.create_task(run_plan(plan, tmp_path, uuid4(), authorized=True))
    await recording_failed.wait()
    await asyncio.sleep(0)
    release_sibling.set()
    with pytest.raises(OSError, match="evidence write"):
        await running
    await sibling_finished.wait()
    assert lock_held_at_sibling_finish
    assert calls == Counter({models[0]: 1, models[1]: 1})
    assert not (tmp_path / ".run.lock").exists()
