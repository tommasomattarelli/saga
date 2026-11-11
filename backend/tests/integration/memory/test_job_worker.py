import asyncio

import pytest
from sqlalchemy import select

from app.memory.job_worker import run_memory_pass, run_memory_worker
from app.models.memory_document import MemorySummary
from app.models.memory_job import MemoryJob
from tests.integration.memory.storage_support import HistoryFixture
from tests.integration.memory.test_job_execution import ControlledProvider
from tests.integration.memory.test_job_scheduler import active_history


async def test_real_pipeline_cascades_original_batches_into_global(
    history_fixture: HistoryFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.ai.router import ModelConfig

    f = history_fixture
    state = await active_history(f, 8)
    provider = ControlledProvider([])
    calls: list[tuple[str, str]] = []

    async def generate(system_prompt, messages, **kwargs):
        prompt = messages[0]["content"]
        calls.append((system_prompt, prompt))
        if '"story_so_far"' in system_prompt and '"resolved_threads"' in system_prompt:
            assert '"previous"' in prompt
            assert '"player_action":"Action"' in prompt
            return '{"story_so_far":"The first batch.","open_threads":[],"relationships":[],"resolved_threads":[]}'
        if '"facts"' in system_prompt:
            return '{"facts":[]}'
        return '{"text":"Intermediate memory."}'

    async def resolve(owner):
        return provider, ModelConfig(provider="local", model="test-model", max_tokens=500)

    monkeypatch.setattr(provider, "generate", generate)
    monkeypatch.setattr("app.memory.job_execution.get_user_generation", resolve)
    for _ in range(5):
        await run_memory_pass(f.campaign.id)
    await f.session.refresh(state)
    assert state.global_checkpoint_id is not None
    jobs = list(await f.session.scalars(select(MemoryJob)))
    assert len([job for job in jobs if job.kind == "batch"]) == 3
    assert len([job for job in jobs if job.kind == "global"]) == 2
    assert all(job.state == "succeeded" for job in jobs)
    assert len(calls) == 8
    assert len(list(await f.session.scalars(select(MemorySummary)))) == 3
    saved_cursors = state.global_checkpoint_id, state.last_compacted_batch_id
    assert await run_memory_pass(f.campaign.id) == 0
    await f.session.refresh(state)
    assert saved_cursors == (state.global_checkpoint_id, state.last_compacted_batch_id)


async def test_worker_with_no_eligible_campaigns_stops_without_provider_work(
    history_fixture: HistoryFixture,
) -> None:
    stop, wake = asyncio.Event(), asyncio.Event()
    task = asyncio.create_task(run_memory_worker(stop, wake))
    stop.set()
    await asyncio.wait_for(task, timeout=2)
