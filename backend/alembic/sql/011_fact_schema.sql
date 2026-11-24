ALTER TABLE memory_facts
    ALTER COLUMN turn_number DROP NOT NULL,
    ALTER COLUMN entity_name DROP NOT NULL,
    ALTER COLUMN entity_type DROP NOT NULL,
    ADD COLUMN batch_id uuid,
    ADD COLUMN policy_id uuid,
    ADD COLUMN ordinal integer,
    ADD COLUMN category varchar(20),
    ADD COLUMN assertion_type varchar(20),
    ADD COLUMN fact_metadata jsonb,
    ADD COLUMN generation_id uuid,
    ADD COLUMN schema_version integer,
    ADD CONSTRAINT uq_memory_facts_batch_scope UNIQUE (id, batch_id, campaign_id),
    ADD CONSTRAINT uq_memory_facts_batch_ordinal UNIQUE (batch_id, ordinal),
    ADD CONSTRAINT fk_memory_facts_batch FOREIGN KEY (batch_id, campaign_id, policy_id)
        REFERENCES memory_batches (id, campaign_id, policy_id) DEFERRABLE INITIALLY DEFERRED,
    ADD CONSTRAINT ck_memory_facts_production_contract CHECK (
        (batch_id IS NULL AND policy_id IS NULL AND ordinal IS NULL AND category IS NULL
         AND assertion_type IS NULL AND fact_metadata IS NULL AND generation_id IS NULL AND schema_version IS NULL)
        OR (batch_id IS NOT NULL AND policy_id IS NOT NULL AND ordinal IS NOT NULL
            AND ordinal > 0 AND category IS NOT NULL AND assertion_type IS NOT NULL
            AND fact_metadata IS NOT NULL AND generation_id IS NOT NULL
            AND schema_version IS NOT NULL AND schema_version = 1 AND btrim(content) <> ''
            AND turn_number IS NULL AND entity_name IS NULL AND entity_type IS NULL)
    ),
    ADD CONSTRAINT ck_memory_facts_category CHECK (
        category IN ('event','information','commitment','relationship','state_change')
    ),
    ADD CONSTRAINT ck_memory_facts_assertion CHECK (
        assertion_type IN ('occurrence','statement','belief','intention')
    );

CREATE INDEX ix_memory_facts_batch_id ON memory_facts (batch_id);

CREATE INDEX ix_memory_facts_policy_id ON memory_facts (policy_id);

CREATE INDEX ix_memory_facts_generation_id ON memory_facts (generation_id);

CREATE TABLE memory_fact_sources (
    fact_id uuid NOT NULL,
    turn_id uuid NOT NULL,
    batch_id uuid NOT NULL,
    campaign_id uuid NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
    PRIMARY KEY (fact_id, turn_id),
    CONSTRAINT fk_memory_fact_sources_fact FOREIGN KEY (fact_id, batch_id, campaign_id)
        REFERENCES memory_facts (id, batch_id, campaign_id) DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT fk_memory_fact_sources_membership FOREIGN KEY (batch_id, turn_id, campaign_id)
        REFERENCES memory_batch_turns (batch_id, turn_id, campaign_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE INDEX ix_memory_fact_sources_batch_id ON memory_fact_sources (batch_id);

CREATE INDEX ix_memory_fact_sources_campaign_id ON memory_fact_sources (campaign_id);
