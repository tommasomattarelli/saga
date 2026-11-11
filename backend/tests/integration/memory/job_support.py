from datetime import UTC, datetime
from uuid import uuid4

from app.memory.job_contracts import MemoryJobManifest
from app.models.memory_batch import MemoryBatch
from app.models.memory_document import MemoryState
from app.models.memory_generation import MemoryGeneration
from app.models.memory_job import MemoryJob, MemoryJobAttempt
from app.models.turn import Turn
from tests.integration.memory.storage_support import HistoryFixture
from tests.integration.memory.test_batch_storage import batch


async def job_sources(f: HistoryFixture) -> tuple[list[Turn], MemoryBatch, MemoryState]:
    first = await f.turn()
    second = await f.turn(first)
    item = await batch(f, [first, second])
    state = MemoryState(
        id=uuid4(), campaign_id=f.campaign.id, policy_id=f.policy.id, context_epoch=0
    )
    f.session.add(state)
    await f.session.commit()
    return [first, second], item, state


def new_job(
    f: HistoryFixture,
    turns: list[Turn],
    item: MemoryBatch,
    state: MemoryState,
    *,
    key: str = "c" * 64,
) -> MemoryJob:
    return MemoryJob(
        id=uuid4(),
        campaign_id=f.campaign.id,
        policy_id=f.policy.id,
        batch_id=item.id,
        memory_state_id=state.id,
        context_epoch=0,
        kind="batch",
        logical_key=key,
        manifest=MemoryJobManifest(
            instruction_text="Summarize the original batch.",
            instruction_version="test-v1",
            source_turn_ids=tuple(turn.id for turn in turns),
            source_hash="a" * 64,
            language="en",
        ),
        manifest_hash="d" * 64,
        producer_version="test-v1",
        prompt_version="test-v1",
        state="queued",
        attempt_count=0,
        retry_cycle=0,
        cycle_attempt_count=0,
        activation_state="pending",
    )


def new_attempt(job: MemoryJob, number: int, *, cycle: int = 0) -> MemoryJobAttempt:
    return MemoryJobAttempt(
        id=uuid4(),
        job_id=job.id,
        campaign_id=job.campaign_id,
        attempt_number=number,
        retry_cycle=cycle,
        state="failed",
        claim_token=uuid4(),
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        error="Temporary failure.",
    )


def new_generation(job: MemoryJob, attempt: MemoryJobAttempt) -> MemoryGeneration:
    return MemoryGeneration(
        id=uuid4(),
        job_id=job.id,
        attempt_id=attempt.id,
        campaign_id=job.campaign_id,
        policy_id=job.policy_id,
        batch_id=job.batch_id,
        role="batch",
        provider="local",
        model="test-model",
    )
