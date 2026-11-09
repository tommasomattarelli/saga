from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import select

from app.memory.document_contracts import SummaryPayload
from app.memory.job_contracts import MemoryJobManifest
from app.models.memory_batch import MemoryBatch, MemoryBatchTurn
from app.models.memory_document import MemoryState, MemorySummary
from app.models.memory_generation import MemoryGeneration
from app.models.memory_job import MemoryJob, MemoryJobAttempt
from tests.integration.memory.storage_support import HistoryFixture


async def generation(
    f: HistoryFixture,
    batch: MemoryBatch,
    *,
    role: str = "batch",
    previous_checkpoint_id: UUID | None = None,
) -> MemoryGeneration:
    state = MemoryState(
        id=uuid4(), campaign_id=f.campaign.id, policy_id=f.policy.id, context_epoch=0
    )
    sources = tuple(
        (
            await f.session.scalars(
                select(MemoryBatchTurn.turn_id)
                .where(MemoryBatchTurn.batch_id == batch.id)
                .order_by(MemoryBatchTurn.ordinal)
            )
        ).all()
    )
    manifest = MemoryJobManifest(
        instruction_text="Keep the source outcomes.",
        instruction_version="test-v1",
        source_turn_ids=sources,
        source_hash=batch.manifest_hash,
        language="en",
    )
    job_id, attempt_id = uuid4(), uuid4()
    job = MemoryJob(
        id=job_id,
        campaign_id=f.campaign.id,
        policy_id=f.policy.id,
        batch_id=batch.id,
        memory_state_id=state.id,
        context_epoch=0,
        kind="global" if role == "global" else "batch",
        previous_checkpoint_id=previous_checkpoint_id,
        logical_key=sha256(f"{role}:{batch.id}:{previous_checkpoint_id}".encode()).hexdigest(),
        manifest=manifest,
        manifest_hash=sha256(manifest.model_dump_json().encode()).hexdigest(),
        producer_version="test-v1",
        prompt_version="test-v1",
        state="succeeded",
        attempt_count=1,
        retry_cycle=0,
        cycle_attempt_count=1,
        activation_state="detached",
    )
    attempt = MemoryJobAttempt(
        id=attempt_id,
        job_id=job_id,
        campaign_id=f.campaign.id,
        attempt_number=1,
        retry_cycle=0,
        state="succeeded",
        claim_token=uuid4(),
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )
    result = MemoryGeneration(
        id=uuid4(),
        campaign_id=f.campaign.id,
        policy_id=f.policy.id,
        batch_id=batch.id,
        job_id=job_id,
        attempt_id=attempt_id,
        role=role,
        provider="local",
        model="test-model",
    )
    f.session.add_all([state, job, attempt, result])
    await f.session.flush()
    return result


async def summary(f: HistoryFixture, batch: MemoryBatch) -> MemorySummary:
    produced = await generation(f, batch)
    document = MemorySummary(
        campaign_id=f.campaign.id,
        policy_id=f.policy.id,
        batch_id=batch.id,
        payload=SummaryPayload(text="The party found a clue."),
        generation_id=produced.id,
    )
    f.session.add(document)
    await f.session.commit()
    return document
