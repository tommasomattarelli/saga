from json import loads
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.ai.generation_contracts import (
    FormatMode,
    GenerationIdentity,
    OutputLimit,
    RawGenerationReceipt,
)
from app.memory.generation_receipts import encode_receipt
from app.memory.job_contracts import MemoryGenerationIdentitySnapshot, MemoryJobExecutionIdentity
from tests.integration.migrations.migration_db import DisposableDatabase
from tests.integration.migrations.test_generation_recovery_storage_migration import (
    GENERATION_ID,
    JOB_ID,
    _seed_legacy_job,
)


async def test_017_preserves_legacy_unmarked_rows_and_matches_models() -> None:
    async with DisposableDatabase() as database:
        await database.upgrade("015_gen_format_prefs")
        await _seed_legacy_job(database)
        await database.upgrade("016_gen_recovery_storage")
        await database.upgrade()

        assert await database.version() == "017_gen_ledger_contracts"
        await database.require_model_schema()
        assert await database.fetch_one(
            "SELECT execution_contract_version, execution_identity FROM memory_jobs WHERE id=:id",
            {"id": JOB_ID},
        ) == (None, None)


async def test_017_downgrade_removes_generation_ledger_helpers() -> None:
    async with DisposableDatabase() as database:
        await database.upgrade()

        result = await database.run_alembic("downgrade", "016_gen_recovery_storage")

        assert result.returncode == 0, result.stderr
        assert await database.fetch_one(
            "SELECT to_regprocedure('public.saga_memory_validate_job_identity(jsonb)')"
        ) == (None,)
        assert await database.fetch_one(
            "SELECT to_regprocedure('public.saga_memory_job_identity_digest(jsonb,integer)')"
        ) == (None,)
        assert await database.fetch_one(
            "SELECT to_regprocedure('public.saga_memory_canonical_json(jsonb)')"
        ) == (None,)
        assert await database.fetch_one(
            "SELECT to_regprocedure('public.saga_memory_ascii_json_string(text)')"
        ) == (None,)


async def test_017_downgrade_refuses_to_discard_receipt_or_contract_marker() -> None:
    async with DisposableDatabase() as database:
        await database.upgrade()
        await _seed_legacy_job(database)
        await database.execute(
            "INSERT INTO memory_jobs "
            "(id, campaign_id, policy_id, batch_id, memory_state_id, context_epoch, kind, "
            "logical_key, manifest, manifest_hash, producer_version, prompt_version, state, "
            "attempt_count, retry_cycle, cycle_attempt_count, activation_state, "
            "execution_contract_version) "
            "SELECT '88888888-8888-8888-8888-888888888888', campaign_id, policy_id, batch_id, "
            "memory_state_id, context_epoch, kind, :key, manifest, :manifest_hash, "
            "producer_version, prompt_version, 'blocked', 0, 0, 0, 'pending', 1 "
            "FROM memory_jobs WHERE id=:id",
            {"id": JOB_ID, "key": "9" * 64, "manifest_hash": "e" * 64},
        )

        result = await database.run_alembic("downgrade", "016_gen_recovery_storage")

        assert result.returncode != 0
        assert await database.version() == "017_gen_ledger_contracts"


async def test_017_legacy_generation_cannot_gain_receipt_before_typed_reservation() -> None:
    async with DisposableDatabase() as database:
        await database.upgrade()
        await _seed_legacy_job(database)

        with pytest.raises(IntegrityError):
            await database.execute(
                "UPDATE memory_generations SET status='stop', receipt=:receipt WHERE id=:id",
                {
                    "id": GENERATION_ID,
                    "receipt": '{"encoding_version":1,"candidate_in_column":false,"receipt":{}}',
                },
            )


async def test_017_downgrade_refuses_receipt_evidence_without_contract_marker() -> None:
    async with DisposableDatabase() as database:
        await database.upgrade()
        await _seed_legacy_job(database)

        job_id = str(uuid4())
        attempt_id = str(uuid4())
        generation_id = str(uuid4())
        claim_token = str(uuid4())
        base = GenerationIdentity(
            format_version=1,
            role="summary",
            logical_result_id=f"{job_id}:summary",
            initial_prefix_hash="a" * 64,
            contract_name="migration-summary",
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
        generation_identity = MemoryGenerationIdentitySnapshot.model_validate(
            {
                **loads(base.snapshot_json),
                "request_identity_hash": base.digest,
            }
        )
        execution_identity = MemoryJobExecutionIdentity(
            result_identities={"summary": generation_identity},
            max_sends_per_result=3,
        )
        identity_json = execution_identity.model_dump_json()
        identity_hash = execution_identity.digest(1)
        receipt_json, candidate = encode_receipt(RawGenerationReceipt(text="persisted receipt"))
        request_snapshot = base.snapshot_json

        await database.execute(
            "INSERT INTO memory_jobs "
            "(id, campaign_id, policy_id, batch_id, memory_state_id, context_epoch, kind, "
            "logical_key, manifest, manifest_hash, producer_version, prompt_version, state, "
            "attempt_count, retry_cycle, cycle_attempt_count, claim_token, lease_expires_at, "
            "activation_state, execution_identity, execution_identity_hash, "
            "execution_identity_version) "
            "SELECT :new_id, campaign_id, policy_id, batch_id, memory_state_id, context_epoch, "
            "kind, :key, manifest, :manifest_hash, producer_version, prompt_version, 'running', "
            "1, 0, 1, :claim, now() + interval '5 minutes', activation_state, "
            "CAST(:identity AS jsonb), :identity_hash, 1 FROM memory_jobs WHERE id=:source_id",
            {
                "new_id": job_id,
                "key": "7" * 64,
                "manifest_hash": "f" * 64,
                "claim": claim_token,
                "identity": identity_json,
                "identity_hash": identity_hash,
                "source_id": JOB_ID,
            },
        )
        await database.execute(
            "INSERT INTO memory_job_attempts "
            "(id, job_id, campaign_id, attempt_number, retry_cycle, state, claim_token, "
            "started_at) SELECT :id, :job, campaign_id, 1, 0, 'started', :claim, now() "
            "FROM memory_jobs WHERE id=:job",
            {"id": attempt_id, "job": job_id, "claim": claim_token},
        )
        await database.execute(
            "INSERT INTO memory_generations "
            "(id, job_id, attempt_id, campaign_id, policy_id, batch_id, role, provider, model, "
            "send_number, send_kind, request_identity_hash, request_identity_snapshot, format_mode) "
            "SELECT :id, id, :attempt, campaign_id, policy_id, batch_id, 'summary', 'local', "
            "'test-model', 1, 'initial', :request_hash, :request_snapshot, 'strict_native' "
            "FROM memory_jobs WHERE id=:job",
            {
                "id": generation_id,
                "attempt": attempt_id,
                "request_hash": base.digest,
                "request_snapshot": request_snapshot,
                "job": job_id,
            },
        )
        await database.execute(
            "UPDATE memory_generations SET status='invalid', receipt=:receipt, "
            "raw_candidate=:candidate WHERE id=:id",
            {"receipt": receipt_json, "candidate": candidate, "id": generation_id},
        )
        assert await database.fetch_one(
            "SELECT execution_contract_version FROM memory_jobs WHERE id=:id",
            {"id": job_id},
        ) == (None,)

        result = await database.run_alembic("downgrade", "016_gen_recovery_storage")

        assert result.returncode != 0
        assert "send evidence" in result.stderr
