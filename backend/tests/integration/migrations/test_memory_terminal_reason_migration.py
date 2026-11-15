from json import loads
from uuid import uuid4

from app.ai.generation_contracts import (
    FormatMode,
    GenerationIdentity,
    OutputLimit,
)
from app.memory.job_contracts import MemoryGenerationIdentitySnapshot, MemoryJobExecutionIdentity
from tests.integration.migrations.migration_db import DisposableDatabase
from tests.integration.migrations.test_generation_recovery_storage_migration import (
    JOB_ID,
    _seed_legacy_job,
)


def _execution_identity(job_id: str) -> tuple[str, str]:
    base = GenerationIdentity(
        format_version=1,
        role="global",
        logical_result_id=f"{job_id}:global",
        initial_prefix_hash="a" * 64,
        contract_name="migration-global",
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
    result_identity = MemoryGenerationIdentitySnapshot.model_validate(
        {**loads(base.snapshot_json), "request_identity_hash": base.digest}
    )
    identity = MemoryJobExecutionIdentity(
        result_identities={"global": result_identity},
        max_sends_per_result=3,
    )
    return identity.model_dump_json(), identity.digest(1)


async def test_018_adds_reason_without_backfilling_legacy_exhaustion() -> None:
    async with DisposableDatabase() as database:
        await database.upgrade("015_gen_format_prefs")
        await _seed_legacy_job(database)
        await database.execute(
            "UPDATE memory_jobs SET state='exhausted' WHERE id=:id",
            {"id": JOB_ID},
        )
        await database.upgrade("016_gen_recovery_storage")

        await database.upgrade("017_gen_ledger_contracts")
        assert await database.version() == "017_gen_ledger_contracts"
        await database.upgrade("018_memory_terminal_reason")

        assert await database.version() == "018_memory_terminal_reason"
        assert await database.fetch_one(
            "SELECT state, terminal_reason FROM memory_jobs WHERE id=:id", {"id": JOB_ID}
        ) == ("exhausted", None)
        await database.require_model_schema()


async def test_018_migration_roundtrips_without_reason_data() -> None:
    async with DisposableDatabase() as database:
        await database.upgrade("017_gen_ledger_contracts")

        await database.upgrade("018_memory_terminal_reason")
        await database.downgrade("017_gen_ledger_contracts")

        assert await database.version() == "017_gen_ledger_contracts"
        assert await database.fetch_one("SELECT to_regclass('public.memory_jobs')") == (
            "memory_jobs",
        )
        assert (
            await database.fetch_all(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='memory_jobs' AND column_name='terminal_reason'"
            )
            == []
        )


async def test_018_downgrade_refuses_to_discard_terminal_reason() -> None:
    async with DisposableDatabase() as database:
        await database.upgrade("017_gen_ledger_contracts")
        await _seed_legacy_job(database)
        await database.upgrade("018_memory_terminal_reason")
        job_id = str(uuid4())
        identity_json, identity_hash = _execution_identity(job_id)
        await database.execute(
            "INSERT INTO memory_jobs "
            "(id, campaign_id, policy_id, batch_id, memory_state_id, context_epoch, kind, "
            "logical_key, manifest, manifest_hash, producer_version, prompt_version, state, "
            "attempt_count, retry_cycle, cycle_attempt_count, activation_state, "
            "execution_identity, execution_identity_hash, execution_identity_version, "
            "execution_contract_version) "
            "SELECT :id, campaign_id, policy_id, batch_id, memory_state_id, context_epoch, "
            "'global', :key, manifest, :manifest_hash, producer_version, prompt_version, "
            "'queued', 0, 0, 0, 'pending', CAST(:identity AS jsonb), :identity_hash, 1, 1 "
            "FROM memory_jobs WHERE id=:source_id",
            {
                "id": job_id,
                "key": "7" * 64,
                "manifest_hash": "f" * 64,
                "identity": identity_json,
                "identity_hash": identity_hash,
                "source_id": JOB_ID,
            },
        )
        await database.execute(
            "UPDATE memory_jobs SET state='exhausted', terminal_at=clock_timestamp(), "
            "terminal_reason='required_result_send_budget_exhausted' WHERE id=:id",
            {"id": job_id},
        )

        result = await database.run_alembic("downgrade", "017_gen_ledger_contracts")

        assert result.returncode != 0
        assert "terminal reason" in result.stderr.lower()
        assert await database.version() == "018_memory_terminal_reason"
