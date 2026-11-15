import pytest
from sqlalchemy.exc import IntegrityError

from tests.integration.migrations.migration_db import DisposableDatabase
from tests.integration.migrations.test_generation_recovery_storage_migration import (
    JOB_ID,
    _seed_legacy_job,
)


@pytest.mark.parametrize(
    "execution_identity",
    [
        '{"result_identities":{"summary":{"role":"summary",'
        '"request_identity_hash":"' + "a" * 64 + '"}},"max_sends_per_result":true}',
        '{"result_identities":{"summary":{"role":"summary",'
        '"request_identity_hash":"' + "a" * 64 + '"}},"max_sends_per_result":5.0}',
        '{"result_identities":{"summary":{"role":"summary",'
        '"request_identity_hash":"' + "a" * 64 + '"}}}',
    ],
)
async def test_execution_identity_requires_a_strict_integer_send_budget(
    execution_identity: str,
) -> None:
    async with DisposableDatabase() as database:
        await database.upgrade()
        await _seed_legacy_job(database)

        with pytest.raises(IntegrityError):
            await database.execute(
                "INSERT INTO memory_jobs "
                "(id, campaign_id, policy_id, batch_id, memory_state_id, context_epoch, kind, "
                "logical_key, manifest, manifest_hash, producer_version, prompt_version, state, "
                "attempt_count, retry_cycle, cycle_attempt_count, activation_state, "
                "execution_identity, execution_identity_hash, execution_identity_version) "
                "SELECT '88888888-8888-8888-8888-888888888888', campaign_id, policy_id, batch_id, "
                "memory_state_id, context_epoch, kind, :key, manifest, :manifest_hash, "
                "producer_version, prompt_version, 'queued', 0, 0, 0, 'pending', "
                "CAST(:identity AS jsonb), :identity_hash, 1 FROM memory_jobs WHERE id=:legacy_id",
                {
                    "legacy_id": JOB_ID,
                    "key": "9" * 64,
                    "manifest_hash": "e" * 64,
                    "identity": execution_identity,
                    "identity_hash": "f" * 64,
                },
            )
