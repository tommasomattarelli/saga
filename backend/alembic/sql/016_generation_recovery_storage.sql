ALTER TABLE memory_jobs
    ADD COLUMN execution_identity jsonb,
    ADD COLUMN execution_identity_hash varchar(64),
    ADD COLUMN execution_identity_version integer,
    ADD COLUMN terminal_at timestamptz;

ALTER TABLE memory_jobs
    DROP CONSTRAINT ck_memory_jobs_state;

ALTER TABLE memory_jobs
    ALTER COLUMN state TYPE varchar(32);

ALTER TABLE memory_jobs
    ADD CONSTRAINT ck_memory_jobs_state
    CHECK (state IN ('queued', 'running', 'retry_wait', 'blocked', 'manual_retry_required',
                     'exhausted', 'succeeded'));

ALTER TABLE memory_jobs
    ADD CONSTRAINT ck_memory_jobs_execution_identity
    CHECK (
        (execution_identity IS NULL AND execution_identity_hash IS NULL
         AND execution_identity_version IS NULL)
        OR
        (execution_identity IS NOT NULL AND jsonb_typeof(execution_identity) = 'object'
         AND execution_identity_hash IS NOT NULL
         AND execution_identity_hash ~ '^[0-9a-f]{64}$'
         AND execution_identity_version IS NOT NULL AND execution_identity_version > 0
          AND jsonb_typeof(execution_identity->'result_identities') = 'object'
         AND execution_identity->'max_sends_per_result' IS NOT NULL
         AND jsonb_typeof(execution_identity->'max_sends_per_result') = 'number'
         AND execution_identity->>'max_sends_per_result' IS NOT NULL
         AND execution_identity->>'max_sends_per_result' ~ '^[1-9][0-9]*$'
          AND execution_identity->'result_identities' <> '{}'::jsonb)
    );

ALTER TABLE memory_jobs
    ADD CONSTRAINT ck_memory_jobs_terminal_state
    CHECK (terminal_at IS NULL OR state IN ('succeeded', 'exhausted'));

ALTER TABLE memory_jobs
    ADD CONSTRAINT ck_memory_jobs_terminal_identity
    CHECK (execution_identity IS NOT NULL OR terminal_at IS NULL);

ALTER TABLE memory_jobs
    ADD CONSTRAINT ck_memory_jobs_terminal_time
    CHECK (
        execution_identity IS NULL
        OR ((state IN ('succeeded', 'exhausted')) = (terminal_at IS NOT NULL))
    );

ALTER TABLE memory_generations
    ADD COLUMN send_number integer,
    ADD COLUMN send_kind text,
    ADD COLUMN request_identity_hash varchar(64),
    ADD COLUMN format_mode varchar(32),
    ADD COLUMN status text,
    ADD COLUMN raw_candidate text,
    ADD COLUMN raw_candidate_hash varchar(64),
    ADD COLUMN diagnostics jsonb,
    ADD COLUMN normalization varchar(32);

ALTER TABLE memory_generations
    ADD CONSTRAINT uq_memory_generations_job_role_send
    UNIQUE (job_id, role, send_number);

ALTER TABLE memory_generations
    ADD CONSTRAINT ck_memory_generations_send_number
    CHECK (send_number IS NULL OR send_number > 0);

ALTER TABLE memory_generations
    ADD CONSTRAINT ck_memory_generations_send_identity
    CHECK (
        (send_number IS NULL AND send_kind IS NULL AND request_identity_hash IS NULL
         AND format_mode IS NULL)
        OR (send_number IS NOT NULL AND send_kind IS NOT NULL
            AND request_identity_hash IS NOT NULL AND format_mode IS NOT NULL
            AND role <> 'batch')
    );

ALTER TABLE memory_generations
    ADD CONSTRAINT ck_memory_generations_send_kind
    CHECK (send_kind IS NULL OR btrim(send_kind) <> '');

ALTER TABLE memory_generations
    ADD CONSTRAINT ck_memory_generations_request_identity_hash
    CHECK (request_identity_hash IS NULL OR request_identity_hash ~ '^[0-9a-f]{64}$');

ALTER TABLE memory_generations
    ADD CONSTRAINT ck_memory_generations_format_mode
    CHECK (format_mode IS NULL OR format_mode IN ('strict_native', 'json_mode', 'prompt_only'));

ALTER TABLE memory_generations
    ADD CONSTRAINT ck_memory_generations_status
    CHECK (status IS NULL OR btrim(status) <> '');

ALTER TABLE memory_generations
    ADD CONSTRAINT ck_memory_generations_reservation_outcome
    CHECK (
        send_number IS NULL OR status IS NOT NULL
        OR (raw_candidate IS NULL AND raw_candidate_hash IS NULL AND diagnostics IS NULL
            AND normalization IS NULL AND input_tokens IS NULL AND output_tokens IS NULL
            AND cost IS NULL AND latency_ms IS NULL)
    );

ALTER TABLE memory_generations
    ADD CONSTRAINT ck_memory_generations_candidate_hash
    CHECK (raw_candidate_hash IS NULL OR raw_candidate_hash ~ '^[0-9a-f]{64}$');

ALTER TABLE memory_generations
    ADD CONSTRAINT ck_memory_generations_candidate_hash_required
    CHECK (raw_candidate IS NULL OR raw_candidate_hash IS NOT NULL);

ALTER TABLE memory_generations
    ADD CONSTRAINT ck_memory_generations_candidate_hash_matches
    CHECK (
        raw_candidate IS NULL OR raw_candidate_hash =
        encode(sha256(convert_to(raw_candidate, 'UTF8')), 'hex')
    );

ALTER TABLE memory_generations
    ADD CONSTRAINT ck_memory_generations_diagnostics
    CHECK (diagnostics IS NULL OR jsonb_typeof(diagnostics) = 'array');

ALTER TABLE memory_generations
    ADD CONSTRAINT ck_memory_generations_normalization
    CHECK (normalization IS NULL OR normalization IN ('none', 'json_fence_v1'));

CREATE OR REPLACE FUNCTION saga_memory_job_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    batch_predecessor uuid;
    checkpoint_batch uuid;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF ROW(NEW.id, NEW.campaign_id, NEW.policy_id, NEW.batch_id, NEW.memory_state_id,
               NEW.context_epoch, NEW.kind, NEW.previous_checkpoint_id, NEW.logical_key,
               NEW.manifest, NEW.manifest_hash, NEW.producer_version, NEW.prompt_version,
               NEW.execution_identity, NEW.execution_identity_hash, NEW.execution_identity_version)
           IS DISTINCT FROM
           ROW(OLD.id, OLD.campaign_id, OLD.policy_id, OLD.batch_id, OLD.memory_state_id,
               OLD.context_epoch, OLD.kind, OLD.previous_checkpoint_id, OLD.logical_key,
               OLD.manifest, OLD.manifest_hash, OLD.producer_version, OLD.prompt_version,
               OLD.execution_identity, OLD.execution_identity_hash, OLD.execution_identity_version) THEN
            RAISE EXCEPTION 'Memory job identity and input are immutable.' USING ERRCODE = '23514';
        END IF;
        IF NEW.attempt_count < OLD.attempt_count OR NEW.retry_cycle < OLD.retry_cycle THEN
            RAISE EXCEPTION 'Memory job attempt counters cannot decrease.' USING ERRCODE = '23514';
        END IF;
        IF OLD.terminal_at IS NOT NULL THEN
            IF NEW.terminal_at IS DISTINCT FROM OLD.terminal_at
               OR NEW.state IS DISTINCT FROM OLD.state THEN
                RAISE EXCEPTION 'A terminal memory job cannot be reopened or retimed.' USING ERRCODE = '23514';
            END IF;
        ELSIF NEW.terminal_at IS NOT NULL THEN
            IF OLD.state IN ('succeeded', 'exhausted')
               OR NEW.state NOT IN ('succeeded', 'exhausted')
               OR NEW.execution_identity IS NULL THEN
                RAISE EXCEPTION 'A terminal timestamp must be set at definitive termination.' USING ERRCODE = '23514';
            END IF;
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
DECLARE
    job_identity jsonb;
    job_state text;
    job_claim_token uuid;
    job_lease_expires_at timestamptz;
    job_retry_cycle integer;
    attempt_claim_token uuid;
    attempt_state text;
    attempt_retry_cycle integer;
    max_sends numeric;
    existing_sends bigint;
    result_identity jsonb;
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF NOT EXISTS (SELECT 1 FROM campaigns WHERE id = OLD.campaign_id) THEN RETURN OLD; END IF;
        RAISE EXCEPTION 'Memory generation provenance is immutable.' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'INSERT' THEN
        SELECT execution_identity, state, claim_token, retry_cycle, lease_expires_at
        INTO job_identity, job_state, job_claim_token, job_retry_cycle, job_lease_expires_at
        FROM memory_jobs
        WHERE id = NEW.job_id AND campaign_id = NEW.campaign_id
          AND policy_id = NEW.policy_id AND batch_id = NEW.batch_id
        FOR UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'Memory generation job provenance is invalid.' USING ERRCODE = '23514';
        END IF;
        IF NEW.send_number IS NULL THEN
            IF NEW.send_kind IS NOT NULL OR NEW.request_identity_hash IS NOT NULL
               OR NEW.format_mode IS NOT NULL OR job_identity IS NOT NULL THEN
                RAISE EXCEPTION 'Durable jobs require typed send reservations.' USING ERRCODE = '23514';
            END IF;
            IF NEW.status IS NOT NULL OR NEW.raw_candidate IS NOT NULL
               OR NEW.raw_candidate_hash IS NOT NULL OR NEW.diagnostics IS NOT NULL
               OR NEW.normalization IS NOT NULL THEN
                RAISE EXCEPTION 'Legacy generations cannot carry recovery outcomes.' USING ERRCODE = '23514';
            END IF;
        ELSE
            IF NEW.status IS NOT NULL OR NEW.raw_candidate IS NOT NULL
               OR NEW.raw_candidate_hash IS NOT NULL OR NEW.diagnostics IS NOT NULL
               OR NEW.normalization IS NOT NULL OR NEW.input_tokens IS NOT NULL
               OR NEW.output_tokens IS NOT NULL OR NEW.cost IS NOT NULL OR NEW.latency_ms IS NOT NULL THEN
                RAISE EXCEPTION 'A generation reservation cannot include an outcome.' USING ERRCODE = '23514';
            END IF;
            result_identity := job_identity->'result_identities'->NEW.role;
            IF job_identity IS NULL OR jsonb_typeof(result_identity) IS DISTINCT FROM 'object'
               OR result_identity->>'role' IS DISTINCT FROM NEW.role
               OR result_identity->>'request_identity_hash' IS DISTINCT FROM NEW.request_identity_hash
               OR job_state <> 'running' OR job_claim_token IS NULL
               OR job_lease_expires_at <= clock_timestamp() THEN
                RAISE EXCEPTION 'A send reservation requires its active result identity and claim.' USING ERRCODE = '23514';
            END IF;
            IF jsonb_typeof(job_identity->'max_sends_per_result') IS DISTINCT FROM 'number'
               OR job_identity->>'max_sends_per_result' IS NULL
               OR job_identity->>'max_sends_per_result' !~ '^[1-9][0-9]*$' THEN
                RAISE EXCEPTION 'The memory job send budget is invalid.' USING ERRCODE = '23514';
            END IF;
            max_sends := (job_identity->>'max_sends_per_result')::numeric;
            IF NEW.send_number::numeric > max_sends THEN
                RAISE EXCEPTION 'The result send budget is exhausted.' USING ERRCODE = '23514';
            END IF;
            SELECT claim_token, state, retry_cycle
            INTO attempt_claim_token, attempt_state, attempt_retry_cycle
            FROM memory_job_attempts
            WHERE id = NEW.attempt_id AND job_id = NEW.job_id
              AND campaign_id = NEW.campaign_id;
            IF NOT FOUND OR attempt_state <> 'started'
               OR attempt_claim_token IS DISTINCT FROM job_claim_token
               OR attempt_retry_cycle <> job_retry_cycle THEN
                RAISE EXCEPTION 'A send reservation must belong to the active claim attempt.' USING ERRCODE = '23514';
            END IF;
            SELECT count(*) INTO existing_sends
            FROM memory_generations
            WHERE job_id = NEW.job_id AND role = NEW.role AND send_number IS NOT NULL;
            IF NEW.send_number::bigint <> existing_sends + 1 THEN
                RAISE EXCEPTION 'Result send reservations must be consecutive.' USING ERRCODE = '23514';
            END IF;
        END IF;
        RETURN NEW;
    END IF;
    IF to_jsonb(NEW) - ARRAY[
        'updated_at', 'status', 'raw_candidate', 'raw_candidate_hash', 'diagnostics',
        'normalization', 'input_tokens', 'output_tokens', 'cost', 'latency_ms'
    ] IS DISTINCT FROM to_jsonb(OLD) - ARRAY[
        'updated_at', 'status', 'raw_candidate', 'raw_candidate_hash', 'diagnostics',
        'normalization', 'input_tokens', 'output_tokens', 'cost', 'latency_ms'
    ] THEN
        RAISE EXCEPTION 'Memory generation provenance is immutable.' USING ERRCODE = '23514';
    END IF;
    IF ROW(NEW.status, NEW.raw_candidate, NEW.raw_candidate_hash, NEW.diagnostics,
           NEW.normalization, NEW.input_tokens, NEW.output_tokens, NEW.cost, NEW.latency_ms)
       IS DISTINCT FROM
       ROW(OLD.status, OLD.raw_candidate, OLD.raw_candidate_hash, OLD.diagnostics,
           OLD.normalization, OLD.input_tokens, OLD.output_tokens, OLD.cost, OLD.latency_ms) THEN
        IF OLD.send_number IS NULL OR OLD.status IS NOT NULL OR NEW.status IS NULL THEN
            RAISE EXCEPTION 'A generation outcome can be recorded only once.' USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END
$$;

DROP TRIGGER memory_generation_guard ON memory_generations;

CREATE TRIGGER memory_generation_guard BEFORE INSERT OR UPDATE OR DELETE ON memory_generations
FOR EACH ROW EXECUTE FUNCTION saga_memory_generation_guard();
