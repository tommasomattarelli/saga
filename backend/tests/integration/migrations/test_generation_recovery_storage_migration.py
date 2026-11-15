import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from tests.integration.migrations.migration_db import HEAD_REVISION, DisposableDatabase
from tests.integration.migrations.test_migration_chain import _insert_campaign, _insert_user

USER_ID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
CAMPAIGN_ID = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
TURN_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
CONTINUATION_ID = "dddddddd-dddd-dddd-dddd-dddddddddddd"
POLICY_ID = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
BATCH_ID = "11111111-1111-1111-1111-111111111111"
STATE_ID = "22222222-2222-2222-2222-222222222222"
JOB_ID = "33333333-3333-3333-3333-333333333333"
ATTEMPT_ID = "44444444-4444-4444-4444-444444444444"
GENERATION_ID = "55555555-5555-5555-5555-555555555555"
MANIFEST_HASH = "a" * 64


async def _seed_legacy_job(database: DisposableDatabase) -> None:
    await _insert_user(database, USER_ID)
    await _insert_campaign(
        database,
        campaign_id=CAMPAIGN_ID,
        user_id=USER_ID,
        turn_number=1,
        world_slug="legacy-world",
        difficulty="MEDIUM",
    )
    async with database._engine().begin() as connection:
        await connection.execute(
            text(
                "INSERT INTO memory_policies "
                "(id, campaign_id, schema_version, payload, payload_hash) "
                "VALUES (:id, :campaign, 1, CAST(:payload AS jsonb), :hash)"
            ),
            {
                "id": POLICY_ID,
                "campaign": CAMPAIGN_ID,
                "payload": '{"batch_turns":1}',
                "hash": "b" * 64,
            },
        )
        await connection.execute(
            text("INSERT INTO history_continuations (id, campaign_id) VALUES (:id, :campaign)"),
            {"id": CONTINUATION_ID, "campaign": CAMPAIGN_ID},
        )
        await connection.execute(
            text(
                "INSERT INTO turns "
                "(id, campaign_id, turn_number, player_action, narration, model_used, "
                "importance_score, summarization_failed, continuation_id, history_depth) "
                "VALUES (:id, :campaign, 1, 'Open the gate.', 'The gate opens.', "
                "'legacy-model', 5, false, :continuation, 1)"
            ),
            {"id": TURN_ID, "campaign": CAMPAIGN_ID, "continuation": CONTINUATION_ID},
        )
        await connection.execute(
            text(
                "INSERT INTO memory_batches "
                "(id, campaign_id, policy_id, source_head_turn_id, manifest_hash) "
                "VALUES (:id, :campaign, :policy, :turn, :hash)"
            ),
            {
                "id": BATCH_ID,
                "campaign": CAMPAIGN_ID,
                "policy": POLICY_ID,
                "turn": TURN_ID,
                "hash": MANIFEST_HASH,
            },
        )
        await connection.execute(
            text(
                "INSERT INTO memory_batch_turns (batch_id, ordinal, campaign_id, turn_id) "
                "VALUES (:batch, 1, :campaign, :turn)"
            ),
            {"batch": BATCH_ID, "campaign": CAMPAIGN_ID, "turn": TURN_ID},
        )
        await connection.execute(
            text(
                "INSERT INTO memory_states (id, campaign_id, policy_id, context_epoch) "
                "VALUES (:id, :campaign, :policy, 0)"
            ),
            {"id": STATE_ID, "campaign": CAMPAIGN_ID, "policy": POLICY_ID},
        )
        await connection.execute(
            text(
                "INSERT INTO memory_jobs "
                "(id, campaign_id, policy_id, batch_id, memory_state_id, context_epoch, kind, "
                "logical_key, manifest, manifest_hash, producer_version, prompt_version, state, "
                "attempt_count, retry_cycle, cycle_attempt_count, activation_state) "
                "VALUES (:id, :campaign, :policy, :batch, :state, 0, 'batch', :key, "
                "CAST(:manifest AS jsonb), :hash, 'legacy-producer', 'legacy-prompt', 'queued', "
                "1, 0, 1, 'pending')"
            ),
            {
                "id": JOB_ID,
                "campaign": CAMPAIGN_ID,
                "policy": POLICY_ID,
                "batch": BATCH_ID,
                "state": STATE_ID,
                "key": "c" * 64,
                "manifest": (
                    '{"instruction_text":"legacy instructions",'
                    '"instruction_version":"legacy-v1",'
                    f'"source_turn_ids":["{TURN_ID}"],'
                    f'"source_hash":"{MANIFEST_HASH}","language":"en"}}'
                ),
                "hash": "d" * 64,
            },
        )
        await connection.execute(
            text(
                "INSERT INTO memory_job_attempts "
                "(id, job_id, campaign_id, attempt_number, retry_cycle, state, claim_token, "
                "started_at, finished_at, error) "
                "VALUES (:id, :job, :campaign, 1, 0, 'failed', "
                "'66666666-6666-6666-6666-666666666666', now(), now(), 'Legacy failure.')"
            ),
            {"id": ATTEMPT_ID, "job": JOB_ID, "campaign": CAMPAIGN_ID},
        )
        await connection.execute(
            text(
                "INSERT INTO memory_generations "
                "(id, job_id, attempt_id, campaign_id, policy_id, batch_id, role, provider, "
                "model, input_tokens, output_tokens, cost, latency_ms) "
                "VALUES (:id, :job, :attempt, :campaign, :policy, :batch, 'batch', "
                "'legacy-provider', 'legacy-model', 7, 11, 0.00000002, 30)"
            ),
            {
                "id": GENERATION_ID,
                "job": JOB_ID,
                "attempt": ATTEMPT_ID,
                "campaign": CAMPAIGN_ID,
                "policy": POLICY_ID,
                "batch": BATCH_ID,
            },
        )


async def test_fresh_upgrade_matches_models_and_adds_recovery_storage() -> None:
    async with DisposableDatabase() as database:
        await database.upgrade()

        assert await database.version() == HEAD_REVISION
        await database.require_model_schema()
        assert await database.fetch_all(
            "SELECT data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='memory_jobs' "
            "AND column_name='execution_identity'"
        ) == [("jsonb", "YES")]
        assert await database.fetch_all(
            "SELECT data_type, is_nullable FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='memory_generations' "
            "AND column_name='raw_candidate'"
        ) == [("text", "YES")]
        assert await database.fetch_all(
            "SELECT column_name, is_nullable FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='memory_generations' "
            "AND column_name IN ('format_mode', 'request_identity_hash') "
            "ORDER BY column_name"
        ) == [("format_mode", "YES"), ("request_identity_hash", "YES")]
        assert await database.fetch_all(
            "SELECT indexdef FROM pg_indexes WHERE schemaname='public' "
            "AND indexname='uq_memory_generations_job_role_send'"
        )
        assert await database.fetch_one(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='memory_generations' "
            "AND column_name='attempt_id'"
        ) == ("NO",)


async def test_upgrade_preserves_legacy_jobs_and_generations_without_backfill() -> None:
    async with DisposableDatabase() as database:
        await database.upgrade("015_gen_format_prefs")
        await _seed_legacy_job(database)
        original_job = await database.fetch_one(
            "SELECT id, campaign_id, policy_id, batch_id, manifest, manifest_hash, state "
            "FROM memory_jobs WHERE id=:id",
            {"id": JOB_ID},
        )
        original_generation = await database.fetch_one(
            "SELECT id, job_id, attempt_id, campaign_id, policy_id, batch_id, role, provider, "
            "model, input_tokens, output_tokens, cost, latency_ms "
            "FROM memory_generations WHERE id=:id",
            {"id": GENERATION_ID},
        )

        await database.upgrade()

        assert await database.version() == HEAD_REVISION
        assert await database.fetch_one(
            "SELECT id, campaign_id, policy_id, batch_id, manifest, manifest_hash, state, "
            "execution_identity, execution_identity_hash, execution_identity_version, terminal_at "
            "FROM memory_jobs WHERE id=:id",
            {"id": JOB_ID},
        ) == (*original_job, None, None, None, None)
        assert await database.fetch_one(
            "SELECT id, job_id, attempt_id, campaign_id, policy_id, batch_id, role, provider, "
            "model, input_tokens, output_tokens, cost, latency_ms, send_number, send_kind, "
            "request_identity_hash, format_mode, "
            "status, raw_candidate, raw_candidate_hash, diagnostics, normalization "
            "FROM memory_generations WHERE id=:id",
            {"id": GENERATION_ID},
        ) == (*original_generation, None, None, None, None, None, None, None, None, None)

        await database.execute(
            "UPDATE memory_jobs SET last_error='Legacy update' WHERE id=:id", {"id": JOB_ID}
        )
        await database.execute(
            "INSERT INTO memory_generations "
            "(id, job_id, attempt_id, campaign_id, policy_id, batch_id, role, provider, model) "
            "VALUES ('77777777-7777-7777-7777-777777777777', :job, :attempt, :campaign, "
            ":policy, :batch, 'batch', 'legacy-provider', 'legacy-model')",
            {
                "job": JOB_ID,
                "attempt": ATTEMPT_ID,
                "campaign": CAMPAIGN_ID,
                "policy": POLICY_ID,
                "batch": BATCH_ID,
            },
        )
        assert await database.fetch_one(
            "SELECT last_error FROM memory_jobs WHERE id=:id", {"id": JOB_ID}
        ) == ("Legacy update",)
        assert await database.fetch_one(
            "SELECT count(*) FROM memory_generations WHERE job_id=:id", {"id": JOB_ID}
        ) == (2,)
        with pytest.raises(IntegrityError):
            await database.execute(
                "DELETE FROM memory_generations WHERE id=:id", {"id": GENERATION_ID}
            )


async def test_downgrade_refuses_to_discard_execution_identity() -> None:
    async with DisposableDatabase() as database:
        await database.upgrade()
        await _seed_legacy_job(database)
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
                "identity": '{"result_identities":{"summary":{"role":"summary",'
                '"request_identity_hash":"' + "a" * 64 + '"}},'
                '"max_sends_per_result":5}',
                "identity_hash": "f" * 64,
            },
        )

        result = await database.run_alembic("downgrade", "015_gen_format_prefs")

        assert result.returncode != 0
        assert await database.version() == HEAD_REVISION
        assert await database.fetch_one(
            "SELECT execution_identity IS NOT NULL FROM memory_jobs "
            "WHERE id='88888888-8888-8888-8888-888888888888'"
        ) == (True,)
