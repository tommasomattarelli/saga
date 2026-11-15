from json import dumps
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.memory.job_contracts import (
    MemoryGenerationIdentitySnapshot,
    MemoryGenerationRequestIdentitySnapshot,
    MemoryJobExecutionIdentity,
)
from tests.integration.memory.job_support import (
    job_sources,
    new_attempt,
    new_identity_job,
    new_job,
)
from tests.integration.memory.storage_support import HistoryFixture


async def test_current_contract_identity_binds_once_only_on_blocked_retry_transition(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    turns, item, state = await job_sources(f)
    seed, _, _, _ = await new_identity_job(f, turns, item, state, unicode_identity=True)
    job = new_job(f, turns, item, state)
    job.manifest_hash = "e" * 64
    job.state = "blocked"
    job.manifest_hash = "e" * 64
    job.execution_contract_version = 1
    f.session.add(job)
    await f.session.commit()

    assert seed.execution_identity is not None
    role_identities = {}
    for role, original in seed.execution_identity.result_identities.items():
        fields = original.model_dump(mode="json", exclude={"request_identity_hash"})
        fields["logical_result_id"] = f"{job.id}:{role}"
        request = MemoryGenerationRequestIdentitySnapshot.model_validate_json(
            dumps(fields, sort_keys=True, separators=(",", ":"))
        )
        role_identities[role] = MemoryGenerationIdentitySnapshot.model_validate_json(
            dumps(
                {**fields, "request_identity_hash": request.digest},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
    execution_identity = MemoryJobExecutionIdentity(
        result_identities=role_identities,
        max_sends_per_result=seed.execution_identity.max_sends_per_result,
    )
    identity = execution_identity.model_dump_json()
    identity_hash = execution_identity.digest(1)
    await f.session.execute(
        text(
            "UPDATE memory_jobs SET state='queued', execution_identity=CAST(:identity AS jsonb), "
            "execution_identity_hash=:hash, execution_identity_version=1 WHERE id=:id"
        ),
        {"identity": identity, "hash": identity_hash, "id": job.id},
    )
    await f.session.commit()

    with pytest.raises(IntegrityError):
        await f.session.execute(
            text("UPDATE memory_jobs SET execution_identity_hash=:hash WHERE id=:id"),
            {"hash": "c" * 64, "id": job.id},
        )
        await f.session.commit()
    await f.session.rollback()


async def test_correctly_hashed_incomplete_identity_is_rejected_on_retry(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    turns, item, state = await job_sources(f)
    seed, _, _, _ = await new_identity_job(f, turns, item, state)
    assert seed.execution_identity is not None
    job = new_job(f, turns, item, state)
    job.manifest_hash = "e" * 64
    job.state = "blocked"
    job.execution_contract_version = 1
    f.session.add(job)
    await f.session.commit()

    incomplete = seed.execution_identity.model_dump(mode="json")
    del incomplete["result_identities"]["summary"]["provider"]
    encoded = dumps(incomplete, sort_keys=True, separators=(",", ":"))
    identity_hash = await f.session.scalar(
        text("SELECT saga_memory_job_identity_digest(CAST(:identity AS jsonb), 1)"),
        {"identity": encoded},
    )
    with pytest.raises(IntegrityError):
        await f.session.execute(
            text(
                "UPDATE memory_jobs SET state='queued', execution_identity=CAST(:identity AS jsonb), "
                "execution_identity_hash=:hash, execution_identity_version=1 WHERE id=:id"
            ),
            {"identity": encoded, "hash": identity_hash, "id": job.id},
        )
        await f.session.commit()
    await f.session.rollback()


async def test_correctly_hashed_incomplete_identity_is_rejected_at_creation(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    turns, item, state = await job_sources(f)
    seed, _, _, _ = await new_identity_job(f, turns, item, state)
    assert seed.execution_identity is not None
    job = new_job(f, turns, item, state)
    job.manifest_hash = "e" * 64
    incomplete = seed.execution_identity.model_dump(mode="json")
    del incomplete["result_identities"]["summary"]["provider"]
    encoded = dumps(incomplete, sort_keys=True, separators=(",", ":"))
    identity_hash = await f.session.scalar(
        text("SELECT saga_memory_job_identity_digest(CAST(:identity AS jsonb), 1)"),
        {"identity": encoded},
    )

    with pytest.raises(IntegrityError):
        await f.session.execute(
            text(
                "INSERT INTO memory_jobs "
                "(id, campaign_id, policy_id, batch_id, memory_state_id, context_epoch, kind, "
                "logical_key, manifest, manifest_hash, producer_version, prompt_version, state, "
                "attempt_count, retry_cycle, cycle_attempt_count, activation_state, "
                "execution_identity, execution_identity_hash, execution_identity_version, "
                "execution_contract_version) "
                "VALUES (:id, :campaign, :policy, :batch, :state_id, :epoch, :kind, :key, "
                "CAST(:manifest AS jsonb), :manifest_hash, :producer, :prompt, 'blocked', "
                "0, 0, 0, 'pending', CAST(:identity AS jsonb), :hash, 1, 1)"
            ),
            {
                "id": job.id,
                "campaign": job.campaign_id,
                "policy": job.policy_id,
                "batch": job.batch_id,
                "state_id": job.memory_state_id,
                "epoch": job.context_epoch,
                "kind": job.kind,
                "key": job.logical_key,
                "manifest": job.manifest.model_dump_json(),
                "manifest_hash": job.manifest_hash,
                "producer": job.producer_version,
                "prompt": job.prompt_version,
                "identity": encoded,
                "hash": identity_hash,
            },
        )
        await f.session.commit()
    await f.session.rollback()


async def test_sql_job_identity_digest_matches_python_for_unicode_values(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    turns, item, state = await job_sources(f)
    job, _, _, _ = await new_identity_job(f, turns, item, state, unicode_identity=True)
    assert job.execution_identity is not None
    assert job.execution_identity_version is not None
    sql_hash = await f.session.scalar(
        text(
            "SELECT saga_memory_job_identity_digest(execution_identity, execution_identity_version) "
            "FROM memory_jobs WHERE id=:id"
        ),
        {"id": job.id},
    )
    assert sql_hash == job.execution_identity.digest(job.execution_identity_version)

    source = job.execution_identity.result_identities["summary"]
    fields = source.model_dump(mode="json", exclude={"request_identity_hash"})
    fields["role"] = "clé/🧙"
    fields["logical_result_id"] = "clé/🧙:résultat"
    request = MemoryGenerationRequestIdentitySnapshot.model_validate_json(
        dumps(fields, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    unicode_role = MemoryGenerationIdentitySnapshot.model_validate_json(
        dumps(
            {**fields, "request_identity_hash": request.digest},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    unicode_key_identity = MemoryJobExecutionIdentity(
        result_identities={"clé/🧙": unicode_role},
        max_sends_per_result=job.execution_identity.max_sends_per_result,
    )
    unicode_key_hash = await f.session.scalar(
        text("SELECT saga_memory_job_identity_digest(CAST(:identity AS jsonb), 1)"),
        {"identity": unicode_key_identity.model_dump_json()},
    )
    assert unicode_key_hash == unicode_key_identity.digest(1)


async def test_legacy_job_cannot_be_marked_or_bound(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    turns, item, state = await job_sources(f)
    job = new_job(f, turns, item, state)
    job.manifest_hash = "e" * 64
    f.session.add(job)
    await f.session.commit()

    with pytest.raises(IntegrityError):
        await f.session.execute(
            text("UPDATE memory_jobs SET execution_contract_version=1 WHERE id=:id"),
            {"id": job.id},
        )
        await f.session.commit()
    await f.session.rollback()


async def test_marked_unbound_job_cannot_become_executable(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    turns, item, state = await job_sources(f)
    job = new_job(f, turns, item, state)
    job.state = "blocked"
    job.execution_contract_version = 1
    f.session.add(job)
    await f.session.commit()

    with pytest.raises(IntegrityError):
        await f.session.execute(
            text("UPDATE memory_jobs SET state='queued' WHERE id=:id"),
            {"id": job.id},
        )
        await f.session.commit()
    await f.session.rollback()


async def test_sql_rejects_fabricated_job_identity_hash(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    turns, item, state = await job_sources(f)
    job = new_job(f, turns, item, state)
    job.state = "blocked"
    job.execution_contract_version = 1
    f.session.add(job)
    await f.session.commit()

    fabricated = (
        '{"result_identities":{"summary":{"role":"summary",'
        '"request_identity_hash":"' + "a" * 64 + '"}},'
        '"max_sends_per_result":3}'
    )
    with pytest.raises(IntegrityError):
        await f.session.execute(
            text(
                "UPDATE memory_jobs SET state='queued', execution_identity=CAST(:identity AS jsonb), "
                "execution_identity_hash=:hash, execution_identity_version=1 WHERE id=:id"
            ),
            {"identity": fabricated, "hash": "b" * 64, "id": job.id},
        )
        await f.session.commit()
    await f.session.rollback()


async def test_marked_unbound_job_rejects_legacy_generation_insert(
    history_fixture: HistoryFixture,
) -> None:
    f = history_fixture
    turns, item, state = await job_sources(f)
    job = new_job(f, turns, item, state)
    job.state = "blocked"
    job.execution_contract_version = 1
    attempt = new_attempt(job, 1)
    f.session.add_all([job, attempt])
    await f.session.commit()

    with pytest.raises(IntegrityError):
        await f.session.execute(
            text(
                "INSERT INTO memory_generations "
                "(id, job_id, attempt_id, campaign_id, policy_id, batch_id, role, provider, model) "
                "VALUES (:id, :job, :attempt, :campaign, :policy, :batch, 'batch', 'local', 'test')"
            ),
            {
                "id": uuid4(),
                "job": job.id,
                "attempt": attempt.id,
                "campaign": job.campaign_id,
                "policy": job.policy_id,
                "batch": job.batch_id,
            },
        )
        await f.session.commit()
    await f.session.rollback()
