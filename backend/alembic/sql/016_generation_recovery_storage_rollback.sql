DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM memory_jobs
        WHERE execution_identity IS NOT NULL OR execution_identity_hash IS NOT NULL
           OR execution_identity_version IS NOT NULL OR terminal_at IS NOT NULL
           OR state = 'manual_retry_required'
    ) OR EXISTS (
        SELECT 1 FROM memory_generations
        WHERE send_number IS NOT NULL OR send_kind IS NOT NULL
           OR request_identity_hash IS NOT NULL OR format_mode IS NOT NULL
           OR status IS NOT NULL
           OR raw_candidate IS NOT NULL OR raw_candidate_hash IS NOT NULL
           OR diagnostics IS NOT NULL OR normalization IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'Cannot downgrade memory recovery storage while durable recovery data exists.';
    END IF;
END
$$;

CREATE OR REPLACE FUNCTION saga_memory_job_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    batch_predecessor uuid;
    checkpoint_batch uuid;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF ROW(NEW.id, NEW.campaign_id, NEW.policy_id, NEW.batch_id, NEW.memory_state_id,
               NEW.context_epoch, NEW.kind, NEW.previous_checkpoint_id, NEW.logical_key,
               NEW.manifest, NEW.manifest_hash, NEW.producer_version, NEW.prompt_version)
           IS DISTINCT FROM
           ROW(OLD.id, OLD.campaign_id, OLD.policy_id, OLD.batch_id, OLD.memory_state_id,
               OLD.context_epoch, OLD.kind, OLD.previous_checkpoint_id, OLD.logical_key,
               OLD.manifest, OLD.manifest_hash, OLD.producer_version, OLD.prompt_version) THEN
            RAISE EXCEPTION 'Memory job identity and input are immutable.' USING ERRCODE = '23514';
        END IF;
        IF NEW.attempt_count < OLD.attempt_count OR NEW.retry_cycle < OLD.retry_cycle THEN
            RAISE EXCEPTION 'Memory job attempt counters cannot decrease.' USING ERRCODE = '23514';
        END IF;
    END IF;
    SELECT previous_batch_id INTO batch_predecessor
    FROM memory_batches
    WHERE id = NEW.batch_id AND campaign_id = NEW.campaign_id AND policy_id = NEW.policy_id;
    IF NEW.kind = 'batch' AND NEW.previous_checkpoint_id IS NOT NULL THEN
        RAISE EXCEPTION 'Batch jobs cannot name a global checkpoint predecessor.' USING ERRCODE = '23514';
    END IF;
    IF NEW.kind = 'global' THEN
        SELECT batch_id INTO checkpoint_batch
        FROM memory_global_checkpoints
        WHERE id = NEW.previous_checkpoint_id
          AND campaign_id = NEW.campaign_id
          AND policy_id = NEW.policy_id;
        IF checkpoint_batch IS DISTINCT FROM batch_predecessor THEN
            RAISE EXCEPTION 'Global jobs must follow the checkpoint for the batch predecessor.' USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END
$$;

CREATE OR REPLACE FUNCTION saga_memory_generation_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF NOT EXISTS (SELECT 1 FROM campaigns WHERE id = OLD.campaign_id) THEN RETURN OLD; END IF;
        RAISE EXCEPTION 'Memory generation provenance is immutable.' USING ERRCODE = '23514';
    END IF;
    IF to_jsonb(NEW) - 'updated_at' IS DISTINCT FROM to_jsonb(OLD) - 'updated_at' THEN
        RAISE EXCEPTION 'Memory generation provenance is immutable.' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

DROP TRIGGER memory_generation_guard ON memory_generations;

CREATE TRIGGER memory_generation_guard BEFORE UPDATE OR DELETE ON memory_generations
FOR EACH ROW EXECUTE FUNCTION saga_memory_generation_guard();

ALTER TABLE memory_jobs
    DROP CONSTRAINT ck_memory_jobs_terminal_time,
    DROP CONSTRAINT ck_memory_jobs_terminal_identity,
    DROP CONSTRAINT ck_memory_jobs_terminal_state,
    DROP CONSTRAINT ck_memory_jobs_execution_identity;

ALTER TABLE memory_jobs
    DROP COLUMN terminal_at,
    DROP COLUMN execution_identity_version,
    DROP COLUMN execution_identity_hash,
    DROP COLUMN execution_identity;

ALTER TABLE memory_jobs
    DROP CONSTRAINT ck_memory_jobs_state;

ALTER TABLE memory_jobs
    ALTER COLUMN state TYPE varchar(16);

ALTER TABLE memory_jobs
    ADD CONSTRAINT ck_memory_jobs_state
    CHECK (state IN ('queued', 'running', 'retry_wait', 'blocked', 'exhausted', 'succeeded'));

ALTER TABLE memory_generations
    DROP CONSTRAINT uq_memory_generations_job_role_send,
    DROP CONSTRAINT ck_memory_generations_send_number,
    DROP CONSTRAINT ck_memory_generations_send_identity,
    DROP CONSTRAINT ck_memory_generations_send_kind,
    DROP CONSTRAINT ck_memory_generations_request_identity_hash,
    DROP CONSTRAINT ck_memory_generations_format_mode,
    DROP CONSTRAINT ck_memory_generations_status,
    DROP CONSTRAINT ck_memory_generations_reservation_outcome,
    DROP CONSTRAINT ck_memory_generations_candidate_hash,
    DROP CONSTRAINT ck_memory_generations_candidate_hash_required,
    DROP CONSTRAINT ck_memory_generations_candidate_hash_matches,
    DROP CONSTRAINT ck_memory_generations_diagnostics,
    DROP CONSTRAINT ck_memory_generations_normalization;

ALTER TABLE memory_generations
    DROP COLUMN normalization,
    DROP COLUMN diagnostics,
    DROP COLUMN raw_candidate_hash,
    DROP COLUMN raw_candidate,
    DROP COLUMN status,
    DROP COLUMN format_mode,
    DROP COLUMN request_identity_hash,
    DROP COLUMN send_kind,
    DROP COLUMN send_number;
