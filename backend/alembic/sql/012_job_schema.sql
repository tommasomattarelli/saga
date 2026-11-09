CREATE TABLE memory_jobs (
    id uuid PRIMARY KEY,
    campaign_id uuid NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    policy_id uuid NOT NULL,
    batch_id uuid NOT NULL,
    memory_state_id uuid NOT NULL,
    context_epoch integer NOT NULL,
    kind varchar(16) NOT NULL,
    previous_checkpoint_id uuid,
    logical_key varchar(64) NOT NULL,
    manifest jsonb NOT NULL,
    manifest_hash varchar(64) NOT NULL,
    producer_version varchar(100) NOT NULL,
    prompt_version varchar(100) NOT NULL,
    state varchar(16) NOT NULL,
    attempt_count integer NOT NULL,
    retry_cycle integer NOT NULL,
    cycle_attempt_count integer NOT NULL,
    next_attempt_at timestamptz,
    claim_token uuid,
    lease_expires_at timestamptz,
    last_error varchar(500),
    activation_state varchar(16) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_memory_jobs_policy_campaign
        FOREIGN KEY (policy_id, campaign_id) REFERENCES memory_policies(id, campaign_id)
        DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT fk_memory_jobs_batch_campaign_policy
        FOREIGN KEY (batch_id, campaign_id, policy_id)
        REFERENCES memory_batches(id, campaign_id, policy_id) DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT fk_memory_jobs_state_campaign_policy
        FOREIGN KEY (memory_state_id, campaign_id, policy_id)
        REFERENCES memory_states(id, campaign_id, policy_id) DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT fk_memory_jobs_checkpoint_campaign_policy
        FOREIGN KEY (previous_checkpoint_id, campaign_id, policy_id)
        REFERENCES memory_global_checkpoints(id, campaign_id, policy_id) DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT uq_memory_jobs_id_campaign UNIQUE (id, campaign_id),
    CONSTRAINT uq_memory_jobs_provenance UNIQUE (id, campaign_id, policy_id, batch_id),
    CONSTRAINT uq_memory_jobs_campaign_key UNIQUE (campaign_id, logical_key),
    CONSTRAINT ck_memory_jobs_kind CHECK (kind IN ('batch', 'global')),
    CONSTRAINT ck_memory_jobs_state
        CHECK (state IN ('queued', 'running', 'retry_wait', 'blocked', 'exhausted', 'succeeded')),
    CONSTRAINT ck_memory_jobs_activation CHECK (activation_state IN ('pending', 'active', 'detached')),
    CONSTRAINT ck_memory_jobs_counters
        CHECK (attempt_count >= 0 AND retry_cycle >= 0 AND cycle_attempt_count >= 0
               AND cycle_attempt_count <= attempt_count),
    CONSTRAINT ck_memory_jobs_context_epoch CHECK (context_epoch >= 0),
    CONSTRAINT ck_memory_jobs_logical_key CHECK (logical_key ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_memory_jobs_manifest_hash CHECK (manifest_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_memory_jobs_batch_predecessor
        CHECK (kind <> 'batch' OR previous_checkpoint_id IS NULL),
    CONSTRAINT ck_memory_jobs_claim_state
        CHECK ((state = 'running' AND claim_token IS NOT NULL AND lease_expires_at IS NOT NULL)
               OR (state <> 'running' AND claim_token IS NULL AND lease_expires_at IS NULL))
);

CREATE INDEX ix_memory_jobs_campaign_id ON memory_jobs (campaign_id);

CREATE INDEX ix_memory_jobs_due ON memory_jobs (state, next_attempt_at);

CREATE UNIQUE INDEX uq_memory_jobs_input
    ON memory_jobs (campaign_id, policy_id, batch_id, kind, previous_checkpoint_id,
                    manifest_hash, producer_version, prompt_version) NULLS NOT DISTINCT;

CREATE INDEX ix_memory_jobs_policy_campaign ON memory_jobs (policy_id, campaign_id);

CREATE INDEX ix_memory_jobs_batch_scope ON memory_jobs (batch_id, campaign_id, policy_id);

CREATE INDEX ix_memory_jobs_state_scope ON memory_jobs (memory_state_id, campaign_id, policy_id);

CREATE INDEX ix_memory_jobs_checkpoint_scope
    ON memory_jobs (previous_checkpoint_id, campaign_id, policy_id);

CREATE TABLE memory_job_attempts (
    id uuid PRIMARY KEY,
    job_id uuid NOT NULL,
    campaign_id uuid NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    attempt_number integer NOT NULL,
    retry_cycle integer NOT NULL,
    state varchar(16) NOT NULL,
    claim_token uuid NOT NULL,
    started_at timestamptz NOT NULL,
    finished_at timestamptz,
    error varchar(500),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_memory_job_attempts_job_campaign
        FOREIGN KEY (job_id, campaign_id) REFERENCES memory_jobs(id, campaign_id)
        DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT uq_memory_job_attempts_id_campaign UNIQUE (id, campaign_id),
    CONSTRAINT uq_memory_job_attempts_provenance UNIQUE (id, job_id, campaign_id),
    CONSTRAINT uq_memory_job_attempts_number UNIQUE (job_id, campaign_id, attempt_number),
    CONSTRAINT ck_memory_job_attempts_counts CHECK (attempt_number > 0 AND retry_cycle >= 0),
    CONSTRAINT ck_memory_job_attempts_state
        CHECK (state IN ('started', 'succeeded', 'failed', 'uncertain'))
);

CREATE INDEX ix_memory_job_attempts_campaign_id ON memory_job_attempts (campaign_id);

CREATE INDEX ix_memory_job_attempts_job_campaign ON memory_job_attempts (job_id, campaign_id);

CREATE TABLE memory_generations (
    id uuid PRIMARY KEY,
    job_id uuid NOT NULL,
    attempt_id uuid NOT NULL,
    campaign_id uuid NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    policy_id uuid NOT NULL,
    batch_id uuid NOT NULL,
    role varchar(16) NOT NULL,
    provider varchar(50) NOT NULL,
    model varchar(200) NOT NULL,
    input_tokens integer,
    output_tokens integer,
    cost numeric(18, 8),
    latency_ms integer,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_memory_generations_job_provenance
        FOREIGN KEY (job_id, campaign_id, policy_id, batch_id)
        REFERENCES memory_jobs(id, campaign_id, policy_id, batch_id) DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT fk_memory_generations_attempt_provenance
        FOREIGN KEY (attempt_id, job_id, campaign_id)
        REFERENCES memory_job_attempts(id, job_id, campaign_id) DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT fk_memory_generations_policy_campaign
        FOREIGN KEY (policy_id, campaign_id) REFERENCES memory_policies(id, campaign_id)
        DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT fk_memory_generations_batch_campaign_policy
        FOREIGN KEY (batch_id, campaign_id, policy_id)
        REFERENCES memory_batches(id, campaign_id, policy_id) DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT uq_memory_generations_document_ref UNIQUE (id, campaign_id, batch_id, policy_id),
    CONSTRAINT ck_memory_generations_role CHECK (role IN ('batch', 'summary', 'facts', 'global')),
    CONSTRAINT ck_memory_generations_input_tokens CHECK (input_tokens IS NULL OR input_tokens >= 0),
    CONSTRAINT ck_memory_generations_output_tokens CHECK (output_tokens IS NULL OR output_tokens >= 0),
    CONSTRAINT ck_memory_generations_cost CHECK (cost IS NULL OR cost >= 0),
    CONSTRAINT ck_memory_generations_latency CHECK (latency_ms IS NULL OR latency_ms >= 0)
);

CREATE INDEX ix_memory_generations_campaign_id ON memory_generations (campaign_id);

CREATE INDEX ix_memory_generations_job_scope
    ON memory_generations (job_id, campaign_id, policy_id, batch_id);

CREATE INDEX ix_memory_generations_attempt_scope
    ON memory_generations (attempt_id, job_id, campaign_id);

CREATE INDEX ix_memory_generations_policy_scope ON memory_generations (policy_id, campaign_id);

CREATE INDEX ix_memory_generations_batch_scope
    ON memory_generations (batch_id, campaign_id, policy_id);

ALTER TABLE memory_summaries
    ADD CONSTRAINT fk_memory_summaries_generation
    FOREIGN KEY (generation_id, campaign_id, batch_id, policy_id)
    REFERENCES memory_generations(id, campaign_id, batch_id, policy_id)
    DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE memory_facts
    ADD CONSTRAINT fk_memory_facts_generation
    FOREIGN KEY (generation_id, campaign_id, batch_id, policy_id)
    REFERENCES memory_generations(id, campaign_id, batch_id, policy_id)
    DEFERRABLE INITIALLY DEFERRED;

ALTER TABLE memory_global_checkpoints
    ADD CONSTRAINT fk_memory_global_checkpoints_generation
    FOREIGN KEY (generation_id, campaign_id, batch_id, policy_id)
    REFERENCES memory_generations(id, campaign_id, batch_id, policy_id)
    DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE turn_requests (
    request_id uuid PRIMARY KEY,
    campaign_id uuid NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    payload_hash varchar(64) NOT NULL,
    starting_head_turn_id uuid,
    context_epoch integer NOT NULL,
    state varchar(16) NOT NULL,
    execution_token uuid,
    execution_expires_at timestamptz,
    claimed_turn_number integer,
    result_turn_id uuid,
    error varchar(500),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_turn_requests_start_head_campaign
        FOREIGN KEY (starting_head_turn_id, campaign_id) REFERENCES turns(id, campaign_id)
        DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT fk_turn_requests_result_turn_campaign
        FOREIGN KEY (result_turn_id, campaign_id) REFERENCES turns(id, campaign_id)
        DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT uq_turn_requests_campaign_request UNIQUE (campaign_id, request_id),
    CONSTRAINT uq_turn_requests_request_campaign UNIQUE (request_id, campaign_id),
    CONSTRAINT ck_turn_requests_state CHECK (state IN ('running', 'committed', 'interrupted', 'invalidated')),
    CONSTRAINT ck_turn_requests_execution_state
        CHECK ((state = 'running' AND execution_token IS NOT NULL AND execution_expires_at IS NOT NULL)
               OR (state <> 'running' AND execution_token IS NULL AND execution_expires_at IS NULL)),
    CONSTRAINT ck_turn_requests_result_state
        CHECK ((state = 'committed') = (result_turn_id IS NOT NULL)
               AND (state <> 'running' OR claimed_turn_number IS NOT NULL)),
    CONSTRAINT ck_turn_requests_claimed_number
        CHECK (claimed_turn_number IS NULL OR claimed_turn_number > 0),
    CONSTRAINT ck_turn_requests_context_epoch CHECK (context_epoch >= 0),
    CONSTRAINT ck_turn_requests_payload_hash CHECK (payload_hash ~ '^[0-9a-f]{64}$')
);

CREATE INDEX ix_turn_requests_campaign_id ON turn_requests (campaign_id);

CREATE INDEX ix_turn_requests_start_head_scope
    ON turn_requests (starting_head_turn_id, campaign_id);

CREATE INDEX ix_turn_requests_result_turn_scope ON turn_requests (result_turn_id, campaign_id);

CREATE UNIQUE INDEX uq_turn_requests_campaign_running
    ON turn_requests (campaign_id) WHERE state = 'running';

ALTER TABLE campaigns ADD COLUMN active_action_request_id uuid;

ALTER TABLE campaigns
    ADD CONSTRAINT fk_campaigns_active_action_request
    FOREIGN KEY (active_action_request_id, id)
    REFERENCES turn_requests(request_id, campaign_id)
    DEFERRABLE INITIALLY DEFERRED;
