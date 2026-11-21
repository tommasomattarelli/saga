from sqlalchemy import select

from app.ai.credentials import resolve_generation
from app.memory.batch_input import load_batch_input
from app.memory.job_claims import retry_job
from app.memory.job_requests import restore_job_requests
from app.memory.job_scheduler import coordinate_memory
from app.memory.producers import build_generation_request
from app.models.memory_generation import MemoryGeneration
from app.models.memory_job import MemoryJob
from app.models.user import User
from tests.integration.memory.job_support import job_sources, new_job
from tests.integration.memory.storage_support import HistoryFixture
from tests.integration.memory.test_job_scheduler import active_history


async def test_scheduler_creates_jobs_with_identity_from_restored_requests(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    user = await f.session.get(User, f.campaign.user_id)
    assert user is not None
    user.generation_provider = "local"
    user.generation_model = "test-model"
    user.generation_local_endpoint = "ollama"
    await active_history(f, 5)

    job_ids = await coordinate_memory(f.session, f.campaign.id)
    await f.session.commit()
    jobs = list(await f.session.scalars(select(MemoryJob).where(MemoryJob.id.in_(job_ids))))
    assert len(jobs) == 1
    job = jobs[0]
    assert job.execution_contract_version == 1
    assert job.execution_identity is not None

    source = await load_batch_input(f.session, job.campaign_id, job.batch_id)
    requests = restore_job_requests(job.manifest, source, f.policy.payload.facts)
    config, _, _ = resolve_generation(user)
    for prepared in requests:
        frozen = job.execution_identity.result_identities[prepared.kind]
        request = build_generation_request(
            prepared, config, session_affinity=frozen.session_affinity
        )
        assert frozen.request_identity_hash == request.identity.digest
        assert frozen.logical_result_id == request.identity.logical_result_id


async def test_missing_configuration_blocks_new_job_until_explicit_one_time_binding(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    await active_history(f, 5)
    (job_id,) = await coordinate_memory(f.session, f.campaign.id)
    await f.session.commit()
    job = await f.session.get(MemoryJob, job_id)
    assert job is not None
    assert job.state == "blocked"
    assert job.execution_contract_version == 1
    assert job.execution_identity is None
    assert job.attempt_count == 0
    assert await f.session.scalar(select(MemoryGeneration.id)) is None

    user = await f.session.get(User, f.campaign.user_id)
    assert user is not None
    user.generation_provider = "local"
    user.generation_model = "test-model"
    user.generation_local_endpoint = "ollama"
    assert await retry_job(f.session, f.campaign.id, job.id)
    await f.session.commit()
    identity_hash = job.execution_identity_hash
    assert job.state == "queued"
    assert job.execution_identity is not None
    assert job.attempt_count == 0
    assert not await retry_job(f.session, f.campaign.id, job.id)
    await f.session.commit()

    job.state = "blocked"
    user.generation_model = "changed-model"
    await f.session.commit()
    assert not await retry_job(f.session, f.campaign.id, job.id)
    await f.session.commit()
    assert job.execution_identity_hash == identity_hash

    user.generation_model = "test-model"
    await f.session.commit()
    assert await retry_job(f.session, f.campaign.id, job.id)
    await f.session.commit()
    assert job.execution_identity_hash == identity_hash


async def test_legacy_blocked_job_cannot_bind_during_retry(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    turns, batch, state = await job_sources(f)
    job = new_job(f, turns, batch, state)
    job.state = "blocked"
    f.session.add(job)
    await f.session.commit()

    assert not await retry_job(f.session, f.campaign.id, job.id)
    await f.session.commit()
    assert job.execution_contract_version is None
    assert job.execution_identity is None
