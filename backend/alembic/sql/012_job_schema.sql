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
