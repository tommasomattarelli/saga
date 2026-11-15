ALTER TABLE memory_jobs
    ADD COLUMN execution_contract_version integer;

ALTER TABLE memory_generations
    ADD COLUMN request_identity_snapshot text,
    ADD COLUMN outcome_reason varchar(64),
    ADD COLUMN receipt text;

ALTER TABLE memory_jobs
    ADD CONSTRAINT ck_memory_jobs_execution_contract_version
    CHECK (execution_contract_version IS NULL OR execution_contract_version = 1),
    ADD CONSTRAINT ck_memory_jobs_marked_identity_state
    CHECK (
        execution_contract_version IS NULL OR execution_identity IS NOT NULL OR state = 'blocked'
    );

ALTER TABLE memory_generations
    DROP CONSTRAINT ck_memory_generations_send_identity,
    DROP CONSTRAINT ck_memory_generations_reservation_outcome;

ALTER TABLE memory_generations
    ADD CONSTRAINT ck_memory_generations_send_identity
    CHECK (
        (send_number IS NULL AND send_kind IS NULL AND request_identity_hash IS NULL
         AND request_identity_snapshot IS NULL AND format_mode IS NULL)
        OR (send_number IS NOT NULL AND send_kind IS NOT NULL
            AND request_identity_hash IS NOT NULL AND request_identity_snapshot IS NOT NULL
            AND format_mode IS NOT NULL AND role <> 'batch')
    ),
    ADD CONSTRAINT ck_memory_generations_request_identity_snapshot
    CHECK (
        request_identity_snapshot IS NULL
        OR jsonb_typeof(request_identity_snapshot::jsonb) = 'object'
    ),
    ADD CONSTRAINT ck_memory_generations_outcome_reason
    CHECK (
        outcome_reason IS NULL OR outcome_reason IN
        ('cancelled', 'internal_failure', 'validation_failed', 'validator_failure', 'transport_failure',
         'timeout', 'server', 'provider_overloaded', 'provider_unavailable', 'rate_limited',
         'provider_request_rejected', 'context_length_exceeded', 'refusal', 'truncated',
         'content_blocked', 'schema_mode_unsupported', 'quota_or_billing_limit',
         'input_field_too_long', 'token_limit_exceeded', 'invalid_classification_input',
         'unmapped_router_error', 'unclassified_provider_failure', 'unclassified_rate_limit',
         'transient_provider_failure')
    ),
    ADD CONSTRAINT ck_memory_generations_receipt
    CHECK (
        receipt IS NULL
        OR (
            jsonb_typeof(receipt::jsonb) = 'object'
            AND receipt::jsonb->>'encoding_version' = '1'
            AND jsonb_typeof(receipt::jsonb->'candidate_in_column') = 'boolean'
            AND (receipt::jsonb->>'candidate_in_column')::boolean = (raw_candidate IS NOT NULL)
        )
    ),
    ADD CONSTRAINT ck_memory_generations_reservation_outcome
    CHECK (
        send_number IS NULL OR status IS NOT NULL
        OR (outcome_reason IS NULL AND raw_candidate IS NULL AND raw_candidate_hash IS NULL AND receipt IS NULL
            AND diagnostics IS NULL AND normalization IS NULL AND input_tokens IS NULL
            AND output_tokens IS NULL AND cost IS NULL AND latency_ms IS NULL)
    );

CREATE OR REPLACE FUNCTION saga_memory_job_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    batch_predecessor uuid;
    checkpoint_batch uuid;
    identity_changed boolean;
BEGIN
    IF NEW.execution_contract_version IS NOT NULL AND NEW.execution_identity IS NOT NULL
       AND (
           NEW.execution_contract_version <> 1
           OR NEW.execution_identity_version <> 1
           OR jsonb_typeof(NEW.execution_identity->'result_identities') <> 'object'
           OR jsonb_typeof(NEW.execution_identity->'max_sends_per_result') <> 'number'
           OR NEW.execution_identity->>'max_sends_per_result' !~ '^[1-9][0-9]*$'
           OR NOT saga_memory_validate_job_identity(NEW.execution_identity)
           OR NEW.execution_identity_hash IS DISTINCT FROM saga_memory_job_identity_digest(
               NEW.execution_identity, NEW.execution_identity_version
           )
       ) THEN
        RAISE EXCEPTION 'Current-contract memory job identity is invalid.' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'UPDATE' THEN
        IF ROW(NEW.id, NEW.campaign_id, NEW.policy_id, NEW.batch_id, NEW.memory_state_id,
               NEW.context_epoch, NEW.kind, NEW.previous_checkpoint_id, NEW.logical_key,
               NEW.manifest, NEW.manifest_hash, NEW.producer_version, NEW.prompt_version,
               NEW.execution_contract_version)
           IS DISTINCT FROM
           ROW(OLD.id, OLD.campaign_id, OLD.policy_id, OLD.batch_id, OLD.memory_state_id,
               OLD.context_epoch, OLD.kind, OLD.previous_checkpoint_id, OLD.logical_key,
               OLD.manifest, OLD.manifest_hash, OLD.producer_version, OLD.prompt_version,
               OLD.execution_contract_version) THEN
            RAISE EXCEPTION 'Memory job identity and input are immutable.' USING ERRCODE = '23514';
        END IF;
        identity_changed := ROW(NEW.execution_identity, NEW.execution_identity_hash,
                                NEW.execution_identity_version)
                            IS DISTINCT FROM
                            ROW(OLD.execution_identity, OLD.execution_identity_hash,
                                OLD.execution_identity_version);
        IF identity_changed AND NOT (
            OLD.execution_contract_version = 1
            AND NEW.execution_contract_version = OLD.execution_contract_version
            AND OLD.execution_identity IS NULL
            AND OLD.execution_identity_hash IS NULL
            AND OLD.execution_identity_version IS NULL
            AND NEW.execution_identity IS NOT NULL
            AND NEW.execution_identity_hash IS NOT NULL
            AND NEW.execution_identity_version IS NOT NULL
            AND NEW.execution_identity_version = 1
            AND NEW.execution_identity->'result_identities' IS NOT NULL
            AND jsonb_typeof(NEW.execution_identity->'result_identities') = 'object'
            AND NEW.execution_identity->>'max_sends_per_result' ~ '^[1-9][0-9]*$'
            AND saga_memory_validate_job_identity(NEW.execution_identity)
            AND NEW.execution_identity_hash = saga_memory_job_identity_digest(
                NEW.execution_identity, NEW.execution_identity_version
            )
            AND OLD.state = 'blocked'
            AND NEW.state = 'queued'
        ) THEN
            RAISE EXCEPTION 'Memory job execution identity is immutable.' USING ERRCODE = '23514';
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

CREATE OR REPLACE FUNCTION saga_memory_generation_request_snapshot(value jsonb)
RETURNS text LANGUAGE plpgsql IMMUTABLE STRICT AS $$
DECLARE
    snapshot_keys text[] := ARRAY[
        'allow_json_mode_fallback', 'allow_prompt_only_fallback',
        'contextual_validator_version', 'contract_name', 'contract_schema_hash',
        'contract_version', 'destination_fingerprint', 'effective_schema_hash',
        'format_mode', 'format_version', 'initial_prefix_hash', 'logical_result_id',
        'model', 'output_limit', 'provider', 'role', 'session_affinity',
        'tool_declarations_hash', 'wire_encoding_version', 'wire_schema_hash'
    ];
    limit_keys text[] := ARRAY['configured_ceiling', 'known_lower_limit', 'limit_source'];
    fields text;
    limits text;
BEGIN
    IF jsonb_typeof(value) <> 'object'
       OR value - snapshot_keys <> '{}'::jsonb
       OR NOT (value ?& snapshot_keys)
       OR jsonb_typeof(value->'format_version') <> 'number'
       OR (value->>'format_version') !~ '^[1-9][0-9]*$'
       OR jsonb_typeof(value->'allow_json_mode_fallback') <> 'boolean'
       OR jsonb_typeof(value->'allow_prompt_only_fallback') <> 'boolean'
       OR value->>'format_mode' NOT IN ('strict_native', 'json_mode', 'prompt_only')
       OR jsonb_typeof(value->'output_limit') <> 'object'
       OR (value->'output_limit') - limit_keys <> '{}'::jsonb
       OR NOT ((value->'output_limit') ?& limit_keys)
       OR jsonb_typeof(value->'output_limit'->'configured_ceiling') <> 'number'
       OR (value->'output_limit'->>'configured_ceiling') !~ '^[1-9][0-9]*$'
       OR jsonb_typeof(value->'output_limit'->'known_lower_limit') NOT IN ('number', 'null')
       OR (value->'output_limit'->'known_lower_limit' <> 'null'::jsonb
           AND (value->'output_limit'->>'known_lower_limit') !~ '^[1-9][0-9]*$')
       OR jsonb_typeof(value->'output_limit'->'limit_source') NOT IN ('string', 'null')
       OR (value->'output_limit'->'limit_source' = '""'::jsonb)
       OR ((value->'output_limit'->'known_lower_limit' = 'null'::jsonb)
           <> (value->'output_limit'->'limit_source' = 'null'::jsonb))
       OR jsonb_typeof(value->'session_affinity') NOT IN ('string', 'null')
       OR value->'session_affinity' = '""'::jsonb THEN
        RAISE EXCEPTION 'Send request identity snapshot has an invalid typed shape.' USING ERRCODE = '23514';
    END IF;
    IF EXISTS (
        SELECT 1 FROM jsonb_each(value) AS fields(key, val)
        WHERE key <> 'output_limit' AND
              ((key IN ('format_version') AND jsonb_typeof(val) <> 'number')
               OR (key IN ('allow_json_mode_fallback', 'allow_prompt_only_fallback')
                   AND jsonb_typeof(val) <> 'boolean')
               OR (key = 'session_affinity' AND jsonb_typeof(val) NOT IN ('string', 'null'))
               OR (key = 'format_mode' AND jsonb_typeof(val) <> 'string')
               OR (key NOT IN ('format_version', 'allow_json_mode_fallback',
                               'allow_prompt_only_fallback', 'session_affinity',
                               'format_mode') AND jsonb_typeof(val) <> 'string'))
    ) THEN
        RAISE EXCEPTION 'Send request identity snapshot has an invalid typed field.' USING ERRCODE = '23514';
    END IF;
    IF EXISTS (
        SELECT 1 FROM jsonb_each_text(value) AS fields(key, val)
        WHERE key IN ('role', 'logical_result_id', 'contract_name', 'contract_version',
                      'wire_encoding_version', 'contextual_validator_version', 'provider',
                      'model', 'destination_fingerprint')
          AND val = ''
    ) OR EXISTS (
        SELECT 1 FROM jsonb_each_text(value) AS fields(key, val)
        WHERE key IN ('initial_prefix_hash', 'contract_schema_hash', 'effective_schema_hash',
                      'wire_schema_hash', 'tool_declarations_hash')
          AND val !~ '^[0-9a-f]{64}$'
    ) THEN
        RAISE EXCEPTION 'Send request identity snapshot has invalid identity values.' USING ERRCODE = '23514';
    END IF;
    SELECT string_agg(to_json(key)::text || ':' || val::text, ',' ORDER BY key)
    INTO limits FROM jsonb_each(value->'output_limit') AS fields(key, val);
    SELECT string_agg(
        to_json(key)::text || ':' ||
        CASE WHEN key = 'output_limit' THEN '{' || limits || '}' ELSE val::text END,
        ',' ORDER BY key
    ) INTO fields FROM jsonb_each(value) AS fields(key, val);
    RETURN '{' || fields || '}';
END
$$;

CREATE OR REPLACE FUNCTION saga_memory_ascii_json_string(value text)
RETURNS text LANGUAGE plpgsql IMMUTABLE STRICT AS $$
DECLARE
    result text := '"';
    character text;
    codepoint integer;
    scalar integer;
    index integer;
BEGIN
    FOR index IN 1..char_length(value)
    LOOP
        character := substr(value, index, 1);
        codepoint := ascii(character);
        IF character = '"' THEN
            result := result || E'\\"';
        ELSIF character = E'\\' THEN
            result := result || E'\\\\';
        ELSIF codepoint = 8 THEN
            result := result || E'\\b';
        ELSIF codepoint = 9 THEN
            result := result || E'\\t';
        ELSIF codepoint = 10 THEN
            result := result || E'\\n';
        ELSIF codepoint = 12 THEN
            result := result || E'\\f';
        ELSIF codepoint = 13 THEN
            result := result || E'\\r';
        ELSIF codepoint < 32 THEN
            result := result || E'\\u' || lpad(to_hex(codepoint), 4, '0');
        ELSIF codepoint <= 127 THEN
            result := result || character;
        ELSIF codepoint <= 65535 THEN
            result := result || E'\\u' || lpad(to_hex(codepoint), 4, '0');
        ELSE
            scalar := codepoint - 65536;
            result := result || E'\\u' || lpad(to_hex(55296 + (scalar >> 10)), 4, '0')
                || E'\\u' || lpad(to_hex(56320 + (scalar & 1023)), 4, '0');
        END IF;
    END LOOP;
    RETURN result || '"';
END
$$;

CREATE OR REPLACE FUNCTION saga_memory_canonical_json(value jsonb)
RETURNS text LANGUAGE plpgsql IMMUTABLE STRICT AS $$
DECLARE
    result text;
BEGIN
    CASE jsonb_typeof(value)
        WHEN 'object' THEN
            SELECT '{' || COALESCE(string_agg(
                saga_memory_ascii_json_string(key) || ':' || saga_memory_canonical_json(val),
                ',' ORDER BY key COLLATE "C"
            ), '') || '}' INTO result FROM jsonb_each(value) AS fields(key, val);
            RETURN result;
        WHEN 'array' THEN
            SELECT '[' || COALESCE(string_agg(saga_memory_canonical_json(val), ',' ORDER BY ord), '') || ']'
            INTO result FROM jsonb_array_elements(value) WITH ORDINALITY AS items(val, ord);
            RETURN result;
        ELSE
            IF jsonb_typeof(value) = 'string' THEN
                RETURN saga_memory_ascii_json_string(value #>> '{}');
            END IF;
            RETURN value::text;
    END CASE;
END
$$;

CREATE OR REPLACE FUNCTION saga_memory_job_identity_digest(value jsonb, version integer)
RETURNS text LANGUAGE sql IMMUTABLE STRICT AS $$
    SELECT encode(sha256(convert_to(saga_memory_canonical_json(
        jsonb_build_object(
            'version', version,
            'result_identities', value->'result_identities',
            'max_sends_per_result', value->'max_sends_per_result'
        )
    ), 'UTF8')), 'hex')
$$;

CREATE OR REPLACE FUNCTION saga_memory_validate_job_identity(value jsonb)
RETURNS boolean LANGUAGE plpgsql IMMUTABLE STRICT AS $$
DECLARE
    identity_keys text[] := ARRAY[
        'allow_json_mode_fallback', 'allow_prompt_only_fallback', 'contract_name',
        'contract_schema_hash', 'contract_version', 'contextual_validator_version',
        'destination_fingerprint', 'effective_schema_hash', 'format_mode',
        'format_version', 'initial_prefix_hash', 'logical_result_id', 'model',
        'output_limit', 'provider', 'request_identity_hash', 'role', 'session_affinity',
        'tool_declarations_hash', 'wire_encoding_version', 'wire_schema_hash'
    ];
    role_key text;
    role_value jsonb;
    limits jsonb;
BEGIN
    IF jsonb_typeof(value) <> 'object'
       OR value - ARRAY['max_sends_per_result', 'result_identities'] <> '{}'::jsonb
       OR NOT (value ?& ARRAY['max_sends_per_result', 'result_identities'])
       OR jsonb_typeof(value->'max_sends_per_result') <> 'number'
       OR (value->>'max_sends_per_result') !~ '^[1-9][0-9]*$'
       OR jsonb_typeof(value->'result_identities') <> 'object'
       OR value->'result_identities' = '{}'::jsonb THEN
        RETURN false;
    END IF;
    FOR role_key, role_value IN
        SELECT key, val FROM jsonb_each(value->'result_identities') AS roles(key, val)
    LOOP
        IF role_key = ''
           OR jsonb_typeof(role_value) <> 'object'
           OR role_value - identity_keys <> '{}'::jsonb
           OR NOT (role_value ?& identity_keys)
           OR role_value->>'role' IS DISTINCT FROM role_key
           OR jsonb_typeof(role_value->'format_version') <> 'number'
           OR (role_value->>'format_version') !~ '^[1-9][0-9]*$'
           OR jsonb_typeof(role_value->'role') <> 'string'
           OR jsonb_typeof(role_value->'logical_result_id') <> 'string'
           OR jsonb_typeof(role_value->'contract_name') <> 'string'
           OR jsonb_typeof(role_value->'contract_version') <> 'string'
           OR jsonb_typeof(role_value->'contextual_validator_version') <> 'string'
           OR jsonb_typeof(role_value->'destination_fingerprint') <> 'string'
           OR jsonb_typeof(role_value->'wire_encoding_version') <> 'string'
           OR jsonb_typeof(role_value->'provider') <> 'string'
           OR jsonb_typeof(role_value->'model') <> 'string'
           OR jsonb_typeof(role_value->'allow_json_mode_fallback') <> 'boolean'
           OR jsonb_typeof(role_value->'allow_prompt_only_fallback') <> 'boolean'
           OR jsonb_typeof(role_value->'session_affinity') NOT IN ('string', 'null')
           OR role_value->'session_affinity' = '""'::jsonb
           OR jsonb_typeof(role_value->'format_mode') <> 'string'
           OR role_value->>'format_mode' NOT IN ('strict_native', 'json_mode', 'prompt_only')
           OR jsonb_typeof(role_value->'output_limit') <> 'object' THEN
            RETURN false;
        END IF;
        IF EXISTS (
            SELECT 1 FROM jsonb_each(role_value) AS fields(key, val)
            WHERE key IN ('initial_prefix_hash', 'contract_schema_hash',
                          'effective_schema_hash', 'wire_schema_hash',
                          'tool_declarations_hash', 'request_identity_hash')
              AND jsonb_typeof(val) <> 'string'
        ) OR EXISTS (
            SELECT 1 FROM jsonb_each_text(role_value) AS fields(key, val)
            WHERE key IN ('initial_prefix_hash', 'contract_schema_hash',
                          'effective_schema_hash', 'wire_schema_hash',
                          'tool_declarations_hash', 'request_identity_hash')
              AND val !~ '^[0-9a-f]{64}$'
        ) OR EXISTS (
            SELECT 1 FROM jsonb_each_text(role_value) AS fields(key, val)
            WHERE key IN ('logical_result_id', 'contract_name', 'contract_version',
                          'contextual_validator_version', 'destination_fingerprint',
                          'wire_encoding_version', 'provider', 'model')
              AND val = ''
        ) THEN
            RETURN false;
        END IF;
        limits := role_value->'output_limit';
        IF limits - ARRAY['configured_ceiling', 'known_lower_limit', 'limit_source'] <> '{}'::jsonb
           OR NOT (limits ?& ARRAY['configured_ceiling', 'known_lower_limit', 'limit_source'])
           OR jsonb_typeof(limits->'configured_ceiling') <> 'number'
           OR (limits->>'configured_ceiling') !~ '^[1-9][0-9]*$'
           OR jsonb_typeof(limits->'known_lower_limit') NOT IN ('number', 'null')
           OR (limits->'known_lower_limit' <> 'null'::jsonb
               AND (limits->>'known_lower_limit') !~ '^[1-9][0-9]*$')
           OR jsonb_typeof(limits->'limit_source') NOT IN ('string', 'null')
           OR limits->'limit_source' = '""'::jsonb
           OR ((limits->'known_lower_limit' = 'null'::jsonb)
               <> (limits->'limit_source' = 'null'::jsonb)) THEN
            RETURN false;
        END IF;
    END LOOP;
    RETURN true;
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
    derived_identity jsonb;
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
               OR NEW.request_identity_snapshot IS NOT NULL OR NEW.format_mode IS NOT NULL
               OR NEW.receipt IS NOT NULL OR job_identity IS NOT NULL THEN
                RAISE EXCEPTION 'Durable jobs require typed send reservations.' USING ERRCODE = '23514';
            END IF;
            IF EXISTS (
                SELECT 1 FROM memory_jobs
                WHERE id = NEW.job_id AND execution_contract_version IS NOT NULL
            ) THEN
                RAISE EXCEPTION 'Current-contract jobs require typed send reservations.' USING ERRCODE = '23514';
            END IF;
            IF NEW.status IS NOT NULL OR NEW.raw_candidate IS NOT NULL
               OR NEW.raw_candidate_hash IS NOT NULL OR NEW.diagnostics IS NOT NULL
               OR NEW.normalization IS NOT NULL THEN
                RAISE EXCEPTION 'Legacy generations cannot carry recovery outcomes.' USING ERRCODE = '23514';
            END IF;
        ELSE
            IF NEW.status IS NOT NULL OR NEW.raw_candidate IS NOT NULL
               OR NEW.raw_candidate_hash IS NOT NULL OR NEW.receipt IS NOT NULL
               OR NEW.diagnostics IS NOT NULL OR NEW.normalization IS NOT NULL
               OR NEW.input_tokens IS NOT NULL OR NEW.output_tokens IS NOT NULL
               OR NEW.cost IS NOT NULL OR NEW.latency_ms IS NOT NULL THEN
                RAISE EXCEPTION 'A generation reservation cannot include an outcome.' USING ERRCODE = '23514';
            END IF;
            result_identity := job_identity->'result_identities'->NEW.role;
            IF job_identity IS NULL OR jsonb_typeof(result_identity) IS DISTINCT FROM 'object'
               OR result_identity->>'role' IS DISTINCT FROM NEW.role
               OR job_state <> 'running' OR job_claim_token IS NULL
               OR job_lease_expires_at <= clock_timestamp() THEN
                RAISE EXCEPTION 'A send reservation requires its active result identity and claim.' USING ERRCODE = '23514';
            END IF;
            derived_identity := NEW.request_identity_snapshot::jsonb;
            IF saga_memory_generation_request_snapshot(derived_identity)
                   IS DISTINCT FROM NEW.request_identity_snapshot
               OR encode(sha256(convert_to(NEW.request_identity_snapshot, 'UTF8')), 'hex')
                   IS DISTINCT FROM NEW.request_identity_hash
               OR derived_identity->>'role' IS DISTINCT FROM NEW.role
               OR (derived_identity - 'initial_prefix_hash' - 'format_mode')
                    IS DISTINCT FROM
                  (result_identity - 'request_identity_hash' - 'initial_prefix_hash' - 'format_mode') THEN
                RAISE EXCEPTION 'A send identity must be a verified derivation of its frozen result.' USING ERRCODE = '23514';
            END IF;
            IF derived_identity->>'format_mode' IS DISTINCT FROM result_identity->>'format_mode'
               AND NOT (
                   (result_identity->>'format_mode' = 'strict_native'
                    AND derived_identity->>'format_mode' = 'json_mode'
                    AND result_identity->>'allow_json_mode_fallback' = 'true')
                   OR
                   (result_identity->>'format_mode' IN ('strict_native', 'json_mode')
                    AND derived_identity->>'format_mode' = 'prompt_only'
                    AND result_identity->>'allow_prompt_only_fallback' = 'true')
               ) THEN
                RAISE EXCEPTION 'A send identity uses an unauthorized format derivation.' USING ERRCODE = '23514';
            END IF;
            IF derived_identity->>'format_mode' IS DISTINCT FROM NEW.format_mode THEN
                RAISE EXCEPTION 'A send format must match its request identity.' USING ERRCODE = '23514';
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
        'updated_at', 'status', 'outcome_reason', 'raw_candidate', 'raw_candidate_hash', 'receipt',
        'diagnostics', 'normalization', 'input_tokens', 'output_tokens', 'cost', 'latency_ms'
    ] IS DISTINCT FROM to_jsonb(OLD) - ARRAY[
        'updated_at', 'status', 'outcome_reason', 'raw_candidate', 'raw_candidate_hash', 'receipt',
        'diagnostics', 'normalization', 'input_tokens', 'output_tokens', 'cost', 'latency_ms'
    ] THEN
        RAISE EXCEPTION 'Memory generation provenance is immutable.' USING ERRCODE = '23514';
    END IF;
    IF ROW(NEW.status, NEW.outcome_reason, NEW.raw_candidate, NEW.raw_candidate_hash, NEW.receipt,
           NEW.diagnostics, NEW.normalization, NEW.input_tokens, NEW.output_tokens, NEW.cost,
           NEW.latency_ms)
       IS DISTINCT FROM
       ROW(OLD.status, OLD.outcome_reason, OLD.raw_candidate, OLD.raw_candidate_hash, OLD.receipt,
           OLD.diagnostics, OLD.normalization, OLD.input_tokens, OLD.output_tokens, OLD.cost,
           OLD.latency_ms) THEN
        IF OLD.send_number IS NULL THEN
            RAISE EXCEPTION 'A generation outcome can be recorded only once.' USING ERRCODE = '23514';
        END IF;
        IF OLD.status IS NULL THEN
            IF NEW.status IS NULL THEN
                RAISE EXCEPTION 'A generation outcome requires a status.' USING ERRCODE = '23514';
            END IF;
        ELSIF NEW.status IS DISTINCT FROM OLD.status
           OR NEW.outcome_reason IS DISTINCT FROM OLD.outcome_reason
           OR NEW.raw_candidate_hash IS DISTINCT FROM OLD.raw_candidate_hash
           OR (OLD.raw_candidate IS DISTINCT FROM NEW.raw_candidate AND NEW.raw_candidate IS NOT NULL)
           OR (OLD.receipt IS DISTINCT FROM NEW.receipt AND NEW.receipt IS NOT NULL)
           OR (OLD.diagnostics IS DISTINCT FROM NEW.diagnostics AND NEW.diagnostics IS NOT NULL)
           OR (OLD.normalization IS DISTINCT FROM NEW.normalization AND NEW.normalization IS NOT NULL)
           OR (OLD.input_tokens IS DISTINCT FROM NEW.input_tokens AND NEW.input_tokens IS NOT NULL)
           OR (OLD.output_tokens IS DISTINCT FROM NEW.output_tokens AND NEW.output_tokens IS NOT NULL)
           OR (OLD.cost IS DISTINCT FROM NEW.cost AND NEW.cost IS NOT NULL)
           OR (OLD.latency_ms IS DISTINCT FROM NEW.latency_ms AND NEW.latency_ms IS NOT NULL) THEN
            RAISE EXCEPTION 'A generation outcome is immutable except for payload clearing.' USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END
$$;

DROP TRIGGER memory_generation_guard ON memory_generations;

CREATE TRIGGER memory_generation_guard BEFORE INSERT OR UPDATE OR DELETE ON memory_generations
FOR EACH ROW EXECUTE FUNCTION saga_memory_generation_guard();
