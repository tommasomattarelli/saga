from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import raiseload

from app import dependencies
from app.models.base import Base
from app.models.campaign import Campaign
from app.models.history import HistoryContinuation, MemoryPolicy
from app.models.memory_batch import MemoryBatch, MemoryBatchTurn
from app.models.memory_document import MemoryGlobalCheckpoint, MemoryState, MemorySummary
from app.models.memory_fact import MemoryFact, MemoryFactSource
from app.models.memory_generation import MemoryGeneration
from app.models.memory_job import MemoryJob, MemoryJobAttempt
from app.models.save import Save
from app.models.turn import Turn
from app.models.turn_operation import TurnOperation
from app.schemas.campaign_export import (
    CampaignExport,
    ExportBatchTurn,
    ExportCampaign,
    ExportContinuation,
    ExportFactSource,
    ExportGeneration,
    ExportGlobalCheckpoint,
    ExportJob,
    ExportJobAttempt,
    ExportMemoryBatch,
    ExportMemoryFact,
    ExportMemoryPolicy,
    ExportMemoryState,
    ExportMemorySummary,
    ExportSave,
    ExportTurn,
    ExportTurnOperation,
)
from app.services.export_validation import validate_campaign_export


class CampaignExportNotFoundError(ValueError):
    pass


def _safe_error(error: str | None) -> str | None:
    if error is None:
        return None
    if error in {
        "Memory generation requires a configuration update.",
        "Memory generation was interrupted.",
        "Memory generation did not produce a valid result.",
    }:
        return error
    return "Memory generation did not complete successfully."


async def _load_rows[Row: Base](
    db: AsyncSession,
    model: type[Row],
    campaign_id: UUID,
) -> list[Row]:
    statement = (
        select(model).where(model.__table__.c.campaign_id == campaign_id).options(raiseload("*"))
    )
    ordering = (Turn.turn_number, Turn.id) if model is Turn else model.__mapper__.primary_key
    return list(await db.scalars(statement.order_by(*ordering)))


def _records[Record: BaseModel](schema: type[Record], rows: Sequence[object]) -> list[Record]:
    return [schema.model_validate(row) for row in rows]


def _job_record(job: MemoryJob) -> ExportJob:
    return ExportJob(
        id=job.id,
        campaign_id=job.campaign_id,
        created_at=job.created_at,
        updated_at=job.updated_at,
        policy_id=job.policy_id,
        batch_id=job.batch_id,
        memory_state_id=job.memory_state_id,
        context_epoch=job.context_epoch,
        kind=job.kind,
        previous_checkpoint_id=job.previous_checkpoint_id,
        source_turn_ids=list(job.manifest.source_turn_ids),
        source_hash=job.manifest.source_hash,
        instruction_version=job.manifest.instruction_version,
        language=job.manifest.language,
        manifest_hash=job.manifest_hash,
        producer_version=job.producer_version,
        prompt_version=job.prompt_version,
        state=job.state,
        attempt_count=job.attempt_count,
        retry_cycle=job.retry_cycle,
        cycle_attempt_count=job.cycle_attempt_count,
        last_error=_safe_error(job.last_error),
        activation_state=job.activation_state,
    )


async def _snapshot(db: AsyncSession, campaign_id: UUID, owner_id: UUID) -> CampaignExport:
    campaign = await db.scalar(
        select(Campaign)
        .where(Campaign.id == campaign_id, Campaign.user_id == owner_id)
        .options(raiseload("*"))
    )
    if campaign is None:
        raise CampaignExportNotFoundError("Campaign not found")
    exported_at = await db.scalar(select(func.transaction_timestamp()))
    assert isinstance(exported_at, datetime)
    turns = await _load_rows(db, Turn, campaign_id)
    operations = await _load_rows(db, TurnOperation, campaign_id)
    continuations = await _load_rows(db, HistoryContinuation, campaign_id)
    saves = await _load_rows(db, Save, campaign_id)
    policies = await _load_rows(db, MemoryPolicy, campaign_id)
    states = await _load_rows(db, MemoryState, campaign_id)
    batches = await _load_rows(db, MemoryBatch, campaign_id)
    memberships = await _load_rows(db, MemoryBatchTurn, campaign_id)
    summaries = await _load_rows(db, MemorySummary, campaign_id)
    checkpoints = await _load_rows(db, MemoryGlobalCheckpoint, campaign_id)
    facts = await _load_rows(db, MemoryFact, campaign_id)
    sources = await _load_rows(db, MemoryFactSource, campaign_id)
    generations = await _load_rows(db, MemoryGeneration, campaign_id)
    jobs = await _load_rows(db, MemoryJob, campaign_id)
    attempts = await _load_rows(db, MemoryJobAttempt, campaign_id)
    return CampaignExport(
        format_version=1,
        exported_at=exported_at,
        campaign=ExportCampaign.model_validate(campaign),
        turns=_records(ExportTurn, turns),
        turn_operations=_records(ExportTurnOperation, operations),
        continuations=_records(ExportContinuation, continuations),
        saves=_records(ExportSave, saves),
        memory_policies=_records(ExportMemoryPolicy, policies),
        memory_states=_records(ExportMemoryState, states),
        memory_batches=_records(ExportMemoryBatch, batches),
        batch_turns=_records(ExportBatchTurn, memberships),
        memory_summaries=_records(ExportMemorySummary, summaries),
        global_checkpoints=_records(ExportGlobalCheckpoint, checkpoints),
        memory_facts=_records(ExportMemoryFact, facts),
        fact_sources=_records(ExportFactSource, sources),
        generations=_records(ExportGeneration, generations),
        jobs=[_job_record(job) for job in jobs],
        job_attempts=[
            ExportJobAttempt.model_validate(attempt).model_copy(
                update={"error": _safe_error(attempt.error)}
            )
            for attempt in attempts
        ],
    )


async def build_campaign_export(campaign_id: UUID, owner_id: UUID) -> CampaignExport:
    # Authentication has already queried its session, so the archive needs a fresh snapshot.
    async with dependencies.async_session() as db, db.begin():
        await db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        archive = await _snapshot(db, campaign_id, owner_id)
    validate_campaign_export(archive)
    return archive
