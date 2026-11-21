import asyncio

from app.memory.job_worker import run_memory_worker

_task: asyncio.Task[None] | None = None
_stop = asyncio.Event()
_wake = asyncio.Event()


def wake_memory_worker() -> None:
    _wake.set()


def start_memory_worker() -> None:
    global _task
    if _task is not None and not _task.done():
        return
    _stop.clear()
    _wake.clear()
    _task = asyncio.create_task(run_memory_worker(_stop, _wake))


async def stop_memory_worker() -> None:
    global _task
    _stop.set()
    _wake.set()
    if _task is not None:
        _task.cancel()
        await asyncio.gather(_task, return_exceptions=True)
        _task = None
