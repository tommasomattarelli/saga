import asyncio
from unittest.mock import AsyncMock

import pytest
from eval.dialogue.requests import SuiteProvider
from eval.support.ledger import RequestLedger


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def time(self):
        return self.now

    async def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds
        await asyncio.sleep(0)


async def test_free_limit_is_shared_across_model_ids_and_paid_bypasses_it():
    from eval.dialogue.limits import FreeRequestLimiter

    clock = Clock()
    limiter = FreeRequestLimiter(clock=clock.time, sleep=clock.sleep)
    for index in range(20):
        assert await limiter.wait(f"vendor/model-{index % 2}:free") == 0
    assert await limiter.wait("vendor/paid") == 0
    assert clock.sleeps == []
    assert await limiter.wait("vendor/other:free") == 60
    assert clock.sleeps == [60]


async def test_simultaneous_free_calls_obey_the_rolling_window():
    from eval.dialogue.limits import FreeRequestLimiter

    clock = Clock()
    limiter = FreeRequestLimiter(clock=clock.time, sleep=clock.sleep)
    starts = []

    async def call(index):
        await limiter.wait(f"vendor/{index % 2}:free")
        starts.append(clock.time())

    await asyncio.gather(*(call(index) for index in range(45)))
    assert starts == [0] * 20 + [60] * 20 + [120] * 5


async def test_cancelled_free_waiter_does_not_block_paid_or_consume_a_slot():
    from eval.dialogue.limits import FreeRequestLimiter

    clock = Clock()
    sleeping = asyncio.Event()

    async def sleep(seconds):
        sleeping.set()
        await asyncio.Event().wait()

    limiter = FreeRequestLimiter(clock=clock.time, sleep=sleep)
    for _ in range(20):
        await limiter.wait("vendor/free:free")
    waiting = asyncio.create_task(limiter.wait("vendor/free:free"))
    await sleeping.wait()
    assert await asyncio.wait_for(limiter.wait("vendor/paid"), 1) == 0
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    clock.now = 60
    assert await asyncio.wait_for(limiter.wait("vendor/free:free"), 1) == 0


async def test_cancelled_rate_wait_is_not_a_reserved_or_sent_request(tmp_path):
    sleeping = asyncio.Event()

    async def wait(model):
        sleeping.set()
        await asyncio.Event().wait()

    provider = AsyncMock()
    limiter = AsyncMock()
    limiter.wait.side_effect = wait
    ledger = RequestLedger(tmp_path / "ledger.jsonl", budget=1)
    trace = SuiteProvider(
        provider,
        ledger,
        key="trial",
        case="actor",
        model="m:free",
        run=0,
        commit="commit",
        ceiling=1,
        limiter=limiter,
    )
    call = asyncio.create_task(trace.generate("system", [], "m:free"))
    await sleeping.wait()
    call.cancel()
    with pytest.raises(asyncio.CancelledError):
        await call
    assert trace.count == ledger.spent == 0
    assert not ledger.interrupted()
    provider.generate.assert_not_awaited()


async def test_cancelled_inflight_request_stays_interrupted_for_owner_review(tmp_path):
    started = asyncio.Event()

    async def generate(**kwargs):
        started.set()
        await asyncio.Event().wait()

    provider = AsyncMock()
    provider.generate.side_effect = generate
    ledger = RequestLedger(tmp_path / "ledger.jsonl", budget=1)
    trace = SuiteProvider(
        provider,
        ledger,
        key="trial",
        case="actor",
        model="m:free",
        run=0,
        commit="commit",
        ceiling=1,
    )
    call = asyncio.create_task(trace.generate("system", [], "m:free"))
    await started.wait()
    call.cancel()
    with pytest.raises(asyncio.CancelledError):
        await call
    replay = RequestLedger(ledger.path)
    assert replay.spent == 1
    assert replay.interrupted() == ["trial|request-0"]
    assert replay.results() == []


async def test_rate_limit_wait_is_reported_separately_from_request_latency(tmp_path):
    from eval.dialogue.limits import FreeRequestLimiter

    clock = Clock()
    limiter = FreeRequestLimiter(clock=clock.time, sleep=clock.sleep)
    for _ in range(20):
        await limiter.wait("other:free")
    provider = AsyncMock()
    provider.generate.return_value = "ok"
    ledger = RequestLedger(tmp_path / "ledger.jsonl", budget=1)
    trace = SuiteProvider(
        provider,
        ledger,
        key="trial",
        case="actor",
        model="m:free",
        run=0,
        commit="commit",
        ceiling=1,
        limiter=limiter,
    )
    await trace.generate("system", [], "m:free")
    attempt = ledger.results()[0]
    assert attempt.rate_limit_wait_seconds == 60
    assert attempt.seconds < 1
