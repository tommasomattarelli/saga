import asyncio
import logging
from time import monotonic
from uuid import UUID

from sqlalchemy import exists, select

from app import dependencies
from app.memory.job_claims import recover_jobs
from app.memory.job_execution import execute_job
from app.memory.job_scheduler import coordinate_memory
from app.models.campaign import Campaign
from app.models.history import MemoryPolicy
from app.models.memory_job import MemoryJob

logger = logging.getLogger(__name__)


async def run_memory_pass(campaign_id: UUID) -> int:
    async with dependencies.async_session() as db:
        await recover_jobs(db, campaign_id)
        jobs = await coordinate_memory(db, campaign_id)
        await db.commit()
    results = await asyncio.gather(*(execute_job(campaign_id, job_id) for job_id in jobs))
    async with dependencies.async_session() as db:
        await coordinate_memory(db, campaign_id)
        await db.commit()
    return sum(results)


async def _campaign_intervals() -> dict[UUID, float]:
    async with dependencies.async_session() as db:
        rows = await db.execute(
            select(Campaign.id, MemoryPolicy.payload)
            .join(
                MemoryPolicy,
                MemoryPolicy.id == Campaign.memory_policy_id,
            )
            .where(
                Campaign.active_memory_state_id.is_not(None)
                | exists(
                    select(MemoryJob.id).where(
                        MemoryJob.campaign_id == Campaign.id,
                        MemoryJob.state == "running",
                    )
                ),
            )
        )
        return {campaign_id: policy.jobs.poll_seconds for campaign_id, policy in rows}


async def _wait(stop: asyncio.Event, wake: asyncio.Event, timeout: float | None) -> None:
    tasks = [asyncio.create_task(stop.wait()), asyncio.create_task(wake.wait())]
    try:
        await asyncio.wait(tasks, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def run_memory_worker(stop: asyncio.Event, wake: asyncio.Event) -> None:
    due: dict[UUID, float] = {}
    while not stop.is_set():
        awakened = wake.is_set()
        wake.clear()
        intervals = await _campaign_intervals()
        due = {key: value for key, value in due.items() if key in intervals}
        for campaign_id, interval in intervals.items():
            if stop.is_set():
                break
            if awakened or due.get(campaign_id, 0) <= monotonic():
                try:
                    await run_memory_pass(campaign_id)
                except Exception:
                    logger.warning("The memory worker could not complete a campaign pass.")
                due[campaign_id] = monotonic() + interval
        delay = max(min(due.values()) - monotonic(), 0) if due else None
        await _wait(stop, wake, delay)
