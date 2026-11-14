import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import text

from app.ai.generation_contracts import FormatMode, GenerationIdentity, OutputLimit
from app.memory.job_contracts import (
    MemoryGenerationIdentitySnapshot,
    MemoryJobExecutionIdentity,
    MemoryJobManifest,
)
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


async def new_identity_job(
    f: HistoryFixture,
    turns: list[Turn],
    item: MemoryBatch,
    state: MemoryState,
    *,
    role: str = "summary",
) -> tuple[MemoryJob, MemoryJobAttempt, str, str]:
    job = new_job(f, turns, item, state, key=uuid4().hex + "0" * 32)
    token = uuid4()
    job.state = "running"
    job.attempt_count = 1
    job.cycle_attempt_count = 1
    job.claim_token = token
    job.lease_expires_at = datetime.now(UTC) + timedelta(minutes=5)
    attempt = new_attempt(job, 1)
    attempt.state = "started"
    attempt.finished_at = None
    attempt.error = None

    def result_snapshot(result_role: str) -> MemoryGenerationIdentitySnapshot:
        identity = GenerationIdentity(
            format_version=1,
            role=result_role,
            logical_result_id=f"{job.id}:{result_role}",
            initial_prefix_hash="a" * 64,
            contract_name=f"memory_{result_role}",
            contract_version="test-v1",
            contract_schema_hash="b" * 64,
            effective_schema_hash="c" * 64,
            wire_encoding_version="wire-v1",
            wire_schema_hash="d" * 64,
            tool_declarations_hash="e" * 64,
            contextual_validator_version="context-v1",
            provider="local",
            model="test-model",
            destination_fingerprint="f" * 64,
            output_limit=OutputLimit(configured_ceiling=1024),
            format_mode=FormatMode.STRICT_NATIVE,
            allow_json_mode_fallback=False,
            allow_prompt_only_fallback=False,
            session_affinity=None,
        )
        return MemoryGenerationIdentitySnapshot.model_validate(
            {
                **json.loads(identity.snapshot_json),
                "request_identity_hash": identity.digest,
            }
        )

    roles = ("global",) if role == "global" else ("summary", "facts")
    snapshots = {result_role: result_snapshot(result_role) for result_role in roles}
    version = 1
    execution_identity = MemoryJobExecutionIdentity(
        result_identities=snapshots,
        max_sends_per_result=5,
    )
    identity_hash = execution_identity.digest(version)
    request_identity_hash = snapshots[role].request_identity_hash
    await f.session.execute(
        text(
            "INSERT INTO memory_jobs "
            "(id, campaign_id, policy_id, batch_id, memory_state_id, context_epoch, kind, "
            "previous_checkpoint_id, logical_key, manifest, manifest_hash, producer_version, "
            "prompt_version, state, attempt_count, retry_cycle, cycle_attempt_count, "
            "claim_token, lease_expires_at, activation_state, execution_identity, "
            "execution_identity_hash, execution_identity_version) "
            "VALUES (:id, :campaign, :policy, :batch, :state_id, 0, 'batch', NULL, :key, "
            "CAST(:manifest AS jsonb), :manifest_hash, :producer, :prompt, 'running', 1, 0, 1, "
            ":claim_token, :lease, 'pending', CAST(:identity AS jsonb), :identity_hash, :version)"
        ),
        {
            "id": job.id,
            "campaign": job.campaign_id,
            "policy": job.policy_id,
            "batch": job.batch_id,
            "state_id": job.memory_state_id,
            "key": job.logical_key,
            "manifest": job.manifest.model_dump_json(),
            "manifest_hash": job.manifest_hash,
            "producer": job.producer_version,
            "prompt": job.prompt_version,
            "claim_token": token,
            "lease": job.lease_expires_at,
            "identity": execution_identity.model_dump_json(),
            "identity_hash": identity_hash,
            "version": version,
        },
    )
    await f.session.execute(
        text(
            "INSERT INTO memory_job_attempts "
            "(id, job_id, campaign_id, attempt_number, retry_cycle, state, claim_token, "
            "started_at) VALUES (:id, :job, :campaign, 1, 0, 'started', :claim_token, :started)"
        ),
        {
            "id": attempt.id,
            "job": job.id,
            "campaign": job.campaign_id,
            "claim_token": token,
            "started": attempt.started_at,
        },
    )
    await f.session.commit()
    return job, attempt, identity_hash, request_identity_hash
