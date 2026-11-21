import asyncio

import pytest

from app.memory import job_lifecycle


async def test_worker_start_is_idempotent_and_stop_cancels_active_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered = asyncio.Event()
    cancelled = asyncio.Event()
    calls = 0

    async def worker(stop: asyncio.Event, wake: asyncio.Event) -> None:
        nonlocal calls
        calls += 1
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(job_lifecycle, "run_memory_worker", worker)
    job_lifecycle.start_memory_worker()
    job_lifecycle.start_memory_worker()
    await asyncio.wait_for(entered.wait(), 1)
    job_lifecycle.wake_memory_worker()
    await job_lifecycle.stop_memory_worker()
    assert calls == 1 and cancelled.is_set()
    assert job_lifecycle._task is None


async def test_worker_can_restart_with_fresh_events(monkeypatch: pytest.MonkeyPatch) -> None:
    stopped = []

    async def worker(stop: asyncio.Event, wake: asyncio.Event) -> None:
        stopped.append(stop.is_set())
        await stop.wait()

    monkeypatch.setattr(job_lifecycle, "run_memory_worker", worker)
    for _ in range(2):
        job_lifecycle.start_memory_worker()
        await asyncio.sleep(0)
        await job_lifecycle.stop_memory_worker()
    assert stopped == [False, False]
