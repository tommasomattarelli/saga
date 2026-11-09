CREATE FUNCTION saga_memory_job_guard() RETURNS trigger LANGUAGE plpgsql AS $$
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

CREATE TRIGGER memory_job_guard BEFORE INSERT OR UPDATE ON memory_jobs
FOR EACH ROW EXECUTE FUNCTION saga_memory_job_guard();

CREATE FUNCTION saga_memory_job_sources() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    expected_ids jsonb;
    expected_hash text;
BEGIN
    SELECT jsonb_agg(m.turn_id ORDER BY m.ordinal), b.manifest_hash INTO expected_ids, expected_hash
    FROM memory_batches b JOIN memory_batch_turns m ON m.batch_id = b.id
    WHERE b.id = NEW.batch_id AND b.campaign_id = NEW.campaign_id AND b.policy_id = NEW.policy_id
    GROUP BY b.id, b.manifest_hash;
    IF NEW.manifest->'source_turn_ids' IS DISTINCT FROM expected_ids
        OR NEW.manifest->>'source_hash' IS DISTINCT FROM expected_hash THEN
        RAISE EXCEPTION 'A memory job must reference its complete ordered batch input.' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

CREATE CONSTRAINT TRIGGER memory_job_sources AFTER INSERT ON memory_jobs
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION saga_memory_job_sources();

CREATE FUNCTION saga_memory_generation_guard() RETURNS trigger LANGUAGE plpgsql AS $$
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

CREATE TRIGGER memory_generation_guard BEFORE UPDATE OR DELETE ON memory_generations
FOR EACH ROW EXECUTE FUNCTION saga_memory_generation_guard();

CREATE FUNCTION saga_turn_request_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF ROW(NEW.request_id, NEW.campaign_id, NEW.payload_hash, NEW.starting_head_turn_id,
           NEW.context_epoch)
       IS DISTINCT FROM
       ROW(OLD.request_id, OLD.campaign_id, OLD.payload_hash, OLD.starting_head_turn_id,
           OLD.context_epoch) THEN
        RAISE EXCEPTION 'Turn request identity is immutable.' USING ERRCODE = '23514';
    END IF;
    IF OLD.claimed_turn_number IS NOT NULL
       AND NEW.claimed_turn_number IS DISTINCT FROM OLD.claimed_turn_number THEN
        RAISE EXCEPTION 'A claimed turn number is immutable.' USING ERRCODE = '23514';
    END IF;
    IF OLD.result_turn_id IS NOT NULL AND NEW.result_turn_id IS DISTINCT FROM OLD.result_turn_id THEN
        RAISE EXCEPTION 'A committed turn result is immutable.' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER turn_request_guard BEFORE UPDATE ON turn_requests
FOR EACH ROW EXECUTE FUNCTION saga_turn_request_guard();
