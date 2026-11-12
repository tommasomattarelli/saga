from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import dependencies
from app.models.memory_batch import MemoryBatch
from app.models.memory_job import MemoryJob
from app.models.turn import Turn


class OperationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    source_operation_id: UUID
    operation_id: UUID
    turn_id: UUID


class PersistedTurnEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    source_turn_id: UUID
    turn_id: UUID
    request_id: UUID
    head_turn_id: UUID
    context_epoch: int
    operations: tuple[OperationEvidence, ...]
    status: Literal["verified", "invalid"] = "verified"
    diagnostic: str | None = None


class BatchEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    batch_id: UUID
    job_id: UUID
    source_turn_ids: tuple[UUID, ...]


async def ordered_batches(db: AsyncSession, campaign_id: UUID) -> list[MemoryBatch]:
    return list(
        await db.scalars(
            select(MemoryBatch)
            .join(Turn, Turn.id == MemoryBatch.source_head_turn_id)
            .where(MemoryBatch.campaign_id == campaign_id)
            .order_by(Turn.history_depth)
        )
    )


async def ordered_batch_ids(campaign_id: UUID) -> tuple[UUID, ...]:
    async with dependencies.async_session() as db:
        return tuple(batch.id for batch in await ordered_batches(db, campaign_id))


async def collect_batch_evidence(
    campaign_id: UUID, turns: tuple[PersistedTurnEvidence, ...]
) -> tuple[BatchEvidence, ...]:
    from app.memory.batch_input import load_batch_input
    from app.models.memory_batch import MemoryBatchTurn

    turn_ids = {turn.turn_id for turn in turns}
    async with dependencies.async_session() as db:
        evidence: list[BatchEvidence] = []
        for batch in await ordered_batches(db, campaign_id):
            source = await load_batch_input(db, campaign_id, batch.id)
            job = await db.scalar(
                select(MemoryJob).where(
                    MemoryJob.batch_id == batch.id,
                    MemoryJob.campaign_id == campaign_id,
                    MemoryJob.kind == "batch",
                )
            )
            if job is None:
                raise AssertionError(f"batch {batch.id} has no persisted specialist job")
            member_ids = tuple(
                await db.scalars(
                    select(MemoryBatchTurn.turn_id)
                    .where(MemoryBatchTurn.batch_id == batch.id)
                    .order_by(MemoryBatchTurn.ordinal)
                )
            )
            if not set(member_ids) <= turn_ids:
                raise AssertionError(f"batch {batch.id} includes a turn outside the replay")
            if (
                member_ids != tuple(turn.turn_id for turn in source.turns)
                or member_ids != job.manifest.source_turn_ids
            ):
                raise ValueError("persisted batch order differs from the evaluated job sources")
            evidence.append(
                BatchEvidence(
                    batch_id=batch.id,
                    job_id=job.id,
                    source_turn_ids=member_ids,
                )
            )
        return tuple(evidence)
