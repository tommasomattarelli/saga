from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.batch_input import load_batch_input
from app.memory.job_activation import activate_artifact
from app.memory.job_claims import JobClaim, load_claim
from app.memory.job_requests import restore_job_requests
from app.memory.producer_contracts import (
    FactsPayload,
    MemoryOutputError,
    ResolvedFact,
    SummaryPayload,
    validate_facts,
)
from app.models.campaign import Campaign
from app.models.history import MemoryPolicy
from app.models.memory_batch import MemoryBatch
from app.models.memory_document import MemoryGlobalCheckpoint, MemoryState, MemorySummary
from app.models.memory_fact import MemoryFact, MemoryFactSource
from app.models.memory_generation import MemoryGeneration
from app.models.memory_job import MemoryJob
from app.models.source_embedding import EmbeddingSourceType


@dataclass(frozen=True)
class JobOutput:
    generation_id: UUID
    raw: str


class PublicationLeaseExpiredError(Exception):
    pass


async def publish_job(db: AsyncSession, claim: JobClaim, outputs: tuple[JobOutput, ...]) -> bool:
    loaded = await load_claim(db, claim)
    if loaded is None:
        return False
    job, attempt, _ = loaded
    roles = ("summary", "facts") if job.kind == "batch" else ("global",)
    if len(outputs) != len(roles):
        raise MemoryOutputError("Memory generation output roles are incomplete.")
    source = await load_batch_input(db, job.campaign_id, job.batch_id)
    policy = await db.get(MemoryPolicy, job.policy_id)
    if policy is None:
        raise ValueError("Memory job policy is missing.")
    requests = restore_job_requests(job.manifest, source, claim.policy.facts)
    if tuple(request.kind for request in requests) != roles:
        raise MemoryOutputError("Frozen memory requests do not match job roles.")

    generations: list[MemoryGeneration] = []
    payloads = []
    for output, role, request in zip(outputs, roles, requests, strict=True):
        generation = await db.scalar(
            select(MemoryGeneration).where(
                MemoryGeneration.id == output.generation_id,
                MemoryGeneration.job_id == job.id,
                MemoryGeneration.attempt_id == attempt.id,
                MemoryGeneration.campaign_id == job.campaign_id,
                MemoryGeneration.batch_id == job.batch_id,
                MemoryGeneration.policy_id == job.policy_id,
                MemoryGeneration.role == role,
            )
        )
        if generation is None:
            raise MemoryOutputError("Memory generation provenance does not match this attempt.")
        payload = request.validate_output(output.raw)
        if isinstance(payload, FactsPayload):
            validate_facts(payload, source, claim.policy.facts)
        generations.append(generation)
        payloads.append(payload)

    campaign = await db.get(Campaign, job.campaign_id, populate_existing=True)
    batch = await db.get(MemoryBatch, job.batch_id, populate_existing=True)
    state = await db.get(MemoryState, job.memory_state_id, populate_existing=True)
    if campaign is None or batch is None or state is None:
        raise ValueError("Memory job publication scope is missing.")
    if job.kind == "batch":
        summary_payload, facts_payload = payloads
        assert isinstance(summary_payload, SummaryPayload)
        assert isinstance(facts_payload, FactsPayload)
        db.add(
            MemorySummary(
                campaign_id=job.campaign_id,
                policy_id=job.policy_id,
                batch_id=job.batch_id,
                payload=summary_payload,
                generation_id=generations[0].id,
            )
        )
        resolved = validate_facts(facts_payload, source, claim.policy.facts)
        await _store_facts(db, job, generations[1], resolved)
        activated = (
            await activate_artifact(db, campaign, state, batch)
            if state.context_epoch == job.context_epoch
            else False
        )
    else:
        global_payload = payloads[0]
        from app.memory.document_contracts import GlobalPayload

        assert isinstance(global_payload, GlobalPayload)
        checkpoint = MemoryGlobalCheckpoint(
            campaign_id=job.campaign_id,
            policy_id=job.policy_id,
            batch_id=job.batch_id,
            previous_checkpoint_id=job.previous_checkpoint_id,
            payload=global_payload,
            generation_id=generations[0].id,
        )
        db.add(checkpoint)
        await db.flush()
        activated = (
            await activate_artifact(db, campaign, state, batch, checkpoint)
            if state.context_epoch == job.context_epoch
            else False
        )

    finished_at = await db.scalar(
        select(func.clock_timestamp()).where(
            MemoryJob.id == job.id,
            MemoryJob.claim_token == claim.token,
            MemoryJob.state == "running",
            MemoryJob.lease_expires_at > func.clock_timestamp(),
        )
    )
    if finished_at is None:
        raise PublicationLeaseExpiredError("The memory claim expired before publication.")
    job.state = "succeeded"
    job.claim_token = None
    job.lease_expires_at = None
    job.activation_state = "active" if activated else "detached"
    attempt.state = "succeeded"
    attempt.finished_at = finished_at
    attempt.error = None
    return True


async def _store_facts(
    db: AsyncSession,
    job: MemoryJob,
    generation: MemoryGeneration,
    facts: tuple[ResolvedFact, ...],
) -> None:
    from app.memory.embedding_queue import enqueue_source_embedding

    for ordinal, fact in enumerate(facts, start=1):
        row = MemoryFact(
            campaign_id=job.campaign_id,
            content=fact.content,
            batch_id=job.batch_id,
            policy_id=job.policy_id,
            ordinal=ordinal,
            category=fact.category,
            assertion_type=fact.assertion_type,
            fact_metadata=fact.metadata,
            generation_id=generation.id,
            schema_version=1,
        )
        db.add(row)
        await db.flush()
        db.add_all(
            MemoryFactSource(
                fact_id=row.id,
                turn_id=turn_id,
                batch_id=job.batch_id,
                campaign_id=job.campaign_id,
            )
            for turn_id in fact.source_turn_ids
        )
        await enqueue_source_embedding(
            db,
            campaign_id=job.campaign_id,
            source_type=EmbeddingSourceType.MEMORY_FACT,
            source_id=row.id,
            source_text=fact.content,
        )
