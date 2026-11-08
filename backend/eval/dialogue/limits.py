import asyncio
import time
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from eval.support.ledger import RequestLedger

FREE_REQUESTS_PER_MINUTE = 20


class FreeRequestLimiter:
    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._clock = clock
        self._sleep = sleep
        self._starts: deque[float] = deque()
        self._lock = asyncio.Lock()

    async def wait(self, model: str) -> float:
        if not model.endswith(":free"):
            return 0.0
        started = self._clock()
        async with self._lock:
            while True:
                now = self._clock()
                while self._starts and self._starts[0] <= now - 60:
                    self._starts.popleft()
                if len(self._starts) < FREE_REQUESTS_PER_MINUTE:
                    self._starts.append(now)
                    return now - started
                await self._sleep(60 - (now - self._starts[0]))


class TrialBudget:
    def __init__(self, ledger: RequestLedger) -> None:
        self._available = ledger.remaining
        self._active = 0
        self._condition = asyncio.Condition()

    @asynccontextmanager
    async def hold(self, ceiling: int, used: Callable[[], int]) -> AsyncIterator[bool]:
        async with self._condition:
            while self._available is not None and self._available < ceiling and self._active:
                await self._condition.wait()
            admitted = self._available is None or self._available >= ceiling
            if admitted:
                if self._available is not None:
                    self._available -= ceiling
                self._active += 1
        try:
            yield admitted
        finally:
            if admitted:
                async with self._condition:
                    if self._available is not None:
                        self._available += ceiling - used()
                    self._active -= 1
                    self._condition.notify_all()
