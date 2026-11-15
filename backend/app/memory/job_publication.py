import hashlib
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.generation_execution_ledger import GenerationSendKind
from app.ai.response_validation import ResponseValidationError, validate_response
from app.memory.batch_input import load_batch_input
from app.memory.document_contracts import GlobalPayload
from app.memory.generation_receipts import decode_receipt
from app.memory.job_activation import activate_artifact
from app.memory.job_claims import JobClaim, load_claim
from app.memory.job_contracts import MemoryGenerationRequestIdentitySnapshot
from app.memory.job_identity import config_from_identity
from app.memory.job_requests import restore_job_requests
from app.memory.producer_contracts import (
    FactsPayload,
    MemoryOutputError,
    ResolvedFact,
    SummaryPayload,
    validate_facts,
)
from app.memory.producer_prompts import PreparedMemoryRequest, response_contract
from app.memory.producers import build_generation_request
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
    role: Literal["summary", "facts", "global"]
    send_number: int


class PublicationLeaseExpiredError(Exception):
    pass


async def _validated_payload(
    db: AsyncSession,
    job: MemoryJob,
    output: JobOutput,
    request: PreparedMemoryRequest,
) -> tuple[MemoryGeneration, object, tuple[ResolvedFact, ...]]:
    identity = job.execution_identity
    if identity is None or output.send_number < 1:
        raise MemoryOutputError("Memory generation identity is unavailable.")
    frozen = identity.result_identities.get(output.role)
    if frozen is None:
        raise MemoryOutputError("Memory generation role is not frozen.")

    base = build_generation_request(
        request,
        config_from_identity(frozen),
        session_affinity=frozen.session_affinity,
    )
    if base.identity.digest != frozen.request_identity_hash:
        raise MemoryOutputError("Memory generation request identity changed.")

    generation = await db.scalar(
        select(MemoryGeneration)
        .where(
            MemoryGeneration.job_id == job.id,
            MemoryGeneration.campaign_id == job.campaign_id,
            MemoryGeneration.policy_id == job.policy_id,
            MemoryGeneration.batch_id == job.batch_id,
            MemoryGeneration.role == output.role,
            MemoryGeneration.send_number == output.send_number,
        )
        .with_for_update()
    )
    if (
        generation is None
        or generation.status != "valid"
        or generation.receipt is None
        or generation.request_identity_hash is None
        or generation.request_identity_snapshot is None
        or generation.send_kind is None
        or generation.format_mode is None
    ):
        raise MemoryOutputError("A persisted valid memory receipt is unavailable.")

    try:
        stored_request = MemoryGenerationRequestIdentitySnapshot.model_validate_json(
            generation.request_identity_snapshot
        )
        send_kind = GenerationSendKind(generation.send_kind)
        receipt = decode_receipt(generation.receipt, generation.raw_candidate)
    except ValueError:
        raise MemoryOutputError("A persisted memory receipt is invalid.") from None
    fixed_fields = frozen.model_dump(mode="json", exclude={"request_identity_hash", "format_mode"})
    stored_fields = stored_request.model_dump(mode="json", exclude={"format_mode"})
    if (
        stored_request.digest != generation.request_identity_hash
        or stored_request.snapshot_json != generation.request_identity_snapshot
        or stored_fields != fixed_fields
        or stored_request.format_mode != generation.format_mode
        or generation.provider != frozen.provider
        or generation.model != frozen.model
        or (
            send_kind is GenerationSendKind.INITIAL
            and (
                generation.request_identity_hash != frozen.request_identity_hash
                or stored_request.format_mode != frozen.format_mode
            )
        )
        or (
            generation.raw_candidate is not None
            and generation.raw_candidate_hash
            != hashlib.sha256(generation.raw_candidate.encode()).hexdigest()
        )
    ):
        raise MemoryOutputError("Memory generation provenance does not match its frozen identity.")
    if (
        receipt.text is None
        or receipt.refusal is not None
        or receipt.blocked_reason is not None
        or (receipt.finish_reason or "").upper()
        in {
            "CONTENT_FILTER",
            "LENGTH",
            "MAX_TOKENS",
            "SAFETY",
            "RECITATION",
            "BLOCKLIST",
            "PROHIBITED_CONTENT",
            "SPII",
            "LANGUAGE",
        }
    ):
        raise MemoryOutputError("A persisted valid memory receipt is not publishable.")
    try:
        payload = validate_response(receipt.text, response_contract(request.kind)).model
        resolved = (
            validate_facts(payload, request.source, request.facts_policy)
            if isinstance(payload, FactsPayload)
            else ()
        )
    except (ResponseValidationError, ValueError, TypeError):
        raise MemoryOutputError("A persisted valid memory receipt no longer validates.") from None
    return generation, payload, resolved


async def publish_job(db: AsyncSession, claim: JobClaim, outputs: tuple[JobOutput, ...]) -> bool:
    loaded = await load_claim(db, claim)
    if loaded is None:
        return False
    job, attempt, _ = loaded
    roles = ("summary", "facts") if job.kind == "batch" else ("global",)
    if (
        job.execution_contract_version != 1
        or job.execution_identity is None
        or job.execution_identity_hash is None
        or job.execution_identity_version is None
    ):
        raise MemoryOutputError("This memory job has no supported execution identity.")
    try:
        job.execution_identity.verify(job.execution_identity_version, job.execution_identity_hash)
    except ValueError:
        raise MemoryOutputError("This memory job has no supported execution identity.") from None
    if (
        len(outputs) != len(roles)
        or tuple(output.role for output in outputs) != roles
        or set(job.execution_identity.result_identities) != set(roles)
    ):
        raise MemoryOutputError("Memory generation output roles are incomplete.")

    source = await load_batch_input(db, job.campaign_id, job.batch_id)
    policy = await db.get(MemoryPolicy, job.policy_id)
    if policy is None:
        raise ValueError("Memory job policy is missing.")
    requests = restore_job_requests(job.manifest, source, claim.policy.facts)
    if tuple(request.kind for request in requests) != roles:
        raise MemoryOutputError("Frozen memory requests do not match job roles.")

    generations = []
    payloads = []
    resolved_facts: list[tuple[ResolvedFact, ...]] = []
    for output, request in zip(outputs, requests, strict=True):
        generation, payload, resolved = await _validated_payload(db, job, output, request)
        generations.append(generation)
        payloads.append(payload)
        resolved_facts.append(resolved)

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
        await _store_facts(db, job, generations[1], resolved_facts[1])
        activated = (
            await activate_artifact(db, campaign, state, batch)
            if state.context_epoch == job.context_epoch
            else False
        )
    else:
        global_payload = payloads[0]
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
    job.terminal_at = finished_at
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
