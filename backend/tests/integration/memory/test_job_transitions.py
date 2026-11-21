import pytest
from sqlalchemy import select

from app.memory.batch_input import load_batch_input
from app.memory.job_claims import JobClaim, claim_job
from app.memory.job_coverage import load_coverage
from app.memory.job_identity import config_from_identity
from app.memory.job_publication import JobOutput, publish_job
from app.memory.job_requests import restore_job_requests
from app.memory.job_scheduler import coordinate_memory
from app.models.memory_job import MemoryJob, MemoryJobAttempt
from tests.integration.memory.job_support import (
    _durable_generation,
    configure_local_generation,
    outputs_for,
    persist_durable_generations,
)
from tests.integration.memory.storage_support import HistoryFixture
from tests.integration.memory.test_job_scheduler import active_history


async def reserve_outputs(
    f: HistoryFixture,
    claim: JobClaim,
    kind: str,
) -> tuple[JobOutput, ...]:
    job = await f.session.get(MemoryJob, claim.job_id)
    assert job is not None
    assert job.execution_identity is not None
    attempt = await f.session.get(MemoryJobAttempt, claim.attempt_id)
    assert attempt is not None
    source = await load_batch_input(f.session, job.campaign_id, job.batch_id)
    requests = restore_job_requests(job.manifest, source, claim.policy.facts)
    raw = {
        "summary": '{"text":"Intermediate."}',
        "facts": '{"facts":[]}',
        "global": '{"story_so_far":"Remote history.","open_threads":[],"relationships":[],"resolved_threads":[]}',
    }
    generations = tuple(
        _durable_generation(
            job,
            attempt,
            request,
            config_from_identity(job.execution_identity.result_identities[request.kind]),
            raw[request.kind],
        )
        for request in requests
    )
    await persist_durable_generations(f.session, generations)
    await f.session.commit()
    return outputs_for(generations)


@pytest.mark.parametrize("global_first", [False, True])
async def test_disjoint_raw_and_global_completion_preserve_both_cursors(
    history_fixture: HistoryFixture,
    global_first: bool,
) -> None:
    f = history_fixture
    await configure_local_generation(f)
    state = await active_history(f, 6)
    (first_id,) = await coordinate_memory(f.session, f.campaign.id)
    await f.session.commit()
    first = await claim_job(f.session, f.campaign.id, first_id)
    assert first is not None
    first_outputs = await reserve_outputs(f, first, "batch")
    assert await publish_job(f.session, first, first_outputs)
    await f.session.commit()
    first_batch = state.last_compacted_batch_id
    ids = await coordinate_memory(f.session, f.campaign.id)
    await f.session.commit()
    assert len(ids) == 2
    pending = []
    for job_id in ids:
        job = await f.session.get(MemoryJob, job_id)
        assert job is not None
        claim = await claim_job(f.session, f.campaign.id, job.id)
        assert claim is not None
        parts = await reserve_outputs(f, claim, job.kind)
        pending.append((job.kind, claim, parts))
    pending.sort(key=lambda item: (item[0] == "global") != global_first)
    for kind, claim, parts in pending:
        other_cursor = (
            state.last_compacted_batch_id if kind == "global" else state.global_checkpoint_id
        )
        assert await publish_job(f.session, claim, parts)
        await f.session.commit()
        assert other_cursor == (
            state.last_compacted_batch_id if kind == "global" else state.global_checkpoint_id
        )
    assert state.last_compacted_batch_id != first_batch
    assert state.global_checkpoint_id is not None and state.revision == 3
    coverage = await load_coverage(f.session, f.campaign, state, f.policy.payload)
    assert (len(coverage.raw_turn_ids), coverage.intermediates, coverage.global_batches) == (
        2,
        1,
        1,
    )
    assert len(list(await f.session.scalars(select(MemoryJob)))) == 3
